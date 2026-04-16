"""
backend/schemas/auth.py
认证相关的请求/响应 schema。
"""

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, description="登录用户名，全局唯一")
    password: str = Field(..., min_length=6, description="明文密码，后端负责 bcrypt 哈希")
    display_name: str = Field(..., max_length=128, description="界面显示名")
    major: str = Field(..., max_length=128, description="专业，例如 'Software Engineering'")


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    """登录/注册成功后返回，包含 JWT token 和基础用户信息。"""
    user_id: str
    display_name: str
    major: str
    token: str = Field(..., description="JWT Bearer token，前端后续请求放入 Authorization header")
