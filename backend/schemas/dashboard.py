"""
backend/schemas/dashboard.py
Dashboard bootstrap 响应 schema。
"""

from pydantic import BaseModel

from backend.schemas.agent import ChatMessage, ScheduleData
from backend.schemas.material import MaterialInfo
from backend.schemas.user import UserProfile


class BootstrapResponse(BaseModel):
    """
    GET /api/dashboard/bootstrap 的响应体。
    一次性返回主界面所需的全部初始化数据。
    缺失数据返回空列表/空对象，不允许缺字段。
    """
    user_profile: UserProfile
    chat_history: list[ChatMessage]       # 最近 N 条历史消息（N 由后端决定，建议 50）
    materials: list[MaterialInfo]
    local_schedule: ScheduleData          # 上次缓存的日程数据；无数据时返回 events=[], conflicts=[]
