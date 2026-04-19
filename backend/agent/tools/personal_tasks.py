"""
backend/agent/tools/personal_tasks.py
个人事务管理工具：Agent 从对话中提取事务信息后调用，存入 PostgreSQL personal_tasks 表。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from pydantic_ai import RunContext

from backend.agent.core import AgentDeps, agent
from backend.services import task_service


def _parse_dt(s: str) -> datetime:
    """
    将字符串解析为带时区的 datetime。
    支持格式：
      - ISO 8601 含时区，如 "2026-04-15T14:00:00+08:00"
      - ISO 8601 不含时区，如 "2026-04-15T14:00:00"（按 UTC+8 本地时间处理）
      - 仅日期，如 "2026-04-15"（当天 00:00 CST）
    """
    from zoneinfo import ZoneInfo
    cst = ZoneInfo("Asia/Shanghai")
    s = s.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=cst)
            return dt
        except ValueError:
            continue
    raise ValueError(f"无法解析时间字符串：{s!r}")


@agent.tool
async def save_personal_task(
    ctx: RunContext[AgentDeps],
    title: str,
    start_time: str,
    end_time: str = "",
    description: str = "",
    location: str = "",
) -> str:
    """
    将用户在对话中提到的个人事务存入数据库。
    当用户说"明天下午三点有组会""周五要交作业""下周一去图书馆还书"等，
    提取关键信息后调用此工具。

    Args:
        title:       事务标题，简短描述，如"组会""提交作业""图书馆还书"
        start_time:  开始时间，ISO 8601 格式字符串，如 "2026-04-15T15:00:00"
        end_time:    结束时间（可选），ISO 8601 格式字符串；不确定则传空字符串
        description: 补充说明（可选），如"算法课期末作业"
        location:    地点（可选），如"理学院 203"

    Returns:
        成功："SAVED:{task_id}"
        失败："ERROR:{原因}"
    """
    try:
        start_dt = _parse_dt(start_time)
    except ValueError as e:
        return f"ERROR:无法解析 start_time：{e}"

    end_dt = None
    if end_time.strip():
        try:
            end_dt = _parse_dt(end_time)
        except ValueError as e:
            return f"ERROR:无法解析 end_time：{e}"

    try:
        task = await task_service.add_task(
            db=ctx.deps.db,
            user_id=ctx.deps.user.user_id,
            title=title,
            start_time=start_dt,
            description=description or None,
            end_time=end_dt,
            location=location or None,
        )
        return f"SAVED:{task.task_id}"
    except Exception as e:
        return f"ERROR:{e}"


@agent.tool
async def list_personal_tasks(
    ctx: RunContext[AgentDeps],
    from_time: str = "",
    to_time: str = "",
) -> str:
    """
    查询用户的待办事务列表，可按时间范围过滤。
    当用户问"我这周有什么安排""明天有什么事"时调用。

    Args:
        from_time: 查询起始时间（ISO 8601），空字符串表示不限
        to_time:   查询截止时间（ISO 8601），空字符串表示不限

    Returns:
        JSON 字符串，格式：
        [
          {
            "task_id": str,
            "title": str,
            "start_time": str,
            "end_time": str | null,
            "location": str | null,
            "description": str | null
          }
        ]
        若无事务返回空列表 "[]"。
    """
    from_dt = None
    to_dt = None
    if from_time.strip():
        try:
            from_dt = _parse_dt(from_time)
        except ValueError:
            pass
    if to_time.strip():
        try:
            to_dt = _parse_dt(to_time)
        except ValueError:
            pass

    try:
        tasks = await task_service.list_tasks(
            db=ctx.deps.db,
            user_id=ctx.deps.user.user_id,
            from_time=from_dt,
            to_time=to_dt,
        )
        return json.dumps(
            [
                {
                    "task_id": str(t.task_id),
                    "title": t.title,
                    "start_time": t.start_time.isoformat(),
                    "end_time": t.end_time.isoformat() if t.end_time else None,
                    "location": t.location,
                    "description": t.description,
                }
                for t in tasks
            ],
            ensure_ascii=False,
        )
    except Exception as e:
        return f"ERROR:{e}"


@agent.tool
async def mark_task_done(
    ctx: RunContext[AgentDeps],
    task_id: str,
) -> str:
    """
    将某条事务标记为已完成。
    当用户说"组会结束了""作业交完了"时，先用 list_personal_tasks 找到对应 task_id，
    再调用此工具。

    Args:
        task_id: 事务的 UUID 字符串

    Returns:
        "OK" 或 "ERROR:NOT_FOUND"
    """
    import uuid as _uuid
    try:
        tid = _uuid.UUID(task_id)
    except ValueError:
        return "ERROR:task_id 格式无效"

    try:
        found = await task_service.mark_done(
            db=ctx.deps.db,
            user_id=ctx.deps.user.user_id,
            task_id=tid,
        )
        return "OK" if found else "ERROR:NOT_FOUND"
    except Exception as e:
        return f"ERROR:{e}"
