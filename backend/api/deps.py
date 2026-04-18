"""
backend/api/deps.py
FastAPI 公共依赖项（Dependencies）。
所有需要认证的路由通过 get_current_user 验证 JWT。
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.postgres import User, get_db
from backend.services import auth_service

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    从 Authorization: Bearer <token> 中提取并验证 JWT。
    验证通过后从数据库加载并返回 User ORM 对象。

    Raises:
        401: token 缺失、格式错误或已过期
        404: token 合法但用户已被删除
    """
    try:
        user_id = auth_service.decode_token(credentials.credentials)
    except (JWTError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
