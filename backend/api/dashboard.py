"""
backend/api/dashboard.py
Dashboard 初始化路由。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.postgres import User, get_db
from backend.schemas.dashboard import BootstrapResponse
from backend.services import dashboard_service
from backend.api.deps import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/bootstrap", response_model=BootstrapResponse)
async def bootstrap(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BootstrapResponse:
    """
    前端进入主界面后调用一次，拉取所有初始化数据：
    - user_profile：用户基础信息
    - chat_history：最近 50 条历史消息
    - materials：用户上传的教材列表
    - local_schedule：上次缓存的日程（无则返回空列表）

    缺失数据时字段返回空列表/空对象，不允许 null 或缺字段。
    """
    # TODO: return await dashboard_service.build_bootstrap(db, current_user)
    raise NotImplementedError
