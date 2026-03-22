"""
backend/api/schedule.py
日程路由：手动触发重新爬取 Blackboard 和教务系统。
"""

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.postgres import User, get_db
from backend.schemas.agent import ScheduleData
from backend.services import schedule_service
from backend.api.deps import get_current_user

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


@router.post("/refresh", response_model=ScheduleData)
async def refresh_schedule(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScheduleData:
    """
    手动触发重新爬取 Blackboard DDL 和教务系统课表，检测冲突后返回最新日程。

    前置条件：用户已在 /api/user/credentials 填入 CAS 账号和密码。
    爬取可能较慢（5~30s），建议前端展示 loading 状态。

    Raises:
        424: CAS 登录失败（密码错误或网络不通）
        503: Blackboard/教务系统服务不可达
    """
    # TODO: return await schedule_service.refresh(db, current_user)
    raise NotImplementedError
