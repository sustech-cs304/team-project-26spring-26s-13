"""
backend/api/deps.py
FastAPI 公共依赖项（Dependencies）。
所有需要认证的路由通过 get_current_user 验证 JWT。

T--当一个用户请求受保护的接口时，它负责检查该用户是否登录（拿着合法的 JWT 令牌），
如果合法，就把该用户的信息从数据库里取出来供后续使用
"""
"""
T--HTTPBearer(): 这是 FastAPI 提供的一个安全方案工具。
它会自动在 API 文档 Swagger UI 中右上角添加一个 "Authorize" 按钮，
并要求客户端在请求头中发送 Authorization: Bearer <TOKEN>
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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
        404: token 合法但用户已被删除（极少见）
    """
    try:
        user_id = auth_service.decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user
