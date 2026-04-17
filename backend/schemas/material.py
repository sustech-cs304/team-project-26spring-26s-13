"""
backend/schemas/material.py
教材/文件相关的请求/响应 schema。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

SubjectType = Literal[
    "cs", "electronics", "materials", "math", "physics",
    "chemistry", "biology", "geography", "philosophy", "history",
    "literature", "politics", "finance", "statistics", "ocean",
    "economics", "law", "management", "medicine", "policy", "other"
]


class MaterialInfo(BaseModel):
    """文件列表项，用于前端侧边栏材料列表。"""
    file_id: str
    file_name: str
    file_type: str            # MIME type, e.g. "application/pdf"
    subject_type: SubjectType # LLM 分类结果
    vectorized: bool          # 向量化是否完成
    uploaded_at: datetime
