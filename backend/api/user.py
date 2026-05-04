"""
backend/api/user.py
用户信息路由：获取/更新 profile、更新敏感凭据。
所有路由需要 JWT 认证（通过 get_current_user dependency）。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.postgres import get_db, User
from backend.schemas.user import (
    UpdateCredentialsRequest,
    UpdateProfileRequest,
    UserProfile,
)
from backend.services import user_service
from backend.api.deps import get_current_user

router = APIRouter(prefix="/api/user", tags=["user"])


@router.get("/profile", response_model=UserProfile)
async def get_profile(
    current_user: User = Depends(get_current_user),
) -> UserProfile:
    """
    获取当前用户的 profile（用于前端用户卡片）。
    不含任何敏感字段（CAS 密码、API Key 等）。
    """
    return user_service.to_profile(current_user)


@router.put("/profile", response_model=UserProfile)
async def update_profile(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    """
    更新 display_name、major、preferences 等非敏感字段。
    传 null 的字段保持不变。
    """
    return await user_service.update_profile(db, current_user, body)


@router.put("/credentials", status_code=204)
async def update_credentials(
    body: UpdateCredentialsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    更新 CAS 账号/密码 或 DeepSeek API Key。
    所有值在写入前通过 utils/crypto.py Fernet 加密。
    传 null 的字段保持不变。
    """
    await user_service.update_credentials(db, current_user, body)
