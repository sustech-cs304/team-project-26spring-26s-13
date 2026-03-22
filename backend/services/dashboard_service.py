"""
backend/services/dashboard_service.py
Dashboard bootstrap 数据组装服务。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.postgres import ChatMessage, ChatSession, Material, User
from backend.schemas.agent import ScheduleData
from backend.schemas.dashboard import BootstrapResponse
from backend.schemas.user import UserPreferences, UserProfile
from backend.schemas.material import MaterialInfo

CHAT_HISTORY_LIMIT = 50  # bootstrap 时返回最近多少条消息


async def build_bootstrap(db: AsyncSession, user: User) -> BootstrapResponse:
    """
    组装主界面初始化所需的全部数据，一次性返回。

    Args:
        db:   数据库 Session
        user: 已认证的用户 ORM 对象

    Returns:
        BootstrapResponse，所有字段保证非 null（缺数据时返回空列表/空对象）
    """
    # TODO:
    # profile = _build_profile(user)
    # history = await _load_chat_history(db, user.user_id)
    # materials = await _load_materials(db, user.user_id)
    # schedule = ScheduleData(events=[], conflicts=[])  # 缓存版本，暂时返回空
    # return BootstrapResponse(user_profile=profile, chat_history=history,
    #                          materials=materials, local_schedule=schedule)
    raise NotImplementedError


def _build_profile(user: User) -> UserProfile:
    """将 User ORM 转换为 UserProfile schema（不含敏感字段）。"""
    # TODO
    raise NotImplementedError


async def _load_chat_history(db: AsyncSession, user_id) -> list:
    """
    加载该用户最近 CHAT_HISTORY_LIMIT 条消息（跨所有 session，按时间倒序后反转）。
    """
    # TODO:
    # 联表 ChatSession → ChatMessage，ORDER BY timestamp DESC，LIMIT 50，然后 reversed
    raise NotImplementedError


async def _load_materials(db: AsyncSession, user_id) -> list[MaterialInfo]:
    """加载用户所有教材列表，按上传时间倒序。"""
    # TODO
    raise NotImplementedError
