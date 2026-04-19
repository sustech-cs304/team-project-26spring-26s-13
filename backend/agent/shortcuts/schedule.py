from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.postgres import ChatMessage, ChatSession, User
from backend.schemas.agent import (
    AgentRequest,
    AgentResponse,
    AssistantMessage,
    ScheduleData,
    ScheduleEvent,
    TraceItem,
    UIPayload,
)
from backend.utils.crypto import decrypt

TraceEmitter = Callable[[TraceItem], Awaitable[None] | None]


def _extract_explicit_date(text: str) -> str | None:
    patterns = [
        r"20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}",
        r"(?:20\d{2}年)?\d{1,2}月\d{1,2}日",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None


def _is_specific_schedule_query(text: str) -> bool:
    lowered = (text or "").lower()
    if not _extract_explicit_date(text):
        return False
    schedule_keywords = (
        "课表",
        "课程",
        "上课",
        "第1节",
        "第一节",
        "安排",
        "schedule",
        "course",
        "timetable",
        "class",
    )
    return any(keyword in text or keyword in lowered for keyword in schedule_keywords)


def _is_adjustment_query(text: str) -> bool:
    lowered = (text or "").lower()
    keywords = (
        "调休",
        "补课",
        "补班",
        "校历",
        "holiday",
        "make-up",
        "makeup",
        "calendar",
    )
    schedule_scope = ("学期" in text) or ("semester" in lowered) or bool(_extract_explicit_date(text))
    return schedule_scope and any(keyword in text or keyword in lowered for keyword in keywords)


def _is_conflict_query(text: str) -> bool:
    lowered = (text or "").lower()
    keywords = (
        "冲突",
        "重叠",
        "撞课",
        "conflict",
        "overlap",
    )
    return bool(_extract_explicit_date(text)) and any(keyword in text or keyword in lowered for keyword in keywords)


def _extract_time_range(text: str) -> tuple[time, time] | None:
    match = re.search(r"(\d{1,2}:\d{2})\s*(?:~|-|到|至)\s*(\d{1,2}:\d{2})", text)
    if not match:
        return None
    try:
        start_time = datetime.strptime(match.group(1), "%H:%M").time()
        end_time = datetime.strptime(match.group(2), "%H:%M").time()
    except ValueError:
        return None
    if end_time <= start_time:
        return None
    return start_time, end_time


async def _persist_chat_turn(
    db: AsyncSession,
    *,
    user_id,
    session_id: str,
    user_prompt: str,
    assistant_content: str,
) -> None:
    stmt_session = select(ChatSession).where(ChatSession.session_id == session_id)
    chat_session = (await db.execute(stmt_session)).scalar_one_or_none()
    if chat_session is None:
        chat_session = ChatSession(session_id=session_id, user_id=user_id)
        db.add(chat_session)
    chat_session.updated_at = datetime.now(timezone.utc)

    user_message_time = datetime.now(timezone.utc)
    assistant_message_time = user_message_time + timedelta(microseconds=1)
    db.add_all(
        [
            ChatMessage(
                session_id=session_id,
                role="user",
                content=user_prompt,
                timestamp=user_message_time,
            ),
            ChatMessage(
                session_id=session_id,
                role="assistant",
                content=assistant_content,
                timestamp=assistant_message_time,
            ),
        ]
    )
    await db.commit()


async def try_handle_specific_schedule_query(
    db: AsyncSession,
    user: User,
    request: AgentRequest,
    *,
    user_prompt: str,
    emit_trace: TraceEmitter,
    traces: list[TraceItem],
) -> AgentResponse | None:
    from backend.agent.tools import scheduler as scheduler_tools

    if _is_adjustment_query(user_prompt):
        await emit_trace(
            TraceItem(
                phase="Tool Use",
                title="查询调休安排",
                detail="检测到调休/补课问题，直接查询校历 overrides。",
                status="running",
                timestamp=datetime.now(timezone.utc),
            )
        )

        try:
            payload = await scheduler_tools._fetch_adjustment_payload()
        except Exception:
            payload = None

        if payload is not None:
            move_rules = payload.get("move_rules", [])
            cancel_days = payload.get("cancel_days", [])
            lines = ["本学期调休安排如下：", ""]
            if isinstance(move_rules, list) and move_rules:
                lines.append("补课安排：")
                for row in move_rules:
                    lines.append(f"- {row.get('summary', '')}")
                lines.append("")
            if isinstance(cancel_days, list) and cancel_days:
                lines.append("停课日期：")
                for row in cancel_days:
                    lines.append(f"- {row.get('date', '')}（{row.get('weekday', '')}）")
            if len(lines) <= 2:
                lines.append("当前未解析到明确的调休/补课规则。")
            assistant_content = "\n".join(lines)

            await _persist_chat_turn(
                db,
                user_id=user.user_id,
                session_id=request.session_id,
                user_prompt=user_prompt,
                assistant_content=assistant_content,
            )

            await emit_trace(
                TraceItem(
                    phase="Reflection",
                    title="直接返回调休结果",
                    detail="已直接基于校历 overrides 返回调休/补课安排。",
                    status="done",
                    timestamp=datetime.now(timezone.utc),
                )
            )

            events = [
                ScheduleEvent(
                    event_id=f"adjustment_{idx}",
                    title="调休补课",
                    time=str(row.get("to_date", "")),
                    source="校历",
                    detail=str(row.get("summary", "")),
                )
                for idx, row in enumerate(move_rules if isinstance(move_rules, list) else [], start=1)
            ]

            return AgentResponse(
                session_id=request.session_id,
                assistant_message=AssistantMessage(
                    role="assistant",
                    content=assistant_content,
                    timestamp=datetime.now(timezone.utc),
                ),
                trace=traces,
                route="scheduler",
                ui_payload=UIPayload(
                    schedule=ScheduleData(events=events, conflicts=[]),
                ),
                hitl_request=None,
                error=None,
            )

    if _is_conflict_query(user_prompt):
        cas_account = (user.cas_account or "").strip()
        cas_password = decrypt(user.cas_password_encrypted) if user.cas_password_encrypted else None
        if not cas_account or not cas_password:
            return None

        raw_date = _extract_explicit_date(user_prompt)
        time_range = _extract_time_range(user_prompt)
        if not raw_date or not time_range:
            return None

        week1 = await scheduler_tools._get_week1_monday()
        target_dt = scheduler_tools._parse_target_date(raw_date, fallback_year=week1.year)
        if target_dt is None:
            return None

        await emit_trace(
            TraceItem(
                phase="Tool Use",
                title="检测课程时间冲突",
                detail=f"检测 {target_dt.date().isoformat()} {time_range[0].strftime('%H:%M')}-{time_range[1].strftime('%H:%M')} 与课表是否重叠。",
                status="running",
                timestamp=datetime.now(timezone.utc),
            )
        )

        try:
            conflict_result = await scheduler_tools.schedule_service.query_effective_schedule_conflicts(
                cas_account,
                cas_password,
                target_dt.date(),
                time_range[0],
                time_range[1],
            )
        except Exception:
            conflict_result = None

        if conflict_result is not None:
            if conflict_result.conflicting_courses:
                lines = [
                    f"会存在时间冲突。教学日说明：{conflict_result.resolution.reason}",
                    "",
                    "与以下课程重叠：",
                ]
                for course in conflict_result.conflicting_courses:
                    lines.extend(
                        [
                            f"- {course.start_at.strftime('%H:%M')}-{course.end_at.strftime('%H:%M')} {course.notes or course.course_id}",
                            f"  地点：{course.location or '未提供'}",
                            f"  教师：{course.instructor or '未提供'}",
                        ]
                    )
            else:
                lines = [
                    f"不会与课表产生时间冲突。教学日说明：{conflict_result.resolution.reason}",
                    "",
                    f"活动时间：{conflict_result.activity_start.strftime('%H:%M')}-{conflict_result.activity_end.strftime('%H:%M')}",
                ]
            assistant_content = "\n".join(lines)

            await _persist_chat_turn(
                db,
                user_id=user.user_id,
                session_id=request.session_id,
                user_prompt=user_prompt,
                assistant_content=assistant_content,
            )

            await emit_trace(
                TraceItem(
                    phase="Reflection",
                    title="直接返回冲突检测结果",
                    detail="已基于教学日与有效课程进行确定性冲突判断。",
                    status="done",
                    timestamp=datetime.now(timezone.utc),
                )
            )

            events = [
                ScheduleEvent(
                    event_id=f"conflict_{idx}",
                    title=course.notes or course.course_id,
                    time=f"{target_dt.date().isoformat()} {course.start_at.strftime('%H:%M')}-{course.end_at.strftime('%H:%M')}",
                    source="教务系统",
                    detail=f"地点：{course.location or '未提供'}；教师：{course.instructor or '未提供'}",
                )
                for idx, course in enumerate(conflict_result.conflicting_courses, start=1)
            ]

            return AgentResponse(
                session_id=request.session_id,
                assistant_message=AssistantMessage(
                    role="assistant",
                    content=assistant_content,
                    timestamp=datetime.now(timezone.utc),
                ),
                trace=traces,
                route="scheduler",
                ui_payload=UIPayload(
                    schedule=ScheduleData(events=events, conflicts=[]),
                ),
                hitl_request=None,
                error=None,
            )

    if not _is_specific_schedule_query(user_prompt):
        return None

    cas_account = (user.cas_account or "").strip()
    cas_password = decrypt(user.cas_password_encrypted) if user.cas_password_encrypted else None
    if not cas_account or not cas_password:
        return None

    raw_date = _extract_explicit_date(user_prompt)
    if not raw_date:
        return None

    week1 = await scheduler_tools._get_week1_monday()
    target_dt = scheduler_tools._parse_target_date(raw_date, fallback_year=week1.year)
    if target_dt is None:
        return None

    await emit_trace(
        TraceItem(
            phase="Tool Use",
            title="按具体日期查询课表",
            detail=f"检测到具体日期课表问题，直接查询 {target_dt.date().isoformat()} 的课程安排。",
            status="running",
            timestamp=datetime.now(timezone.utc),
        )
    )

    try:
        effective_day = await scheduler_tools.schedule_service.query_effective_schedule_for_date(
            cas_account,
            cas_password,
            target_dt.date(),
        )
    except PermissionError:
        effective_day = None
    except ConnectionError:
        effective_day = None
    except Exception:
        effective_day = None

    if effective_day is None:
        return None

    target_iso = target_dt.date().isoformat()
    courses = [
        scheduler_tools._serialize_occurrence(course, week1=week1)
        for course in effective_day.courses
    ]
    courses.sort(key=lambda x: (str(x.get("start_time", "")), str(x.get("course", ""))))

    wants_first_class = ("第一节" in user_prompt) or ("第1节" in user_prompt) or ("first class" in user_prompt.lower())

    if not courses:
        assistant_content = f"{target_iso} 当天没有查询到课程安排。"
    elif wants_first_class:
        first = courses[0]
        assistant_content = (
            f"{target_iso} 当天第一节课如下：\n\n"
            f"- 课程名称：{first.get('course', '')}\n"
            f"- 上课时间：{first.get('start_time', '')}-{first.get('end_time', '')}\n"
            f"- 上课地点：{first.get('location', '') or '未提供'}\n"
            f"- 授课教师：{first.get('instructor', '') or '未提供'}\n"
            f"- 教学日说明：{effective_day.resolution.reason}"
        )
    else:
        lines = [f"{target_iso} 当天的课程安排如下：", ""]
        lines.append(f"教学日说明：{effective_day.resolution.reason}")
        lines.append("")
        for row in courses:
            lines.extend(
                [
                    f"- {row.get('start_time', '')}-{row.get('end_time', '')} {row.get('course', '')}",
                    f"  地点：{row.get('location', '') or '未提供'}",
                    f"  教师：{row.get('instructor', '') or '未提供'}",
                ]
            )
        assistant_content = "\n".join(lines)

    await _persist_chat_turn(
        db,
        user_id=user.user_id,
        session_id=request.session_id,
        user_prompt=user_prompt,
        assistant_content=assistant_content,
    )

    await emit_trace(
        TraceItem(
            phase="Reflection",
            title="直接返回日期课表结果",
            detail=f"无需依赖模型从整学期课表中推理，已按日期 {target_iso} 确定性返回。",
            status="done",
            timestamp=datetime.now(timezone.utc),
        )
    )

    events = [
        ScheduleEvent(
            event_id=f"{target_iso}_{idx}",
            title=str(row.get("course", "")),
            time=f"{target_iso} {row.get('start_time', '')}-{row.get('end_time', '')}",
            source="教务系统",
            detail=f"地点：{row.get('location', '') or '未提供'}；教师：{row.get('instructor', '') or '未提供'}",
        )
        for idx, row in enumerate(courses, start=1)
    ]

    return AgentResponse(
        session_id=request.session_id,
        assistant_message=AssistantMessage(
            role="assistant",
            content=assistant_content,
            timestamp=datetime.now(timezone.utc),
        ),
        trace=traces,
        route="scheduler",
        ui_payload=UIPayload(
            schedule=ScheduleData(events=events, conflicts=[]),
        ),
        hitl_request=None,
        error=None,
    )
