"""
backend/services/dashboard_service.py
Dashboard bootstrap 数据组装服务。
"""

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.postgres import (
    ChatMessage as ChatMessageORM,
    ChatSession,
    Material,
    User,
)
from backend.schemas.agent import ChatMessage as ChatMessageSchema, ScheduleData
from backend.schemas.dashboard import BootstrapResponse
from backend.schemas.user import UserPreferences, UserProfile
from backend.schemas.material import MaterialInfo


async def build_bootstrap(db: AsyncSession, user: User) -> BootstrapResponse:
    """
    组装主界面初始化所需的全部数据，一次性返回。

    Args:
        db:   数据库 Session
        user: 已认证的用户 ORM 对象

    Returns:
        BootstrapResponse，所有字段保证非 null（缺数据时返回空列表/空对象）
    """
    profile = _build_profile(user)
    active_session_id = await _load_latest_session_id(db, user.user_id)
    history = await _load_session_history(db, active_session_id)
    materials = await _load_materials(db, user.user_id)
    schedule = ScheduleData(events=[], conflicts=[])
    return BootstrapResponse(
        user_profile=profile,
        active_session_id=active_session_id,
        chat_history=history,
        materials=materials,
        local_schedule=schedule,
    )


def _build_profile(user: User) -> UserProfile:
    """将 User ORM 转换为 UserProfile schema（不含敏感字段）。"""
    prefs = (
        UserPreferences(**user.preferences) if user.preferences else UserPreferences()
    )
    return UserProfile(
        user_id=str(user.user_id),
        display_name=user.display_name,
        major=user.major,
        preferences=prefs,
    )


async def _load_latest_session_id(db: AsyncSession, user_id) -> str | None:
    stmt = (
        select(ChatSession.session_id)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _load_session_history(
    db: AsyncSession, session_id: str | None
) -> list[ChatMessageSchema]:
    """加载单个会话的完整历史消息，按时间正序返回。"""
    if not session_id:
        return []

    stmt = (
        select(ChatMessageORM)
        .where(ChatMessageORM.session_id == session_id)
        .order_by(
            ChatMessageORM.timestamp.asc(),
            case((ChatMessageORM.role == "user", 0), else_=1).asc(),
        )
    )
    rows = (await db.scalars(stmt)).all()
    return [
        ChatMessageSchema(
            message_id=str(msg.message_id),
            role=msg.role,
            content=msg.content,
            timestamp=msg.timestamp,
        )
        for msg in rows
    ]


async def _load_materials(db: AsyncSession, user_id) -> list[MaterialInfo]:
    """加载用户所有教材列表，按上传时间倒序。"""
    rows = await db.scalars(
        select(Material)
        .where(Material.user_id == user_id)
        .order_by(Material.uploaded_at.desc())
    )
    return [
        MaterialInfo(
            file_id=str(m.file_id),
            file_name=m.file_name,
            file_type=m.file_type,
            subject_type=m.subject_type,
            vectorized=m.vectorized,
            uploaded_at=m.uploaded_at,
        )
        for m in rows
    ]
