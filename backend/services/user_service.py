"""
backend/services/user_service.py
用户信息管理业务逻辑。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.postgres import User
from backend.schemas.user import UpdateCredentialsRequest, UpdateProfileRequest, UserPreferences, UserProfile
from backend.utils.crypto import encrypt


def to_profile(user: User) -> UserProfile:
    """
    将 User ORM 对象转换为 UserProfile schema，不含任何敏感字段。

    Args:
        user: User ORM 对象

    Returns:
        UserProfile
    """
    # TODO:
    # prefs = UserPreferences(**user.preferences) if user.preferences else UserPreferences()
    # return UserProfile(user_id=str(user.user_id), display_name=user.display_name,
    #                    major=user.major, preferences=prefs)
    raise NotImplementedError


async def update_profile(
    db: AsyncSession,
    user: User,
    body: UpdateProfileRequest,
) -> UserProfile:
    """
    更新用户 display_name、major、preferences 等非敏感字段。
    body 中为 None 的字段不修改。

    Returns:
        更新后的 UserProfile
    """
    # TODO:
    # if body.display_name: user.display_name = body.display_name
    # if body.major: user.major = body.major
    # if body.preferences: user.preferences = body.preferences.model_dump()
    # await db.commit(); await db.refresh(user)
    # return to_profile(user)
    raise NotImplementedError


async def update_credentials(
    db: AsyncSession,
    user: User,
    body: UpdateCredentialsRequest,
) -> None:
    """
    更新 CAS 账号/密码 或 LLM API Key。
    明文值在写入前通过 utils/crypto.encrypt 加密。
    body 中为 None 的字段不修改。
    """
    # TODO:
    # if body.cas_account is not None: user.cas_account = body.cas_account
    # if body.cas_password is not None: user.cas_password_encrypted = encrypt(body.cas_password)
    # if body.llm_api_key is not None: user.llm_api_key_encrypted = encrypt(body.llm_api_key)
    # await db.commit()
    raise NotImplementedError
