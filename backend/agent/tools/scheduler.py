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
from backend.services import schedule_service
from backend.services.schedule_service.academic_calendar_provider import get_calendar_overrides
from backend.services.schedule_service.enums import CourseOccurrenceKind, DeadlineType
from backend.services.schedule_service.service_config import TIS_WEEK1_MONDAY


async def _get_week1_monday() -> datetime:
    try:
        from backend.services.schedule_service.academic_calendar_provider import get_calendar_overrides

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
        for src, dst in sorted(overrides.move_rules, key=lambda pair: (pair[1], pair[0]))
    ]
    cancel_days = [
        {
            "date": d.isoformat(),
            "weekday": _weekday_label(datetime(d.year, d.month, d.day)),
        }
        for d in sorted(overrides.cancel_days)
    ]
    return {
        "week1_monday": overrides.week1_monday.isoformat() if overrides.week1_monday else None,
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
        _serialize_occurrence(course, week1=week1)
        for course in effective_day.courses
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
