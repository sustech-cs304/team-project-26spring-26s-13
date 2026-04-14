"""
backend/services/auth_service.py
认证业务逻辑：注册、登录、JWT 签发与验证。
"""

import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database.postgres import User
from backend.schemas.auth import AuthResponse, LoginRequest, RegisterRequest

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def register(db: AsyncSession, body: RegisterRequest) -> AuthResponse:
    """
    注册新用户，写入 users 表，返回 JWT token。

    Raises:
        ValueError: username 已被注册
    """
    # 1. 检查用户名唯一性
    existing = await db.scalar(select(User).where(User.username == body.username))
    if existing:
        raise ValueError("username already exists")

    # 2. 创建用户
    user = User(
        username=body.username,
        password_hash=pwd_context.hash(body.password),
        display_name=body.display_name,
        major=body.major,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # 3. 签发 token
    token = _create_token(str(user.user_id))
    return AuthResponse(
        user_id=str(user.user_id),
        display_name=user.display_name,
        major=user.major,
        token=token,
    )


async def login(db: AsyncSession, body: LoginRequest) -> AuthResponse:
    """
    用户登录，验证密码后返回 JWT token。

    Raises:
        ValueError: 用户名不存在或密码错误
    """
    user = await db.scalar(select(User).where(User.username == body.username))
    if not user or not pwd_context.verify(body.password, user.password_hash):
        raise ValueError("invalid credentials")

    token = _create_token(str(user.user_id))
    return AuthResponse(
        user_id=str(user.user_id),
        display_name=user.display_name,
        major=user.major,
        token=token,
    )


def decode_token(token: str) -> str:
    """
    解码 JWT token，返回 user_id（sub 字段）。

    Raises:
        JWTError: token 无效或已过期
    """
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    return payload["sub"]


def _create_token(user_id: str) -> str:
    """
    签发 JWT token。

    Args:
        user_id: users.user_id 的字符串形式

    Returns:
        JWT token 字符串
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
