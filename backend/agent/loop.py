"""
backend/agent/loop.py
PydanticAI Agent 主循环。
负责：上下文组装 → Agent 推理 → 工具调用 → Observation (Trace 收集) → 结果封装。
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone


from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database.postgres import User, ChatMessage, ChatSession
from backend.utils.crypto import decrypt
from backend.schemas.agent import (
    AgentRequest,
    AgentResponse,
    AssistantMessage,
    ErrorDetail,
    RiskLevel,
    TraceItem,
    UIPayload,
)
from backend.agent.hitl import HITLPendingState, hitl_manager
from backend.agent.core import AgentDeps, agent, FinalResponse
from backend.agent.prompt import build_hitl_continuation_prompt
from backend.agent.router import determine_route
from backend.agent.shortcuts.schedule import try_handle_specific_schedule_query
from backend.agent.tool_policy import normalize_route_for_prompt
from backend.agent.validators import ResponseValidationContext, detect_alignment_issue
import traceback


TraceEmitter = Callable[[TraceItem], Awaitable[None] | None]


# ── HITL 异常 ─────────────────────────────────────────────────────────────────

class HITLInterrupt(Exception):
    """
    工具函数检测到高风险操作时抛出此异常，由 run_agent 捕获。
    """

    def __init__(self, pending_state: HITLPendingState, payload: list[str], reason: str) -> None:
        super().__init__(reason)
        self.pending_state = pending_state
        self.payload = payload
        self.reason = reason


def wait_for_user_interrupt(
    *,
    session_id: str,
    action: str,
    risk: RiskLevel,
    payload: list[str],
    reason: str,
) -> None:
    """
    供工具层调用的标准化 “Wait-for-User” 中断钩子。
    工具一旦进入高风险路径，应调用本函数抛出 HITLInterrupt。
    """
    request_id = f"hitl_{session_id}_{int(time.time() * 1000)}"
    pending_state = hitl_manager.create(
        request_id=request_id,
        session_id=session_id,
        action=action,
        risk=risk,
    )
    raise HITLInterrupt(pending_state=pending_state, payload=payload, reason=reason)


# ── 主入口 ────────────────────────────────────────────────────────────────────

async def run_agent(
    db: AsyncSession,
    user: User,
    request: AgentRequest,
    hitl_context: HITLPendingState | None = None,
    trace_emitter: TraceEmitter | None = None,
) -> AgentResponse:
    """
    执行一次完整的 Agent 推理循环，返回结构化响应。
    """
    traces: list[TraceItem] = []

    async def emit_trace(item: TraceItem) -> None:
        traces.append(item)
        if trace_emitter is None:
            return
        maybe_awaitable = trace_emitter(item)
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable

    await emit_trace(
        TraceItem(
            phase="Observation",
            title="读取用户目标",
            detail="Agent 收到请求，开始构建上下文与依赖。",
            status="running",
            timestamp=datetime.now(timezone.utc),
        )
    )

    llm_api_key = (
        decrypt(user.llm_api_key_encrypted)
        if user.llm_api_key_encrypted
        else settings.DEEPSEEK_API_KEY
    )
    llm_api_key = (llm_api_key or "").strip()
    cas_account = user.cas_account
    cas_password = decrypt(user.cas_password_encrypted) if user.cas_password_encrypted else None

    if not llm_api_key:
        await emit_trace(
            TraceItem(
                phase="Reflection",
                title="缺少 LLM API Key",
                detail="当前用户未保存个人 API Key，且服务端也未配置默认的 DEEPSEEK_API_KEY。",
                status="error",
                timestamp=datetime.now(timezone.utc),
            )
        )
        return AgentResponse(
            session_id=request.session_id,
            assistant_message=AssistantMessage(
                role="assistant",
                content="当前未配置 LLM API Key。请先在设置中保存个人 API Key，或在服务端 .env 中配置 DEEPSEEK_API_KEY。",
                timestamp=datetime.now(timezone.utc),
            ),
            trace=traces,
            route="chat",
            ui_payload=UIPayload(),
            hitl_request=None,
            error=ErrorDetail(
                code="missing_llm_api_key",
                message="Missing LLM API key. Save a user API key or configure DEEPSEEK_API_KEY in .env.",
                retryable=False,
            ),
        )

    deps = AgentDeps(
        db=db,
        user=user,
        session_id=request.session_id,
        llm_api_key=llm_api_key,
        cas_account=cas_account,
        cas_password=cas_password,
        trace_log=[],
    )

    user_prompt = request.message
    if hitl_context and request.hitl_reply is not None:
        user_prompt = build_hitl_continuation_prompt(hitl_context.action, request.hitl_reply.approved)

    deterministic_schedule_response = await try_handle_specific_schedule_query(
        db,
        user,
        request,
        user_prompt=user_prompt,
        emit_trace=emit_trace,
        traces=traces,
    )
    if deterministic_schedule_response is not None:
        return deterministic_schedule_response

    # 读取最近历史消息并注入 message_history，避免多轮对话丢失上下文。
    history_stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == request.session_id)
        .order_by(
            ChatMessage.timestamp.asc(),
            case((ChatMessage.role == "user", 0), else_=1).asc(),
        )
        .limit(10)
    )
    history_messages = (await db.execute(history_stmt)).scalars().all()
    message_history = _build_message_history(history_messages)

    try:
        provider = OpenAIProvider(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=llm_api_key,
        )
        dynamic_model = OpenAIModel(
            model_name=settings.DEEPSEEK_MODEL,
            provider=provider,
        )

        await emit_trace(
            TraceItem(
                phase="Reasoning",
                title="规划工具调用",
                detail="LLM 正在执行 goal-to-tool 推理并决定是否调用工具。",
                status="running",
                timestamp=datetime.now(timezone.utc),
            )
        )

        print("=== agent.run start ===")
        print(f"model={settings.DEEPSEEK_MODEL}")
        print(f"base_url={settings.DEEPSEEK_BASE_URL}")
        print(f"has_llm_api_key={bool(llm_api_key)}")
        print(f"user_prompt={user_prompt!r}")

        result = await asyncio.wait_for(
            agent.run(
                user_prompt,
                deps=deps,
                model=dynamic_model,
                message_history=message_history,
            ),
            timeout=settings.AGENT_RUN_TIMEOUT_SECONDS,
        )

        print("=== agent.run success ===")
        print(f"result_type={type(result)}")
        print(f"has_data={hasattr(result, 'data')}")
        print("=== after agent.run ===")
        final_data: FinalResponse = getattr(result, "data", None) or result.output
        print(f"final_data_type={type(final_data)}")
        print(f"final_data={final_data!r}")
        raw_messages = result.all_messages()
        print("=== got raw_messages ===")
        print(f"raw_messages_count={len(raw_messages)}")

        for item in _build_trace(raw_messages):
            await emit_trace(item)
        print("=== trace built ===")

        tool_names = _extract_tool_names(raw_messages)
        print(f"tool_names={tool_names}")
        route_by_tools = determine_route(tool_names)
        chosen_route = route_by_tools if tool_names else final_data.route
        chosen_route = normalize_route_for_prompt(user_prompt, chosen_route)
        print(f"chosen_route={chosen_route}")

        alignment_issue = detect_alignment_issue(
            ResponseValidationContext(
                user_prompt=user_prompt,
                assistant_content=final_data.content,
                route=chosen_route,
                tool_names=tool_names,
            )
        )
        if alignment_issue:
            await emit_trace(
                TraceItem(
                    phase="Reflection",
                    title="检测到答非所问",
                    detail=alignment_issue.message,
                    status="error",
                    timestamp=datetime.now(timezone.utc),
                )
            )
            corrected_response = await try_handle_specific_schedule_query(
                db,
                user,
                request,
                user_prompt=user_prompt,
                emit_trace=emit_trace,
                traces=traces,
            )
            if corrected_response is not None:
                return corrected_response

        # 持久化会话与消息
        stmt_session = select(ChatSession).where(ChatSession.session_id == request.session_id)
        chat_session = (await db.execute(stmt_session)).scalar_one_or_none()
        print("=== session loaded ===")
        if chat_session is None:
            chat_session = ChatSession(session_id=request.session_id, user_id=user.user_id)
            db.add(chat_session)
            print("=== session created ===")
        chat_session.updated_at = datetime.now(timezone.utc)

        user_message_time = datetime.now(timezone.utc)
        assistant_message_time = user_message_time + timedelta(microseconds=1)
        new_user_msg = ChatMessage(
            session_id=request.session_id,
            role="user",
            content=user_prompt,
            timestamp=user_message_time,
        )
        new_ast_msg = ChatMessage(
            session_id=request.session_id,
            role="assistant",
            content=final_data.content,
            timestamp=assistant_message_time,
        )
        db.add_all([new_user_msg, new_ast_msg])
        print("=== messages added ===")
        await db.commit()
        print("=== db.commit done ===")

        await emit_trace(
            TraceItem(
                phase="Reflection",
                title="完成响应封装",
                detail=f"本轮调用工具数: {len(tool_names)}，最终路由: {chosen_route}。",
                status="done",
                timestamp=datetime.now(timezone.utc),
            )
        )

        return AgentResponse(
            session_id=request.session_id,
            assistant_message=AssistantMessage(
                role="assistant",
                content=final_data.content,
                timestamp=datetime.now(timezone.utc),
            ),
            trace=traces,
            route=chosen_route,
            ui_payload=UIPayload(),
            hitl_request=None,
            error=None,
        )

    except HITLInterrupt as e:
        wait_trace = TraceItem(
            phase="Tool Use",
            title="等待用户授权",
            detail=e.reason,
            status="pending",
            timestamp=datetime.now(timezone.utc),
        )
        await emit_trace(wait_trace)

        stmt_session = select(ChatSession).where(ChatSession.session_id == request.session_id)
        chat_session = (await db.execute(stmt_session)).scalar_one_or_none()
        if chat_session is None:
            chat_session = ChatSession(session_id=request.session_id, user_id=user.user_id)
            db.add(chat_session)
        chat_session.updated_at = datetime.now(timezone.utc)
        db.add(ChatMessage(session_id=request.session_id, role="user", content=user_prompt))
        await db.commit()

        return AgentResponse(
            session_id=request.session_id,
            assistant_message=AssistantMessage(
                role="assistant",
                content=f"我需要您的授权来执行：{e.reason}",
                timestamp=datetime.now(timezone.utc),
            ),
            trace=traces,
            route="os_automation",
            ui_payload=UIPayload(),
            hitl_request=hitl_manager.to_schema(
                state=e.pending_state,
                payload=e.payload,
                reason=e.reason,
            ),
            error=None,
        )

    except asyncio.TimeoutError:
        await emit_trace(
            TraceItem(
                phase="Reflection",
                title="推理超时",
                detail=f"Agent 在 {settings.AGENT_RUN_TIMEOUT_SECONDS} 秒内未完成推理或工具调用。",
                status="error",
                timestamp=datetime.now(timezone.utc),
            )
        )
        return AgentResponse(
            session_id=request.session_id,
            assistant_message=AssistantMessage(
                role="assistant",
                content="本次 Agent 推理超时。请稍后重试，或把问题拆小一些再试。",
                timestamp=datetime.now(timezone.utc),
            ),
            trace=traces,
            route="chat",
            ui_payload=UIPayload(),
            hitl_request=None,
            error=ErrorDetail(
                code="agent_timeout",
                message=f"Agent run exceeded {settings.AGENT_RUN_TIMEOUT_SECONDS} seconds.",
                retryable=True,
            ),
        )

    except Exception as e:
        print("=== agent.run exception ===")
        print(f"error_type={type(e).__name__}")
        print(f"error_message={e}")
        print(traceback.format_exc())
        await emit_trace(
            TraceItem(
                phase="Reflection",
                title="运行异常",
                detail=str(e),
                status="error",
                timestamp=datetime.now(timezone.utc),
            )
        )
        return AgentResponse(
            session_id=request.session_id,
            assistant_message=AssistantMessage(
                role="assistant",
                content="Agent 运行出现异常，请稍后重试。",
                timestamp=datetime.now(timezone.utc),
            ),
            trace=traces,
            route="chat",
            ui_payload=UIPayload(),
            hitl_request=None,
            error=ErrorDetail(
                code="agent_runtime_error",
                message=f"Agent 运行异常: {e}",
                retryable=True,
            ),
        )


def _build_trace(raw_messages: list) -> list[TraceItem]:
    """
    将 PydanticAI 的内部消息列表转换为前端 Thought Trace。
    实现 Observation 阶段逻辑：分析工具调用结果中的异常。
    """
    traces: list[TraceItem] = []

    for msg in raw_messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    is_error = isinstance(part.content, str) and part.content.startswith("ERROR:")
                    traces.append(TraceItem(
                        phase="Observation",
                        title=f"检查工具 [{part.tool_name}] 的返回结果",
                        detail=str(part.content)[:240] if part.content is not None else "",
                        status="error" if is_error else "done",
                        timestamp=datetime.now(timezone.utc),
                    ))
                elif isinstance(part, UserPromptPart):
                    traces.append(TraceItem(
                        phase="Observation",
                        title="解析用户输入",
                        detail=str(part.content)[:240],
                        status="done",
                        timestamp=datetime.now(timezone.utc),
                    ))

        elif isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    traces.append(TraceItem(
                        phase="Tool Use",
                        title=f"调用工具: {part.tool_name}",
                        detail=f"call_id={getattr(part, 'tool_call_id', '')}",
                        status="done",
                        timestamp=datetime.now(timezone.utc),
                    ))
                elif hasattr(part, "content") and isinstance(part.content, str) and part.content.strip():
                    traces.append(TraceItem(
                        phase="Reasoning",
                        title="思考下一步行动",
                        detail=part.content[:240],
                        status="done",
                        timestamp=datetime.now(timezone.utc),
                    ))

    return traces


def _extract_tool_names(raw_messages: list) -> list[str]:
    tool_names: list[str] = []
    for msg in raw_messages:
        if not isinstance(msg, ModelResponse):
            continue
        for part in msg.parts:
            if isinstance(part, ToolCallPart):
                tool_names.append(part.tool_name)
    return tool_names


def _build_message_history(history_messages: list[ChatMessage]) -> list[ModelRequest | ModelResponse]:
    """Convert persisted chat messages into the PydanticAI message history format."""
    message_history: list[ModelRequest | ModelResponse] = []
    for item in history_messages:
        if item.role == "user":
            message_history.append(
                ModelRequest(parts=[UserPromptPart(item.content)], timestamp=item.timestamp)
            )
        elif item.role == "assistant":
            message_history.append(
                ModelResponse(
                    parts=[TextPart(item.content)],
                    timestamp=item.timestamp,
                    model_name=settings.DEEPSEEK_MODEL,
                )
            )
    return message_history


# ── 工具注册 ──────────────────────────────────────────────────────────────────
from backend.agent import tools  # noqa: E402, F401
