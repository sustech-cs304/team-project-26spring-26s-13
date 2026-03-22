"""
backend/agent/loop.py
PydanticAI Agent 主循环。
负责：上下文组装 → Agent 推理 → 工具调用 → Trace 收集 → 结果封装。

架构说明：
  - AgentDeps 将数据库 session、用户信息、LLM API Key 注入工具函数
  - 所有工具函数定义在 backend/agent/tools/ 中，通过 @agent.tool 注册
  - Trace 通过 PydanticAI 的消息流收集（ModelMessagesTypeAdapter）
  - HITL 通过工具抛出 HITLInterrupt 异常触发挂起流程
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic_ai import Agent, RunContext
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database.postgres import User
from backend.schemas.agent import (
    AgentRequest, AgentResponse, AgentResponse,
    AssistantMessage, TraceItem, UIPayload, RouteType
)
from backend.agent.hitl import HITLPendingState, hitl_manager
from backend.agent.router import determine_route
from backend.agent import tools  # 注册所有 @agent.tool（见 tools/__init__.py）


# ── Agent 依赖上下文 ───────────────────────────────────────────────────────────

@dataclass
class AgentDeps:
    """
    注入给所有工具函数的运行时依赖。
    工具通过 ctx.deps 访问这些字段，严禁工具直接持有全局状态。
    """
    db: AsyncSession
    user: User
    session_id: str
    llm_api_key: str              # 解密后的 DeepSeek API Key（工具调用外部服务时使用）
    cas_account: str | None       # 解密后的 CAS 账号（爬虫工具使用）
    cas_password: str | None      # 解密后的 CAS 密码（爬虫工具使用）


# ── PydanticAI Agent 实例 ─────────────────────────────────────────────────────

# TODO: 初始化时需要指定 model。DeepSeek 通过 OpenAI-compatible API 接入。
#       参考 PydanticAI 文档配置 OpenAIModel with base_url=settings.DEEPSEEK_BASE_URL
#       system_prompt 从 backend/agent/prompt.py 导入
agent: Agent[AgentDeps, str] = None  # type: ignore  # TODO: 替换为实际初始化


# ── HITL 异常 ─────────────────────────────────────────────────────────────────

class HITLInterrupt(Exception):
    """
    工具函数检测到高风险操作时抛出此异常，由 run_agent 捕获并转换为 HITL 响应。

    Attributes:
        pending_state: hitl_manager.create() 返回的挂起状态
        payload:       具体子操作列表（用于弹窗展示）
        reason:        需要审批的原因说明
    """
    def __init__(self, pending_state: HITLPendingState, payload: list[str], reason: str) -> None:
        self.pending_state = pending_state
        self.payload = payload
        self.reason = reason


# ── 主入口 ────────────────────────────────────────────────────────────────────

async def run_agent(
    db: AsyncSession,
    user: User,
    request: AgentRequest,
    hitl_context: HITLPendingState | None = None,
) -> AgentResponse:
    """
    执行一次完整的 Agent 推理循环，返回结构化响应。

    Args:
        db:           当前请求的数据库 Session
        user:         已认证的用户 ORM 对象
        request:      前端发来的 AgentRequest
        hitl_context: 非 None 表示这是 HITL 审批后的续跑，跳过初始路由

    Returns:
        AgentResponse，包含 assistant_message、trace、route、ui_payload 等字段

    Raises:
        RuntimeError: LLM API 调用失败且不可重试
    """
    # TODO:
    # 1. 从 user 解密 llm_api_key、cas_account、cas_password（utils/crypto.py）
    # 2. 构造 AgentDeps
    # 3. 从 DB 加载最近 N 条历史消息作为 message_history
    # 4. 调用 agent.run(request.message, deps=deps, message_history=history)
    #    - 捕获 HITLInterrupt → 构造 HITL 响应并返回
    #    - 收集 result.all_messages() 生成 trace items
    # 5. determine_route(result) 决定 route
    # 6. 从工具返回值提取 ui_payload（schedule / encyclopedia）
    # 7. 将 user message 和 assistant message 写入 chat_messages 表
    # 8. 封装并返回 AgentResponse
    raise NotImplementedError


def _build_trace(raw_messages: list) -> list[TraceItem]:
    """
    将 PydanticAI 的内部消息列表转换为前端 Thought Trace 面板所需的格式。

    Args:
        raw_messages: agent.result.all_messages() 返回的消息列表

    Returns:
        list[TraceItem]，保持时序排列
    """
    # TODO:
    # 遍历 raw_messages：
    #   - ModelRequest → phase="Observation", status="done"
    #   - ToolCallPart → phase="Tool Use", status="done"/"error"
    #   - ModelResponse → phase="Reasoning", status="done"
    raise NotImplementedError
