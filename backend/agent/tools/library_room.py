"""
backend/agent/tools/library_room.py
图书馆讨论间查询工具：根据地点、时间、容量要求查询 SUSTech 图书馆讨论间空闲情况。
"""

from __future__ import annotations

import json

from pydantic_ai import RunContext

from backend.agent.core import AgentDeps, agent
from backend.agent.tools.base import safe_tool
from backend.services.library_room_service import (
    LibraryRoomQueryError,
    query_available_rooms,
)


@agent.tool
@safe_tool
async def query_library_rooms(
    ctx: RunContext[AgentDeps],
    location: str,
    time_slot: str,
    capacity: int = 0,
) -> str:
    """
    查询南方科技大学图书馆讨论间的空闲情况。
    根据用户提供的地点、时间段和容量要求，返回符合要求的讨论间列表。

    Args:
        location:   期望的地点，如 "图书馆一楼"、"图书馆二楼"、""（空字符串表示不限地点）
        time_slot:  期望的时间段，如 "2026-05-10 14:00-16:00"、"明天下午"、""（空字符串表示不限时间）
        capacity:   期望的容量（几人间），如 4、6、8；0 表示不限容量

    Returns:
        JSON 字符串，格式：
        {
          "query_location": str,
          "query_time": str,
          "query_capacity": int | null,
          "has_available": bool,
          "rooms": [
            {
              "room_id": str,
              "room_name": str,
              "location": str,
              "capacity": int,
              "time_slots": ["08:00-10:00", "14:00-16:00"]
            }
          ]
        }
    """
    cas_account = (ctx.deps.cas_account or "").strip()
    cas_password = ctx.deps.cas_password or ""
    if not cas_account or not cas_password:
        return "ERROR:CAS_LOGIN_FAILED"

    try:
        normalized_query, rooms = await query_available_rooms(
            cas_account,
            cas_password,
            location=location,
            time_slot=time_slot,
            capacity=capacity,
        )
    except PermissionError:
        return "ERROR:CAS_LOGIN_FAILED"
    except LibraryRoomQueryError as exc:
        message = str(exc)
        return message if message.startswith("ERROR:") else f"ERROR:{message}"
    except Exception as exc:
        return f"ERROR:LIBRARY_ROOM_QUERY_FAILED:{type(exc).__name__}"

    query_time = normalized_query.target_date.isoformat()
    if normalized_query.start_time and normalized_query.end_time:
        query_time = (
            f"{query_time} {normalized_query.start_time}-{normalized_query.end_time}"
        )

    result = {
        "query_location": location,
        "query_time": query_time,
        "query_capacity": capacity if capacity > 0 else None,
        "has_available": bool(rooms),
        "rooms": [
            {
                "room_id": room.room_id,
                "room_name": room.room_name,
                "location": room.location,
                "capacity": room.capacity,
                "time_slots": room.time_slots,
            }
            for room in rooms
        ],
    }
    return json.dumps(result, ensure_ascii=False)


@agent.tool
async def book_library_room(
    ctx: RunContext[AgentDeps],
    room_id: str,
    time_slot: str,
) -> str:
    """
    预约图书馆讨论间。
    此操作涉及资源锁定，必须通过 HITL 审批后才能执行。

    Args:
        room_id:   讨论间唯一标识（从 query_library_rooms 结果中获取）
        time_slot: 预约时间段，如 "2026-05-10 14:00-16:00"

    Returns:
        成功："BOOKED:{booking_id}"
        失败："ERROR:{原因}"
    """
    # ── Stub 实现 ──
    # TODO: 对接图书馆预约系统 API，并在执行前通过 HITL 审批
    return "ERROR: 图书馆讨论间预约功能尚未对接实际系统，请稍后再试"
