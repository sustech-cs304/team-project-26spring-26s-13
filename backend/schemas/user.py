"""
backend/schemas/user.py
用户信息相关的请求/响应 schema。
"""

from pydantic import BaseModel, Field


class UserPreferences(BaseModel):
    theme: str = "light"  # "light" | "dark" | "cosmic"
    language: str = "zh"  # "zh" | "en"


class UserProfile(BaseModel):
    """用于前端用户卡片展示，不含任何敏感字段。"""

    user_id: str
    display_name: str
    major: str
    preferences: UserPreferences


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(None, max_length=128)
    major: str | None = Field(None, max_length=128)
    preferences: UserPreferences | None = None


class UpdateCredentialsRequest(BaseModel):
    """
    更新 CAS 账号/密码 或 LLM API Key。
    所有字段可选，只传需要更新的字段。
    密码字段在后端写入前会调用 utils/crypto.py 加密。
    """

    cas_account: str | None = Field(None, description="南科大 CAS 统一认证账号")
    cas_password: str | None = Field(None, description="CAS 明文密码，后端加密存储")
    llm_api_key: str | None = Field(None, description="DeepSeek API Key，后端加密存储")
