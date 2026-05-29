"""
backend/services/task_service.py
个人事务的增删查业务逻辑，供 Agent 工具层调用。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.postgres import PersonalTask


async def add_task(
    db: AsyncSession,
    user_id: uuid.UUID,
    title: str,
    start_time: datetime,
    *,
    description: str | None = None,
    end_time: datetime | None = None,
    location: str | None = None,
) -> PersonalTask:
    """新增一条个人事务，返回持久化后的对象。"""
    task = PersonalTask(
        task_id=uuid.uuid4(),
        user_id=user_id,
        title=title,
        description=description,
        start_time=start_time,
        end_time=end_time,
        location=location,
        is_done=False,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def list_tasks(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    include_done: bool = False,
) -> list[PersonalTask]:
    """查询用户的事务列表，支持时间范围过滤和已完成过滤。"""
    conditions = [PersonalTask.user_id == user_id]
    if not include_done:
        conditions.append(PersonalTask.is_done == False)  # noqa: E712
    if from_time:
        conditions.append(PersonalTask.start_time >= from_time)
    if to_time:
        conditions.append(PersonalTask.start_time <= to_time)

    stmt = (
        select(PersonalTask)
        .where(and_(*conditions))
        .order_by(PersonalTask.start_time.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def mark_done(
    db: AsyncSession,
    user_id: uuid.UUID,
    task_id: uuid.UUID,
) -> bool:
    """将指定事务标记为已完成，返回是否找到并更新。"""
    stmt = select(PersonalTask).where(
        PersonalTask.task_id == task_id,
        PersonalTask.user_id == user_id,
    )
    task = (await db.execute(stmt)).scalar_one_or_none()
    if task is None:
        return False
    task.is_done = True
    await db.commit()
    return True


async def delete_task(
    db: AsyncSession,
    user_id: uuid.UUID,
    task_id: uuid.UUID,
) -> bool:
    """删除一条事务，返回是否找到并删除。"""
    stmt = select(PersonalTask).where(
        PersonalTask.task_id == task_id,
        PersonalTask.user_id == user_id,
    )
    task = (await db.execute(stmt)).scalar_one_or_none()
    if task is None:
        return False
    await db.delete(task)
    await db.commit()
    return True


async def upsert_course_tasks(
    db: AsyncSession,
    user_id: uuid.UUID,
    tasks: list[dict],
) -> int:
    existing_keys: set[tuple[str, datetime]] = set()
    stmt = select(PersonalTask.title, PersonalTask.start_time).where(
        PersonalTask.user_id == user_id,
        PersonalTask.source == "course_schedule",
    )
    result = await db.execute(stmt)
    for row in result:
        existing_keys.add((row[0], row[1]))

    added = 0
    for t in tasks:
        key = (t["title"], t["start_time"])
        if key in existing_keys:
            continue
        task = PersonalTask(
            task_id=uuid.uuid4(),
            user_id=user_id,
            title=t["title"],
            start_time=t["start_time"],
            end_time=t.get("end_time"),
            location=t.get("location"),
            description=t.get("description"),
            source="course_schedule",
            is_done=False,
        )
        db.add(task)
        existing_keys.add(key)
        added += 1

    if added:
        await db.flush()
    return added
