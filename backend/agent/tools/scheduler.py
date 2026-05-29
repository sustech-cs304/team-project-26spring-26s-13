"""
backend/agent/tools/scheduler.py
日程相关工具：爬取 Blackboard DDL、教务系统课表，检测时间冲突。

所有工具函数通过 @agent.tool 装饰器注册到 PydanticAI Agent。
工具函数必须是 async，第一个参数固定为 RunContext[AgentDeps]。
工具返回值是字符串（LLM 消费），结构化数据通过 ctx.deps 传出（或在 loop.py 中拦截）。
"""

import json
import re
from datetime import datetime, timedelta

from pydantic_ai import RunContext

from backend.agent.core import AgentDeps, agent
from backend.agent.tools.base import safe_tool
from backend.schemas.agent import ScheduleData, ScheduleEvent, ScheduleConflict
from backend.services import material_service, schedule_service, task_service
from backend.services.schedule_service.academic_calendar_provider import (
    get_calendar_overrides,
)
from backend.services.schedule_service.enums import CourseOccurrenceKind, DeadlineType
from backend.services.schedule_service.service_config import TIS_WEEK1_MONDAY


def _parse_json_payload(raw: str) -> object:
    if not (raw or "").strip() or raw.startswith("ERROR:"):
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _parse_event_start(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if "~" in raw:
        raw = raw.split("~", 1)[0].strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        return None


def _parse_event_end(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if "~" not in raw:
        return None
    try:
        parsed = datetime.fromisoformat(
            raw.split("~", 1)[1].strip().replace("Z", "+00:00")
        )
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        return None


def _event_sort_key(item: dict[str, object]) -> datetime:
    parsed = _parse_event_start(str(item.get("time") or item.get("start_time") or ""))
    return parsed or datetime.max


def _normalize_schedule_event(item: dict[str, object], idx: int) -> dict[str, str]:
    return {
        "event_id": str(item.get("event_id") or f"schedule_event_{idx}"),
        "title": str(item.get("title") or item.get("course") or "Untitled event"),
        "time": str(item.get("time") or item.get("deadline") or ""),
        "source": str(item.get("source") or "Schedule"),
        "detail": str(item.get("detail") or ""),
    }


def _personal_task_to_event(item: dict[str, object], idx: int) -> dict[str, str]:
    start = str(item.get("start_time") or "")
    end = str(item.get("end_time") or "")
    time_label = f"{start}~{end}" if end else start
    detail_parts: list[str] = []
    if item.get("location"):
        detail_parts.append(f"location={item['location']}")
    if item.get("description"):
        detail_parts.append(f"description={item['description']}")
    return {
        "event_id": str(item.get("task_id") or f"personal_task_{idx}"),
        "title": str(item.get("title") or "Personal task"),
        "time": time_label,
        "source": "Local TODO",
        "detail": " ".join(detail_parts),
    }


def _build_proactive_notes(
    events: list[dict[str, str]],
    conflicts: list[dict[str, str]],
    *,
    now: datetime,
) -> list[str]:
    notes: list[str] = []
    if conflicts:
        notes.append(f"检测到 {len(conflicts)} 个潜在时间冲突，优先处理冲突项。")

    upcoming = []
    for event in events:
        start = _parse_event_start(event.get("time", ""))
        if start is None:
            continue
        if start.tzinfo is not None and now.tzinfo is None:
            start = start.replace(tzinfo=None)
        if now <= start <= now + timedelta(days=3):
            upcoming.append((start, event))

    upcoming.sort(key=lambda x: x[0])
    for start, event in upcoming[:5]:
        source = event.get("source") or "Schedule"
        notes.append(
            f"{event.get('title', '事项')} 将在 {start.strftime('%Y-%m-%d %H:%M')} 前后到来，来源：{source}。"
        )

    if not notes and events:
        notes.append("近期没有明显冲突；可按截止时间从近到远安排学习块。")
    return notes[:6]


def _detect_simple_overlaps(events: list[dict[str, str]]) -> list[dict[str, str]]:
    intervals: list[tuple[datetime, datetime, dict[str, str]]] = []
    points: list[tuple[datetime, dict[str, str]]] = []
    for event in events:
        start = _parse_event_start(event.get("time", ""))
        if start is None:
            continue
        end = _parse_event_end(event.get("time", ""))
        if end is not None and end > start:
            intervals.append((start, end, event))
        else:
            points.append((start, event))

    conflicts: list[dict[str, str]] = []
    intervals.sort(key=lambda x: x[0])
    for i, (start_a, end_a, event_a) in enumerate(intervals):
        for start_b, end_b, event_b in intervals[i + 1 :]:
            if start_b >= end_a:
                break
            if end_b > start_a:
                conflicts.append(
                    {
                        "title": event_a["title"],
                        "detail": f"overlaps_with={event_b['title']} time={event_a['time']} vs {event_b['time']}",
                    }
                )

    for point, event in points:
        for start, end, interval_event in intervals:
            if start <= point <= end:
                conflicts.append(
                    {
                        "title": event["title"],
                        "detail": f"deadline_inside_event={interval_event['title']} deadline_at={event['time']} event_time={interval_event['time']}",
                    }
                )
    return conflicts[:20]


async def _get_week1_monday() -> datetime:
    try:
        from backend.services.schedule_service.academic_calendar_provider import (
            get_calendar_overrides,
        )

        overrides = await get_calendar_overrides()
        if overrides.week1_monday is not None:
            d = overrides.week1_monday
            return datetime(d.year, d.month, d.day)
    except Exception:
        return TIS_WEEK1_MONDAY
    return TIS_WEEK1_MONDAY


def _serialize_occurrences(
    occs: list[schedule_service.CourseOccurrence],
    week1: datetime,
) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for o in occs:
        weekday = o.start_at.isoweekday()
        start_time = o.start_at.strftime("%H:%M")
        end_time = o.end_at.strftime("%H:%M")
        location = o.location or ""
        course = o.notes or o.course_id
        instructor = getattr(o, "instructor", "") or ""
        week: int | None = None
        delta_days = (o.start_at.date() - week1.date()).days
        if delta_days >= 0:
            week = delta_days // 7 + 1

        payload.append(
            {
                "course": str(course),
                "course_id": str(o.course_id),
                "date": o.start_at.date().isoformat(),
                "weekday": weekday,
                "week": week,
                "start_time": start_time,
                "end_time": end_time,
                "location": str(location),
                "instructor": str(instructor),
            }
        )

    payload.sort(key=lambda x: (str(x["date"]), str(x["start_time"]), str(x["course"])))
    return payload


def _serialize_occurrence(
    occ: schedule_service.CourseOccurrence,
    *,
    week1: datetime,
) -> dict[str, object]:
    course = occ.notes or occ.course_id
    delta_days = (occ.start_at.date() - week1.date()).days
    week: int | None = delta_days // 7 + 1 if delta_days >= 0 else None
    return {
        "course": str(course),
        "course_id": str(occ.course_id),
        "date": occ.start_at.date().isoformat(),
        "weekday": occ.start_at.isoweekday(),
        "week": week,
        "start_time": occ.start_at.strftime("%H:%M"),
        "end_time": occ.end_at.strftime("%H:%M"),
        "location": str(occ.location or ""),
        "instructor": str(getattr(occ, "instructor", "") or ""),
    }


def _parse_target_date(text: str, fallback_year: int) -> datetime | None:
    raw = (text or "").strip()
    if not raw:
        return None

    iso_candidate = raw.replace("/", "-").replace(".", "-")
    try:
        return datetime.fromisoformat(iso_candidate)
    except ValueError:
        pass

    md_match = re.fullmatch(r"(?:(\d{4})年)?\s*(\d{1,2})月(\d{1,2})日", raw)
    if md_match:
        year = int(md_match.group(1) or fallback_year)
        month = int(md_match.group(2))
        day = int(md_match.group(3))
        try:
            return datetime(year, month, day)
        except ValueError:
            return None

    return None


async def _fetch_schedule_payload(
    cas_account: str,
    cas_password: str,
) -> list[dict[str, object]]:
    occs = await schedule_service.fetch_course_schedule(cas_account, cas_password)
    week1 = await _get_week1_monday()
    return _serialize_occurrences(occs, week1)


def _weekday_label(value: datetime) -> str:
    names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return names[value.weekday()]


async def _fetch_adjustment_payload() -> dict[str, object]:
    overrides = await get_calendar_overrides()
    move_rules = [
        {
            "from_date": src.isoformat(),
            "to_date": dst.isoformat(),
            "from_weekday": _weekday_label(datetime(src.year, src.month, src.day)),
            "to_weekday": _weekday_label(datetime(dst.year, dst.month, dst.day)),
            "summary": f"{dst.isoformat()}（{_weekday_label(datetime(dst.year, dst.month, dst.day))}）补 {src.isoformat()}（{_weekday_label(datetime(src.year, src.month, src.day))}）的课",
        }
        for src, dst in sorted(
            overrides.move_rules, key=lambda pair: (pair[1], pair[0])
        )
    ]
    cancel_days = [
        {
            "date": d.isoformat(),
            "weekday": _weekday_label(datetime(d.year, d.month, d.day)),
        }
        for d in sorted(overrides.cancel_days)
    ]
    return {
        "week1_monday": (
            overrides.week1_monday.isoformat() if overrides.week1_monday else None
        ),
        "source_url": overrides.source_url,
        "source_pdf_url": overrides.source_pdf_url,
        "cancel_days": cancel_days,
        "move_rules": move_rules,
    }


@agent.tool
@safe_tool
async def fetch_blackboard_deadlines(ctx: RunContext[AgentDeps]) -> str:
    """
    爬取 Blackboard 上当前用户的所有未完成作业/考试截止时间。
    使用用户的 CAS 账号密码（已存储）模拟登录。

    Returns:
        JSON 字符串，格式：
        [{
          "title": str,
          "course": str,
          "course_id": str,
          "course_name": str,
          "deadline": "ISO8601",
          "type": "assignment"|"exam"|"quiz"
        }]

    Raises（以字符串形式返回给 LLM）：
        "ERROR:CAS_LOGIN_FAILED" - CAS 登录失败
        "ERROR:BLACKBOARD_UNREACHABLE" - Blackboard 无法访问
    """
    cas_account = (ctx.deps.cas_account or "").strip()
    cas_password = ctx.deps.cas_password or ""
    if not cas_account or not cas_password:
        return "ERROR:CAS_LOGIN_FAILED"

    try:
        deadlines = await schedule_service.fetch_blackboard(cas_account, cas_password)
    except PermissionError:
        return "ERROR:CAS_LOGIN_FAILED"
    except ConnectionError:
        return "ERROR:BLACKBOARD_UNREACHABLE"
    except Exception:
        return "ERROR:BLACKBOARD_UNREACHABLE"

    payload = [
        {
            "title": d.title,
            "course": (d.course_name or d.course_id),
            "course_id": d.course_id,
            "course_name": (d.course_name or d.course_id),
            "deadline": d.due_at.isoformat(),
            "type": d.type.value,
            "estimated_minutes": d.estimated_minutes,
            "priority": d.priority,
            "url": d.url,
        }
        for d in deadlines
    ]
    return json.dumps(payload, ensure_ascii=False)


@agent.tool
@safe_tool
async def sync_blackboard_materials(
    ctx: RunContext[AgentDeps],
    course_keyword: str = "",
    keyword: str = "",
    limit: int = 50,
) -> str:
    """
    从 Blackboard 同步当前用户可访问的课件，并复用现有解析与向量化流程入库。

    Returns:
        JSON 字符串，格式为 materials 列表（MaterialInfo）：
        [{"file_id": str, "file_name": str, "file_type": str, "subject_type": str, "vectorized": bool, "uploaded_at": str}]

    Raises（以字符串形式返回给 LLM）：
        "ERROR:CAS_LOGIN_FAILED" - CAS 登录失败/未配置
        "ERROR:BLACKBOARD_UNREACHABLE" - Blackboard 无法访问
    """
    try:
        synced = await material_service.sync_blackboard_materials(
            ctx.deps.db,
            ctx.deps.user,
            course_keyword=(course_keyword or "").strip() or None,
            keyword=(keyword or "").strip() or None,
            limit=limit,
        )
    except (PermissionError, ValueError):
        return "ERROR:CAS_LOGIN_FAILED"
    except ConnectionError:
        return "ERROR:BLACKBOARD_UNREACHABLE"
    except Exception:
        return "ERROR:BLACKBOARD_UNREACHABLE"

    payload = [m.model_dump() for m in synced]
    return json.dumps(payload, ensure_ascii=False, default=str)


async def _auto_persist_courses(
    ctx: RunContext[AgentDeps],
    payload: list[dict[str, object]],
) -> None:
    from datetime import datetime as _dt, timedelta, timezone as _tz

    now = _dt.now(_tz.utc)
    cutoff = now + timedelta(days=60)

    tasks: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        date_s = str(item.get("date") or "").strip()
        start_t = str(item.get("start_time") or "").strip()
        if not date_s or not start_t:
            continue
        try:
            start_dt = _dt.strptime(
                f"{date_s}T{start_t}:00", "%Y-%m-%dT%H:%M:%S"
            ).replace(tzinfo=_tz.utc)
        except ValueError:
            continue
        if start_dt < now or start_dt > cutoff:
            continue
        end_t = str(item.get("end_time") or "").strip()
        end_dt = None
        if end_t:
            try:
                end_dt = _dt.strptime(
                    f"{date_s}T{end_t}:00", "%Y-%m-%dT%H:%M:%S"
                ).replace(tzinfo=_tz.utc)
            except ValueError:
                pass
        course = str(item.get("course") or "").strip()
        instructor = str(item.get("instructor") or "").strip()
        title = f"{course} - {instructor}" if instructor else course
        location = str(item.get("location") or "").strip()
        description = str(item.get("course_id") or "").strip()

        tasks.append(
            {
                "title": title,
                "start_time": start_dt,
                "end_time": end_dt,
                "location": location,
                "description": description,
            }
        )

    if tasks:
        await task_service.upsert_course_tasks(
            db=ctx.deps.db,
            user_id=ctx.deps.user.user_id,
            tasks=tasks,
        )


@agent.tool
@safe_tool
async def fetch_course_schedule(ctx: RunContext[AgentDeps]) -> str:
    """
    爬取教务系统当前学期的完整课表（固定时间段的课程安排）。

    Returns:
        JSON 字符串，格式：
        [{"course": str, "course_id": str, "date": "YYYY-MM-DD", "weekday": 1-7,
          "week": int, "start_time": "HH:MM", "end_time": "HH:MM",
          "location": str, "instructor": str}]

    Raises（字符串）：
        "ERROR:CAS_LOGIN_FAILED"
        "ERROR:ACADEMIC_SYSTEM_UNREACHABLE"
    """
    cas_account = (ctx.deps.cas_account or "").strip()
    cas_password = ctx.deps.cas_password or ""
    if not cas_account or not cas_password:
        return "ERROR:CAS_LOGIN_FAILED"

    try:
        payload = await _fetch_schedule_payload(cas_account, cas_password)
    except PermissionError:
        return "ERROR:CAS_LOGIN_FAILED"
    except ConnectionError:
        return "ERROR:ACADEMIC_SYSTEM_UNREACHABLE"
    except Exception:
        return "ERROR:ACADEMIC_SYSTEM_UNREACHABLE"

    try:
        await _auto_persist_courses(ctx, payload)
    except Exception:
        try:
            await ctx.deps.db.rollback()
        except Exception:
            pass

    return json.dumps(payload, ensure_ascii=False)


@agent.tool
@safe_tool
async def fetch_courses_on_date(ctx: RunContext[AgentDeps], target_date: str) -> str:
    """
    获取某个具体日期的课程安排，适合回答“某月某日第一节课是什么”这类问题。

    Args:
        target_date: 日期字符串，优先使用 YYYY-MM-DD，也兼容 “5月9日”/“2026年5月9日”

    Returns:
        JSON 字符串，格式：
        {
          "date": "YYYY-MM-DD",
          "courses": [
            {"course": str, "course_id": str, "start_time": "HH:MM", "end_time": "HH:MM",
             "location": str, "instructor": str, "weekday": 1-7, "week": int | null}
          ]
        }
    """
    cas_account = (ctx.deps.cas_account or "").strip()
    cas_password = ctx.deps.cas_password or ""
    if not cas_account or not cas_password:
        return "ERROR:CAS_LOGIN_FAILED"

    week1 = await _get_week1_monday()
    parsed = _parse_target_date(target_date, fallback_year=week1.year)
    if parsed is None:
        return "ERROR:INVALID_DATE"

    try:
        effective_day = await schedule_service.query_effective_schedule_for_date(
            cas_account,
            cas_password,
            parsed.date(),
        )
    except PermissionError:
        return "ERROR:CAS_LOGIN_FAILED"
    except ConnectionError:
        return "ERROR:ACADEMIC_SYSTEM_UNREACHABLE"
    except Exception:
        return "ERROR:ACADEMIC_SYSTEM_UNREACHABLE"

    target_iso = parsed.date().isoformat()
    courses = [
        _serialize_occurrence(course, week1=week1) for course in effective_day.courses
    ]
    courses.sort(key=lambda x: (str(x.get("start_time", "")), str(x.get("course", ""))))
    return json.dumps(
        {
            "date": target_iso,
            "teaching_date": (
                effective_day.resolution.teaching_date.isoformat()
                if effective_day.resolution.teaching_date is not None
                else None
            ),
            "adjusted": effective_day.resolution.adjusted,
            "reason": effective_day.resolution.reason,
            "courses": courses,
        },
        ensure_ascii=False,
    )


@agent.tool
@safe_tool
async def fetch_schedule_adjustments(ctx: RunContext[AgentDeps]) -> str:
    """
    获取学期调休/补课安排，适合回答“本学期调休安排是什么”“某天是不是补周几的课”。

    Returns:
        JSON 字符串，格式：
        {
          "week1_monday": "YYYY-MM-DD" | null,
          "cancel_days": [{"date": "YYYY-MM-DD", "weekday": "周X"}],
          "move_rules": [{"from_date": "...", "to_date": "...", "summary": "..."}],
          "source_url": str | null,
          "source_pdf_url": str | null
        }
    """
    _ = ctx
    try:
        payload = await _fetch_adjustment_payload()
    except Exception:
        return "ERROR:CALENDAR_UNAVAILABLE"
    return json.dumps(payload, ensure_ascii=False)


@agent.tool
@safe_tool
async def detect_schedule_conflicts(
    ctx: RunContext[AgentDeps],
    deadlines_json: str,
    course_schedule_json: str,
) -> str:
    """
    将 Blackboard DDL 列表与固定课表合并，检测时间冲突。
    不需要爬网页，纯本地逻辑。

    Args:
        deadlines_json:       fetch_blackboard_deadlines 的返回值
        course_schedule_json: fetch_course_schedule 的返回值

    Returns:
        JSON 字符串，格式：
        {
          "events":    [...],   # 所有事件，格式同 ScheduleEvent
          "conflicts": [...]    # 检测到的冲突，格式同 ScheduleConflict
        }
    """
    _ = ctx

    if (deadlines_json or "").startswith("ERROR:"):
        return deadlines_json
    if (course_schedule_json or "").startswith("ERROR:"):
        return course_schedule_json

    try:
        dl_raw = json.loads(deadlines_json or "[]")
        cs_raw = json.loads(course_schedule_json or "[]")
    except Exception:
        return "ERROR:INVALID_INPUT"

    if not isinstance(dl_raw, list) or not isinstance(cs_raw, list):
        return "ERROR:INVALID_INPUT"

    allowed_types = {member.value for member in DeadlineType}
    type_map = {"exam": DeadlineType.OTHER.value}

    deadlines: list[schedule_service.Deadline] = []
    for item in dl_raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        course = str(item.get("course") or "").strip()
        course_id = str(item.get("course_id") or "").strip()
        course_name = str(item.get("course_name") or course or course_id).strip()
        deadline_s = str(item.get("deadline") or "").strip()
        typ = str(item.get("type") or "other").strip().lower()
        typ = type_map.get(typ, typ)
        if typ not in allowed_types:
            typ = "other"
        if not title or not (course or course_id or course_name) or not deadline_s:
            continue
        try:
            due_at = datetime.fromisoformat(deadline_s)
        except Exception:
            continue
        normalized_course_id = course_id or course_name or course
        deadlines.append(
            schedule_service.Deadline(
                title=title,
                course_id=normalized_course_id,
                due_at=due_at,
                type=typ,
                course_name=course_name or None,
            )
        )

    week1 = await _get_week1_monday()

    course_slots: list[schedule_service.CourseOccurrence] = []

    def _dt(day0: datetime, hhmm: str) -> datetime:
        hh, mm = hhmm.split(":", 1)
        return datetime(day0.year, day0.month, day0.day, int(hh), int(mm))

    for row in cs_raw:
        if not isinstance(row, dict):
            continue
        course = str(row.get("course") or "").strip()
        location = str(row.get("location") or "").strip()
        try:
            weekday = int(row.get("weekday"))
        except Exception:
            continue
        start_time = str(row.get("start_time") or "").strip()
        end_time = str(row.get("end_time") or "").strip()
        if not course or weekday < 1 or weekday > 7 or not start_time or not end_time:
            continue

        date_s = str(row.get("date") or "").strip()
        if date_s:
            try:
                day0 = datetime.fromisoformat(date_s)
            except Exception:
                continue
            try:
                start_at = _dt(day0, start_time)
                end_at = _dt(day0, end_time)
            except Exception:
                continue
            if end_at <= start_at:
                continue
            course_slots.append(
                schedule_service.CourseOccurrence(
                    course_id=course,
                    start_at=start_at,
                    end_at=end_at,
                    location=location,
                    kind=CourseOccurrenceKind.LECTURE,
                    notes=course,
                )
            )
            continue

        weeks = row.get("weeks") or []
        if not isinstance(weeks, list):
            continue

        for w in weeks:
            try:
                wi = int(w)
            except Exception:
                continue
            if wi <= 0:
                continue
            day0 = week1 + timedelta(days=(wi - 1) * 7 + (weekday - 1))
            try:
                start_at = _dt(day0, start_time)
                end_at = _dt(day0, end_time)
            except Exception:
                continue
            if end_at <= start_at:
                continue
            course_slots.append(
                schedule_service.CourseOccurrence(
                    course_id=course,
                    start_at=start_at,
                    end_at=end_at,
                    location=location,
                    kind=CourseOccurrenceKind.LECTURE,
                    notes=course,
                )
            )

    result = schedule_service.detect_conflicts(deadlines, course_slots)
    return json.dumps(result.model_dump(), ensure_ascii=False)


@agent.tool
@safe_tool
async def build_proactive_schedule_context(
    ctx: RunContext[AgentDeps],
    schedule_data_json: str = "",
    deadlines_json: str = "",
    course_schedule_json: str = "",
    personal_tasks_json: str = "",
    planning_window_days: int = 14,
) -> str:
    """
    将前面调度工具的结果压缩成 Agent 可直接用于主动规划的上下文。

    典型调用顺序：
      1. fetch_blackboard_deadlines / fetch_course_schedule / list_personal_tasks
      2. detect_schedule_conflicts（可选）
      3. build_proactive_schedule_context

    Args:
        schedule_data_json: detect_schedule_conflicts 的 JSON 返回；也兼容
                            {"events": [...], "conflicts": [...]} 结构。
        deadlines_json: fetch_blackboard_deadlines 的 JSON 返回；当还没有
                        detect_schedule_conflicts 输出时可直接传入。
        course_schedule_json: fetch_course_schedule 的 JSON 返回；当还没有
                              detect_schedule_conflicts 输出时可直接传入。
        personal_tasks_json: list_personal_tasks 的 JSON 返回。
        planning_window_days: 只保留未来 N 天内的事件，默认 14 天。

    Returns:
        JSON 字符串，包含 events、conflicts、proactive_notes、sources。
        LLM 应基于 proactive_notes 和 conflicts 生成最终学习计划。
    """
    _ = ctx
    try:
        window_days = max(1, min(int(planning_window_days), 60))
    except Exception:
        window_days = 14

    schedule_payload = _parse_json_payload(schedule_data_json)
    deadlines_payload = _parse_json_payload(deadlines_json)
    course_payload = _parse_json_payload(course_schedule_json)
    personal_payload = _parse_json_payload(personal_tasks_json)

    events: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []

    if isinstance(schedule_payload, dict):
        raw_events = schedule_payload.get("events") or []
        if isinstance(raw_events, list):
            for idx, item in enumerate(raw_events, start=1):
                if isinstance(item, dict):
                    events.append(_normalize_schedule_event(item, idx))

        raw_conflicts = schedule_payload.get("conflicts") or []
        if isinstance(raw_conflicts, list):
            for item in raw_conflicts:
                if isinstance(item, dict):
                    conflicts.append(
                        {
                            "title": str(item.get("title") or "Schedule conflict"),
                            "detail": str(item.get("detail") or ""),
                        }
                    )

    if isinstance(deadlines_payload, list):
        for idx, item in enumerate(deadlines_payload, start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "Blackboard deadline")
            deadline = str(item.get("deadline") or "")
            if not deadline:
                continue
            course = str(
                item.get("course_name")
                or item.get("course")
                or item.get("course_id")
                or ""
            )
            detail_parts = []
            if course:
                detail_parts.append(f"course={course}")
            if item.get("type"):
                detail_parts.append(f"type={item['type']}")
            if item.get("priority") is not None:
                detail_parts.append(f"priority={item['priority']}")
            events.append(
                {
                    "event_id": str(item.get("event_id") or f"bb_deadline_{idx}"),
                    "title": title,
                    "time": deadline,
                    "source": "Blackboard",
                    "detail": " ".join(detail_parts),
                }
            )

    if isinstance(course_payload, list):
        for idx, item in enumerate(course_payload, start=1):
            if not isinstance(item, dict):
                continue
            course = str(item.get("course") or item.get("course_id") or "")
            date_s = str(item.get("date") or "")
            start_time = str(item.get("start_time") or "")
            end_time = str(item.get("end_time") or "")
            if not course or not date_s or not start_time:
                continue
            time_label = f"{date_s}T{start_time}:00"
            if end_time:
                time_label = f"{time_label}~{date_s}T{end_time}:00"
            detail_parts = []
            if item.get("location"):
                detail_parts.append(f"location={item['location']}")
            if item.get("instructor"):
                detail_parts.append(f"instructor={item['instructor']}")
            events.append(
                {
                    "event_id": str(item.get("event_id") or f"course_{idx}"),
                    "title": course,
                    "time": time_label,
                    "source": "教务系统",
                    "detail": " ".join(detail_parts),
                }
            )

    if isinstance(personal_payload, list):
        for idx, item in enumerate(personal_payload, start=1):
            if isinstance(item, dict):
                events.append(_personal_task_to_event(item, idx))

    now = datetime.now()
    window_end = now + timedelta(days=window_days)
    filtered_events: list[dict[str, str]] = []
    for event in events:
        start = _parse_event_start(event.get("time", ""))
        if start is None:
            filtered_events.append(event)
            continue
        comparable = start.replace(tzinfo=None) if start.tzinfo else start
        if now <= comparable <= window_end:
            filtered_events.append(event)

    filtered_events.sort(key=_event_sort_key)
    derived_conflicts = _detect_simple_overlaps(filtered_events)
    all_conflicts = conflicts + [c for c in derived_conflicts if c not in conflicts]
    sources = sorted(
        {
            event.get("source", "").strip()
            for event in filtered_events
            if event.get("source", "").strip()
        }
    )

    return json.dumps(
        {
            "planning_window_days": window_days,
            "events": filtered_events[:50],
            "conflicts": all_conflicts[:25],
            "proactive_notes": _build_proactive_notes(
                filtered_events,
                all_conflicts,
                now=now,
            ),
            "sources": sources,
        },
        ensure_ascii=False,
    )
