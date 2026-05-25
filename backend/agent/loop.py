"""
backend/agent/loop.py
PydanticAI Agent 主循环。
负责：上下文组装 → Agent 推理 → 工具调用 → Observation (Trace 收集) → 结果封装。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone


from pydantic_ai import usage as pai_usage
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
    EncyclopediaResult,
    ErrorDetail,
    LibraryRoom,
    LibraryRoomResult,
    RiskLevel,
    ScheduleConflict,
    ScheduleData,
    ScheduleEvent,
    TraceItem,
    UIPayload,
)
from backend.agent.hitl import HITLInterrupt, HITLPendingState, hitl_manager
from backend.agent.tools.os_automation import execute_approved_hitl_operation
from backend.agent.core import AgentDeps, agent, FinalResponse
from backend.agent.prompt import build_hitl_continuation_prompt
from backend.agent.router import determine_route
from backend.agent.tool_policy import normalize_route_for_prompt
from backend.agent.validators import ResponseValidationContext, detect_alignment_issue
import traceback

TraceEmitter = Callable[[TraceItem], Awaitable[None] | None]


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
    cas_password = (
        decrypt(user.cas_password_encrypted) if user.cas_password_encrypted else None
    )

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
        hitl_approved=bool(
            hitl_context is not None
            and request.hitl_reply is not None
            and request.hitl_reply.approved
        ),
        trace_log=[],
    )

    user_prompt = request.message
    if hitl_context and request.hitl_reply is not None:
        if not request.hitl_reply.approved:
            hitl_manager.remove(hitl_context.request_id)
            await emit_trace(
                TraceItem(
                    phase="Tool Use",
                    title="用户拒绝授权",
                    detail=hitl_context.action,
                    status="done",
                    timestamp=datetime.now(timezone.utc),
                )
            )
            return AgentResponse(
                session_id=request.session_id,
                assistant_message=AssistantMessage(
                    role="assistant",
                    content=f"已取消操作：{hitl_context.action}",
                    timestamp=datetime.now(timezone.utc),
                ),
                trace=traces,
                route="os_automation",
                ui_payload=UIPayload(),
                hitl_request=None,
                error=None,
            )

        if hitl_context.tool_name and hitl_context.tool_args:
            tool_result = await execute_approved_hitl_operation(deps, hitl_context)
            hitl_manager.remove(hitl_context.request_id)
            await emit_trace(
                TraceItem(
                    phase="Tool Use",
                    title="已执行授权操作",
                    detail=tool_result,
                    status="done",
                    timestamp=datetime.now(timezone.utc),
                )
            )
            stmt_session = select(ChatSession).where(
                ChatSession.session_id == request.session_id
            )
            chat_session = (await db.execute(stmt_session)).scalar_one_or_none()
            if chat_session is None:
                chat_session = ChatSession(
                    session_id=request.session_id, user_id=user.user_id
                )
                db.add(chat_session)
            chat_session.updated_at = datetime.now(timezone.utc)
            db.add(
                ChatMessage(
                    session_id=request.session_id,
                    role="user",
                    content=request.message or hitl_context.action,
                )
            )
            db.add(
                ChatMessage(
                    session_id=request.session_id,
                    role="assistant",
                    content=tool_result,
                )
            )
            await db.commit()
            return AgentResponse(
                session_id=request.session_id,
                assistant_message=AssistantMessage(
                    role="assistant",
                    content=tool_result,
                    timestamp=datetime.now(timezone.utc),
                ),
                trace=traces,
                route="os_automation",
                ui_payload=UIPayload(),
                hitl_request=None,
                error=None,
            )

        user_prompt = build_hitl_continuation_prompt(
            hitl_context.action,
            request.hitl_reply.approved,
            tool_name=hitl_context.tool_name,
            tool_args=hitl_context.tool_args,
        )

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
                usage_limits=pai_usage.UsageLimits(request_limit=500),
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
        blackboard_result = _extract_tool_return_content(
            raw_messages, "fetch_blackboard_deadlines"
        )
        final_data = _normalize_blackboard_deadline_response(
            user_prompt, final_data, blackboard_result
        )
        library_result = _extract_tool_return_content(
            raw_messages, "query_library_rooms"
        )
        final_data = _normalize_library_room_response(
            user_prompt, final_data, library_result
        )
        route_by_tools = determine_route(tool_names)
        chosen_route = route_by_tools if tool_names else final_data.route
        chosen_route = normalize_route_for_prompt(user_prompt, chosen_route)
        final_data = _ensure_source_citations(final_data, raw_messages)
        schedule_payload = _build_schedule_data_from_tool_returns(
            user_prompt,
            raw_messages,
            blackboard_result,
        )
        encyclopedia_payload = _build_encyclopedia_payload(
            user_prompt,
            final_data.content,
            raw_messages,
        )
        library_payload = _build_library_payload(raw_messages)
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

        # 持久化会话与消息
        stmt_session = select(ChatSession).where(
            ChatSession.session_id == request.session_id
        )
        chat_session = (await db.execute(stmt_session)).scalar_one_or_none()
        print("=== session loaded ===")
        if chat_session is None:
            chat_session = ChatSession(
                session_id=request.session_id, user_id=user.user_id
            )
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
            ui_payload=UIPayload(
                schedule=schedule_payload,
                encyclopedia=encyclopedia_payload,
                library=library_payload,
            ),
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

        stmt_session = select(ChatSession).where(
            ChatSession.session_id == request.session_id
        )
        chat_session = (await db.execute(stmt_session)).scalar_one_or_none()
        if chat_session is None:
            chat_session = ChatSession(
                session_id=request.session_id, user_id=user.user_id
            )
            db.add(chat_session)
        chat_session.updated_at = datetime.now(timezone.utc)
        db.add(
            ChatMessage(session_id=request.session_id, role="user", content=user_prompt)
        )
        await db.commit()

        return AgentResponse(
            session_id=request.session_id,
            assistant_message=AssistantMessage(
                role="assistant",
                content=(
                    f"我需要您的授权来执行：{e.pending_state.action}。"
                    f"{e.reason}"
                ),
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
                    is_error = isinstance(
                        part.content, str
                    ) and part.content.startswith("ERROR:")
                    traces.append(
                        TraceItem(
                            phase="Observation",
                            title=f"检查工具 [{part.tool_name}] 的返回结果",
                            detail=(
                                str(part.content)[:240]
                                if part.content is not None
                                else ""
                            ),
                            status="error" if is_error else "done",
                            timestamp=datetime.now(timezone.utc),
                        )
                    )
                elif isinstance(part, UserPromptPart):
                    traces.append(
                        TraceItem(
                            phase="Observation",
                            title="解析用户输入",
                            detail=str(part.content)[:240],
                            status="done",
                            timestamp=datetime.now(timezone.utc),
                        )
                    )

        elif isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    traces.append(
                        TraceItem(
                            phase="Tool Use",
                            title=f"调用工具: {part.tool_name}",
                            detail=f"call_id={getattr(part, 'tool_call_id', '')}",
                            status="done",
                            timestamp=datetime.now(timezone.utc),
                        )
                    )
                elif (
                    hasattr(part, "content")
                    and isinstance(part.content, str)
                    and part.content.strip()
                ):
                    traces.append(
                        TraceItem(
                            phase="Reasoning",
                            title="思考下一步行动",
                            detail=part.content[:240],
                            status="done",
                            timestamp=datetime.now(timezone.utc),
                        )
                    )

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


def _extract_tool_return_content(raw_messages: list, tool_name: str) -> str | None:
    contents = _extract_tool_return_contents(raw_messages, tool_name)
    return contents[0] if contents else None


def _extract_tool_return_contents(raw_messages: list, tool_name: str) -> list[str]:
    contents: list[str] = []
    for msg in raw_messages:
        if not isinstance(msg, ModelRequest):
            continue
        for part in msg.parts:
            if isinstance(part, ToolReturnPart) and part.tool_name == tool_name:
                if isinstance(part.content, str):
                    contents.append(part.content)
    return contents


def _load_json_object(raw: str | None) -> object | None:
    if not raw or raw.startswith("ERROR:"):
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _extract_rag_citations(raw_messages: list) -> list[str]:
    citations: list[str] = []
    seen: set[str] = set()
    for raw in _extract_tool_return_contents(raw_messages, "query_rag"):
        payload = _load_json_object(raw)
        if not isinstance(payload, dict):
            continue
        chunks = payload.get("chunks")
        if not isinstance(chunks, list):
            continue
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            file_name = str(chunk.get("file_name") or "").strip()
            if not file_name or file_name in seen:
                continue
            seen.add(file_name)
            citations.append(file_name)
    return citations


def _ensure_source_citations(
    final_data: FinalResponse,
    raw_messages: list,
) -> FinalResponse:
    citations = _extract_rag_citations(raw_messages)
    if not citations:
        return final_data

    content = final_data.content or ""
    if any(citation in content for citation in citations):
        return final_data

    has_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in content)
    heading = "来源" if has_chinese else "Sources"
    citation_lines = [f"{idx}. {citation}" for idx, citation in enumerate(citations, 1)]
    return FinalResponse(
        content=f"{content.rstrip()}\n\n{heading}：\n" + "\n".join(citation_lines),
        route=final_data.route,
    )


def _build_encyclopedia_payload(
    user_prompt: str,
    answer_markdown: str,
    raw_messages: list,
) -> EncyclopediaResult | None:
    citations = _extract_rag_citations(raw_messages)
    if not citations and not _extract_tool_return_contents(raw_messages, "query_rag"):
        return None
    return EncyclopediaResult(
        query=user_prompt,
        answer_markdown=answer_markdown,
        citations=citations,
    )


def _build_library_payload(
    raw_messages: list,
) -> LibraryRoomResult | None:
    """从 query_library_rooms 工具返回中构建 LibraryRoomResult。"""
    raw = _extract_tool_return_content(raw_messages, "query_library_rooms")
    payload = _load_json_object(raw)
    if not isinstance(payload, dict):
        return None

    rooms: list[LibraryRoom] = []
    for item in payload.get("rooms", []):
        if not isinstance(item, dict):
            continue
        rooms.append(
            LibraryRoom(
                room_id=str(item.get("room_id", "")),
                room_name=str(item.get("room_name", "")),
                location=str(item.get("location", "")),
                capacity=int(item.get("capacity", 0)),
                time_slots=item.get("time_slots", []),
            )
        )
    return LibraryRoomResult(
        query_location=str(payload.get("query_location", "")),
        query_time=str(payload.get("query_time", "")),
        query_capacity=payload.get("query_capacity"),
        has_available=bool(payload.get("has_available", False)),
        rooms=rooms,
    )


def _normalize_library_room_response(
    user_prompt: str,
    final_data: FinalResponse,
    library_result: str | None,
) -> FinalResponse:
    if not library_result or not library_result.startswith("ERROR:"):
        return final_data

    message = {
        "ERROR:CAS_LOGIN_FAILED": "我暂时无法查询图书馆讨论间，因为还没有可用的 CAS 账号密码。请先在设置中保存正确的 CAS 凭据后再试。",
        "ERROR:LIBRARY_DATE_IN_PAST": "不能查询过去日期的图书馆讨论间可预约时间。请换成今天、明天或后天。",
        "ERROR:LIBRARY_DATE_OUT_OF_RANGE": "图书馆讨论间通常只能查询/预约最近 2 天内的时间。请换成今天、明天或后天再试。",
    }.get(library_result)
    if message is None:
        message = "我没能从图书馆预约系统获取讨论间空闲信息。请稍后重试，或直接打开图书馆预约系统查看。"

    return FinalResponse(content=message, route="library")


def _is_deadline_query(text: str) -> bool:
    lowered = (text or "").lower()
    return any(
        k in text or k in lowered
        for k in (
            "作业",
            "ddl",
            "截止",
            "deadline",
            "deadlines",
            "assignment",
            "homework",
            "quiz",
            "exam",
        )
    )


def _format_deadline_label(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "未提供"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw
    return dt.strftime("%Y-%m-%d %H:%M")


def _normalize_blackboard_deadline_response(
    user_prompt: str, final_data: FinalResponse, blackboard_result: str | None
) -> FinalResponse:
    if not _is_deadline_query(user_prompt) or not blackboard_result:
        return final_data
    if blackboard_result == "ERROR:CAS_LOGIN_FAILED":
        return FinalResponse(
            content="我暂时无法获取 Blackboard 作业，因为未配置或无法使用 CAS 账号密码。请先在设置中保存正确的 CAS 凭据后重试。",
            route="scheduler",
        )
    if blackboard_result == "ERROR:BLACKBOARD_UNREACHABLE":
        return FinalResponse(
            content="抱歉，暂时无法访问 Blackboard 系统来获取您的未完成作业信息。请稍后重试，或直接登录 Blackboard 查看最新作业截止时间。",
            route="scheduler",
        )
    try:
        payload = json.loads(blackboard_result)
    except Exception:
        return final_data
    if not isinstance(payload, list):
        return final_data
    if not payload:
        return FinalResponse(
            content="当前没有查询到未完成的 Blackboard 作业或考试。", route="scheduler"
        )

    lines = ["您目前有以下未完成的作业：", "", "## 作业列表", ""]
    for idx, item in enumerate(
        sorted(payload, key=lambda x: str(x.get("deadline") or "")), start=1
    ):
        title = str(item.get("title") or "未命名任务")
        course_id = str(item.get("course_id") or "").strip()
        course_name = str(item.get("course_name") or "").strip()
        type_name = str(item.get("type") or "other").strip()
        estimated_minutes = item.get("estimated_minutes")
        priority = item.get("priority")
        url = str(item.get("url") or "").strip()
        course_label = (
            f"课程名称：{course_name}"
            if course_name and course_name != course_id
            else f"课程ID：{course_id or course_name}"
        )
        type_label = {
            "assignment": "作业",
            "quiz": "测验",
            "project": "项目",
            "presentation": "展示",
            "exam": "考试",
            "other": "其他",
        }.get(type_name, "其他")

        lines.append(f"{idx}. **{title}**")
        lines.append(f"   - {course_label}")
        lines.append(
            f"   - 截止时间：{_format_deadline_label(str(item.get('deadline') or ''))}"
        )
        lines.append(f"   - 类型：{type_label}")
        if estimated_minutes is not None:
            lines.append(f"   - 预计耗时：{estimated_minutes} 分钟")
        if priority is not None:
            lines.append(f"   - 优先级：{priority}")
        if url:
            lines.append(f"   - 查看链接：{url}")
        lines.append("")
    return FinalResponse(content="\n".join(lines), route="scheduler")


def _build_blackboard_schedule_data(
    user_prompt: str, blackboard_result: str | None
) -> ScheduleData | None:
    if not _is_deadline_query(user_prompt) or not blackboard_result:
        return None
    if blackboard_result.startswith("ERROR:"):
        return ScheduleData(events=[], conflicts=[])
    try:
        payload = json.loads(blackboard_result)
    except Exception:
        return None
    if not isinstance(payload, list):
        return None

    events: list[ScheduleEvent] = []
    for idx, item in enumerate(
        sorted(payload, key=lambda x: str(x.get("deadline") or "")), start=1
    ):
        title = str(item.get("title") or "未命名任务")
        course_id = str(item.get("course_id") or "").strip()
        course_name = str(item.get("course_name") or "").strip()
        type_name = str(item.get("type") or "other").strip()
        estimated_minutes = item.get("estimated_minutes")
        priority = item.get("priority")
        url = str(item.get("url") or "").strip()

        detail_parts = []
        if course_name and course_name != course_id:
            detail_parts.append(f"课程名称：{course_name}")
        elif course_id:
            detail_parts.append(f"课程ID：{course_id}")
        detail_parts.append(
            "类型："
            + {
                "assignment": "作业",
                "quiz": "测验",
                "project": "项目",
                "presentation": "展示",
                "exam": "考试",
                "other": "其他",
            }.get(type_name, "其他")
        )
        if estimated_minutes is not None:
            detail_parts.append(f"预计耗时：{estimated_minutes} 分钟")
        if priority is not None:
            detail_parts.append(f"优先级：{priority}")
        if url:
            detail_parts.append(f"链接：{url}")

        events.append(
            ScheduleEvent(
                event_id=f"bb_deadline_{idx}",
                title=title,
                time=_format_deadline_label(str(item.get("deadline") or "")),
                source="Blackboard",
                detail="；".join(detail_parts),
            )
        )
    return ScheduleData(events=events, conflicts=[])


def _coerce_schedule_event(item: dict, idx: int, prefix: str) -> ScheduleEvent | None:
    title = str(item.get("title") or item.get("course") or "").strip()
    time_label = str(item.get("time") or item.get("deadline") or "").strip()
    if not title or not time_label:
        return None
    return ScheduleEvent(
        event_id=str(item.get("event_id") or f"{prefix}_{idx}"),
        title=title,
        time=time_label,
        source=str(item.get("source") or "Schedule"),
        detail=str(item.get("detail") or ""),
    )


def _coerce_schedule_conflict(item: dict) -> ScheduleConflict | None:
    title = str(item.get("title") or "").strip()
    detail = str(item.get("detail") or "").strip()
    if not title and not detail:
        return None
    return ScheduleConflict(title=title or "Schedule conflict", detail=detail)


def _schedule_data_from_payload(payload: object, prefix: str) -> ScheduleData | None:
    if not isinstance(payload, dict):
        return None
    raw_events = payload.get("events")
    raw_conflicts = payload.get("conflicts")
    events: list[ScheduleEvent] = []
    conflicts: list[ScheduleConflict] = []

    if isinstance(raw_events, list):
        for idx, item in enumerate(raw_events, start=1):
            if isinstance(item, dict):
                event = _coerce_schedule_event(item, idx, prefix)
                if event is not None:
                    events.append(event)

    if isinstance(raw_conflicts, list):
        for item in raw_conflicts:
            if isinstance(item, dict):
                conflict = _coerce_schedule_conflict(item)
                if conflict is not None:
                    conflicts.append(conflict)

    if not events and not conflicts:
        return None
    return ScheduleData(events=events, conflicts=conflicts)


def _personal_tasks_schedule_data(raw: str | None) -> ScheduleData | None:
    payload = _load_json_object(raw)
    if not isinstance(payload, list):
        return None
    events: list[ScheduleEvent] = []
    for idx, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        start_time = str(item.get("start_time") or "").strip()
        if not title or not start_time:
            continue
        end_time = str(item.get("end_time") or "").strip()
        time_label = f"{start_time}~{end_time}" if end_time else start_time
        detail_parts = []
        if item.get("location"):
            detail_parts.append(f"地点：{item['location']}")
        if item.get("description"):
            detail_parts.append(f"说明：{item['description']}")
        events.append(
            ScheduleEvent(
                event_id=str(item.get("task_id") or f"personal_task_{idx}"),
                title=title,
                time=time_label,
                source="Local TODO",
                detail="；".join(detail_parts),
            )
        )
    return ScheduleData(events=events, conflicts=[]) if events else None


def _courses_on_date_schedule_data(raw: str | None) -> ScheduleData | None:
    payload = _load_json_object(raw)
    if not isinstance(payload, dict):
        return None
    date_label = str(payload.get("date") or "").strip()
    courses = payload.get("courses")
    if not date_label or not isinstance(courses, list):
        return None

    events: list[ScheduleEvent] = []
    for idx, item in enumerate(courses, start=1):
        if not isinstance(item, dict):
            continue
        course = str(item.get("course") or item.get("course_id") or "").strip()
        start_time = str(item.get("start_time") or "").strip()
        end_time = str(item.get("end_time") or "").strip()
        if not course or not start_time:
            continue
        detail_parts = []
        if item.get("location"):
            detail_parts.append(f"地点：{item['location']}")
        if item.get("instructor"):
            detail_parts.append(f"教师：{item['instructor']}")
        events.append(
            ScheduleEvent(
                event_id=f"course_on_date_{idx}",
                title=course,
                time=f"{date_label} {start_time}-{end_time}",
                source="教务系统",
                detail="；".join(detail_parts),
            )
        )
    return ScheduleData(events=events, conflicts=[]) if events else None


def _build_schedule_data_from_tool_returns(
    user_prompt: str,
    raw_messages: list,
    blackboard_result: str | None,
) -> ScheduleData | None:
    for tool_name, prefix in (
        ("build_proactive_schedule_context", "proactive_schedule"),
        ("detect_schedule_conflicts", "schedule_conflict"),
    ):
        for raw in reversed(_extract_tool_return_contents(raw_messages, tool_name)):
            payload = _load_json_object(raw)
            schedule_data = _schedule_data_from_payload(payload, prefix)
            if schedule_data is not None:
                return schedule_data

    personal_raw = _extract_tool_return_content(raw_messages, "list_personal_tasks")
    personal_data = _personal_tasks_schedule_data(personal_raw)
    if personal_data is not None:
        return personal_data

    courses_raw = _extract_tool_return_content(raw_messages, "fetch_courses_on_date")
    courses_data = _courses_on_date_schedule_data(courses_raw)
    if courses_data is not None:
        return courses_data

    return _build_blackboard_schedule_data(user_prompt, blackboard_result)


def _build_message_history(
    history_messages: list[ChatMessage],
) -> list[ModelRequest | ModelResponse]:
    """Convert persisted chat messages into the PydanticAI message history format."""
    message_history: list[ModelRequest | ModelResponse] = []
    for item in history_messages:
        if item.role == "user":
            message_history.append(ModelRequest(parts=[UserPromptPart(item.content)]))
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
