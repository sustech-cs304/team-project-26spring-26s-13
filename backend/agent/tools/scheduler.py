"""
backend/agent/tools/scheduler.py
日程相关工具：爬取 Blackboard DDL、教务系统课表，检测时间冲突。

所有工具函数通过 @agent.tool 装饰器注册到 PydanticAI Agent。
工具函数必须是 async，第一个参数固定为 RunContext[AgentDeps]。
工具返回值是字符串（LLM 消费），结构化数据通过 ctx.deps 传出（或在 loop.py 中拦截）。
"""

import json
from datetime import datetime, timedelta

from pydantic_ai import RunContext

from backend.agent.core import AgentDeps, agent
from backend.schemas.agent import ScheduleData, ScheduleEvent, ScheduleConflict
from backend.services import schedule_service
from backend.services.schedule_service.constants import _TIS_WEEK1_MONDAY


@agent.tool
async def fetch_blackboard_deadlines(ctx: RunContext[AgentDeps]) -> str:
    """
    爬取 Blackboard 上当前用户的所有未完成作业/考试截止时间。
    使用用户的 CAS 账号密码（已存储）模拟登录。

    Returns:
        JSON 字符串，格式：
        [{"title": str, "course": str, "deadline": "ISO8601", "type": "assignment"|"exam"|"quiz"}]

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
            "course": d.course_id,
            "deadline": d.due_at.isoformat(),
            "type": d.type,
        }
        for d in deadlines
    ]
    return json.dumps(payload, ensure_ascii=False)


@agent.tool
async def fetch_course_schedule(ctx: RunContext[AgentDeps]) -> str:
    """
    爬取教务系统当前学期的完整课表（固定时间段的课程安排）。

    Returns:
        JSON 字符串，格式：
        [{"course": str, "weekday": 1-7, "start_time": "HH:MM", "end_time": "HH:MM",
          "location": str, "weeks": [1,2,...,16]}]

    Raises（字符串）：
        "ERROR:CAS_LOGIN_FAILED"
        "ERROR:ACADEMIC_SYSTEM_UNREACHABLE"
    """
    cas_account = (ctx.deps.cas_account or "").strip()
    cas_password = ctx.deps.cas_password or ""
    if not cas_account or not cas_password:
        return "ERROR:CAS_LOGIN_FAILED"

    try:
        occs = await schedule_service.fetch_course_schedule(cas_account, cas_password)
    except PermissionError:
        return "ERROR:CAS_LOGIN_FAILED"
    except ConnectionError:
        return "ERROR:ACADEMIC_SYSTEM_UNREACHABLE"
    except Exception:
        return "ERROR:ACADEMIC_SYSTEM_UNREACHABLE"

    week1 = _TIS_WEEK1_MONDAY

    grouped: dict[tuple[str, int, str, str, str], dict] = {}
    for o in occs:
        weekday = o.start_at.isoweekday()
        start_time = o.start_at.strftime("%H:%M")
        end_time = o.end_at.strftime("%H:%M")
        location = o.location or ""
        course = o.notes or o.course_id

        weeks: list[int] = []
        if week1 is not None:
            delta_days = (o.start_at.date() - week1.date()).days
            if delta_days >= 0:
                weeks = [delta_days // 7 + 1]

        key = (str(course), weekday, start_time, end_time, str(location))
        row = grouped.get(key)
        if row is None:
            row = {
                "course": str(course),
                "weekday": weekday,
                "start_time": start_time,
                "end_time": end_time,
                "location": str(location),
                "weeks": [],
            }
            grouped[key] = row
        row["weeks"].extend(weeks)

    for row in grouped.values():
        row["weeks"] = sorted({int(x) for x in row.get("weeks", []) if isinstance(x, int) or str(x).isdigit()})

    payload = list(grouped.values())
    payload.sort(key=lambda x: (x["weekday"], x["start_time"], x["course"]))
    return json.dumps(payload, ensure_ascii=False)


@agent.tool
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

    allowed_types = {"assignment", "quiz", "project", "presentation", "other"}
    type_map = {"exam": "other"}

    deadlines: list[schedule_service.Deadline] = []
    for item in dl_raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        course = str(item.get("course") or "").strip()
        deadline_s = str(item.get("deadline") or "").strip()
        typ = str(item.get("type") or "other").strip().lower()
        typ = type_map.get(typ, typ)
        if typ not in allowed_types:
            typ = "other"
        if not title or not course or not deadline_s:
            continue
        try:
            due_at = datetime.fromisoformat(deadline_s)
        except Exception:
            continue
        deadlines.append(
            schedule_service.Deadline(
                title=title,
                course_id=course,
                due_at=due_at,
                type=typ,
            )
        )

    week1 = _TIS_WEEK1_MONDAY

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
        weeks = row.get("weeks") or []
        if not course or weekday < 1 or weekday > 7 or not start_time or not end_time or not isinstance(weeks, list):
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
                    kind="lecture",
                    notes=course,
                )
            )

    result = schedule_service.detect_conflicts(deadlines, course_slots)
    return json.dumps(result.model_dump(), ensure_ascii=False)
