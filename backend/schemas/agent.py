"""
backend/schemas/agent.py
Agent 交互的核心请求/响应 schema，是前后端最主要的数据契约。

设计原则：
  - 前端无需指定使用哪个工具，由 Agent 根据消息内容自行路由
  - HITL reply 复用同一个 AgentRequest，通过 hitl_reply 字段区分
  - 所有可空字段返回时必须显式给 null，不能缺字段（前端依赖完整结构）
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ── 枚举常量 ──────────────────────────────────────────────────────────────────

RouteType = Literal["chat", "scheduler", "encyclopedia", "os_automation"]
TraceStatus = Literal["pending", "running", "done", "error"]
TracePhase = Literal["Observation", "Reasoning", "Tool Use", "Reflection"]
RiskLevel = Literal["low", "medium", "high"]


# ── 子结构 ────────────────────────────────────────────────────────────────────

class AttachmentRef(BaseModel):
    """单次请求中引用的已上传文件（不是 multipart，文件已在 /materials/upload 上传）。"""
    file_id: str
    file_name: str
    file_type: str


class HITLReply(BaseModel):
    """用户对 HITL 弹窗的审批结果。"""
    request_id: str
    approved: bool


class TraceItem(BaseModel):
    """Agent 思维链中的单个步骤，展示在 Thought Trace 面板。"""
    phase: TracePhase
    title: str
    detail: str
    status: TraceStatus
    timestamp: datetime


class AssistantMessage(BaseModel):
    """主聊天区显示的 Agent 回复消息。"""
    role: Literal["assistant"] = "assistant"
    content: str
    timestamp: datetime


class ChatMessage(BaseModel):
    """历史消息记录（含 user/assistant 双方）。"""
    message_id: str
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime


class ScheduleEvent(BaseModel):
    event_id: str
    title: str
    time: str       # ISO 8601 datetime string 或人类可读格式，如 "Mon 19:00-20:30"
    source: str     # "Blackboard" | "教务系统" | "Local TODO"
    detail: str


class ScheduleConflict(BaseModel):
    title: str
    detail: str


class ScheduleData(BaseModel):
    events: list[ScheduleEvent]
    conflicts: list[ScheduleConflict]


class EncyclopediaResult(BaseModel):
    query: str
    answer_markdown: str      # Markdown 格式，前端直接渲染
    citations: list[str]      # 来源路径，如 "Student Handbook / Degree Requirements"


class UIPayload(BaseModel):
    """
    结构化展示数据，与 route 对应。
    无数据的字段必须返回 null（不能缺字段）。
    """
    schedule: ScheduleData | None = None
    encyclopedia: EncyclopediaResult | None = None


class HITLRequest(BaseModel):
    """
    Agent 检测到高风险操作时返回此结构，前端展示授权弹窗。
    后端同时在内存 HITLManager 中保存对应的挂起状态。
    """
    request_id: str = Field(..., description="全局唯一，格式建议 'hitl_{session_id}_{timestamp}'")
    action: str = Field(..., description="操作的自然语言描述，直接展示给用户")
    risk: RiskLevel
    reason: str = Field(..., description="为什么这个操作需要审批")
    payload: list[str] = Field(..., description="具体将要执行的子操作列表，展示在弹窗详情中")


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False


# ── 主请求/响应 ───────────────────────────────────────────────────────────────

class AgentRequest(BaseModel):
    """
    POST /api/agent/run 的请求体。
    普通对话：填 message，hitl_reply=null
    HITL 审批：message 可为空字符串，填 hitl_reply
    """
    user_id: str
    session_id: str = Field(..., description="由前端维护，格式建议 'sess_{timestamp}_{random}'")
    message: str = Field(..., description="用户自然语言输入；HITL 审批时可为空字符串")
    attachments: list[AttachmentRef] = Field(default_factory=list)
    hitl_reply: HITLReply | None = None


class AgentResponse(BaseModel):
    """
    POST /api/agent/run 的响应体。
    所有可空字段必须显式返回，不允许缺字段。
    """
    session_id: str
    assistant_message: AssistantMessage
    trace: list[TraceItem]
    route: RouteType
    ui_payload: UIPayload
    hitl_request: HITLRequest | None = None
    error: ErrorDetail | None = None


class SessionSummary(BaseModel):
    """GET /api/agent/sessions 的列表项。"""
    session_id: str
    title: str            # 会话标题，优先取首条用户消息
    preview: str          # 最近一条用户消息或 assistant 回答的截断文本
    updated_at: datetime


class SessionDetail(BaseModel):
    """GET /api/agent/sessions/{session_id} 的响应体。"""
    session_id: str
    title: str
    updated_at: datetime
    messages: list[ChatMessage]
