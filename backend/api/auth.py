"""
backend/api/auth.py
认证路由：注册、
登录、登出。


"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.postgres import get_db
from backend.schemas.auth import AuthResponse, LoginRequest, RegisterRequest
from backend.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    """
    注册新用户。
    - 检查 username 唯一性
    - bcrypt 哈希密码后写入 users 表
    - 返回 JWT token 和用户基础信息

    Raises:
        400: username 已存在
    """
    try:
        return await auth_service.register(db, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    """
    用户登录。
    - 查询 username 对应记录，验证 bcrypt 密码
    - 签发 JWT token（有效期由 settings.ACCESS_TOKEN_EXPIRE_MINUTES 控制）

    Raises:
        401: 用户名或密码错误
    """
    try:
        return await auth_service.login(db, body)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout() -> None:
    """
    登出（客户端丢弃 token 即可）。
    当前为无状态 JWT，服务端无需操作；
    后续如需 token 黑名单，在此添加 Redis 写入逻辑。
    """
    # TODO: 可选：将 token jti 加入黑名单
    return
