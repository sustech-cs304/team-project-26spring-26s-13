"""
backend/api/agent.py
Agent 核心路由：统一接收用户消息（含 HITL 审批）并返回 Agent 响应。
"""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.postgres import User, ChatSession, ChatMessage, get_db
from backend.schemas.agent import AgentRequest, AgentResponse, ChatMessage as ChatMessageSchema, SessionDetail, SessionSummary
from backend.agent.loop import run_agent
from backend.agent.hitl import hitl_manager
from backend.api.deps import get_current_user

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/run", response_model=AgentResponse)
async def agent_run(
    body: AgentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    """
    Agent 主入口，处理两种请求：

    【普通对话】body.hitl_reply == None
        流程：message → agent loop → tools → AgentResponse

    【HITL 审批回传】body.hitl_reply != None
        流程：
        1. 通过 hitl_reply.request_id 在 hitl_manager 中找到挂起状态
        2. 设置 approved 并触发 threading.Event 解锁等待中的操作
        3. 运行后续 Agent 步骤并返回最终结果

    注意：user_id 必须与 token 中的 user_id 一致，否则 403。

    Raises:
        400: session_id 格式错误
        403: user_id 与 token 不匹配
        404: HITL request_id 不存在（可能已超时被清理）
        500: LLM API 调用失败
    """
    return await _run_agent_with_hitl_resolution(
        db=db,
        current_user=current_user,
        body=body,
    )


@router.post("/run/stream")
async def agent_run_stream(
    body: AgentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    NDJSON 流式版本：持续输出 trace，再输出 final 响应。

    每行一个 JSON 对象：
      {"event":"trace","data":{TraceItem...}}
      {"event":"final","data":{AgentResponse...}}
      {"event":"error","data":{"message":"..."}}
    """
    queue: asyncio.Queue[dict] = asyncio.Queue()

    async def on_trace(trace_item) -> None:
        await queue.put({"event": "trace", "data": trace_item.model_dump(mode="json")})

    task = asyncio.create_task(
        _run_agent_with_hitl_resolution(
            db=db,
            current_user=current_user,
            body=body,
            trace_emitter=on_trace,
        )
    )

    async def stream_gen():
        while True:
            if task.done() and queue.empty():
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.2)
            except TimeoutError:
                continue
            yield json.dumps(event, ensure_ascii=False) + "\n"

        try:
            result = await task
        except HTTPException as exc:
            payload = {"event": "error", "data": {"message": str(exc.detail), "status_code": exc.status_code}}
            yield json.dumps(payload, ensure_ascii=False) + "\n"
            return
        except Exception as exc:  # noqa: BLE001
            payload = {"event": "error", "data": {"message": str(exc), "status_code": 500}}
            yield json.dumps(payload, ensure_ascii=False) + "\n"
            return

        yield json.dumps({"event": "final", "data": result.model_dump(mode="json")}, ensure_ascii=False) + "\n"

    return StreamingResponse(stream_gen(), media_type="application/x-ndjson")


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionSummary]:
    """
    返回当前用户的历史会话列表（按更新时间倒序）。
    用于前端"历史对话"入口。
    """
    stmt = (
        select(ChatSession)
        .where(ChatSession.user_id == current_user.user_id)
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = (await db.execute(stmt)).scalars().all()

    results: list[SessionSummary] = []
    for sess in sessions:
        title_stmt = (
            select(ChatMessage.content)
            .where(
                ChatMessage.session_id == sess.session_id,
                ChatMessage.role == "user",
            )
            .order_by(
                ChatMessage.timestamp.asc(),
                case((ChatMessage.role == "user", 0), else_=1).asc(),
            )
            .limit(1)
        )
        preview_stmt = (
            select(ChatMessage.content)
            .where(ChatMessage.session_id == sess.session_id)
            .where(ChatMessage.role == "user")
            .order_by(
                ChatMessage.timestamp.desc(),
                case((ChatMessage.role == "user", 0), else_=1).asc(),
            )
            .limit(1)
        )
        title_content = (await db.execute(title_stmt)).scalar_one_or_none() or ""
        preview_content = (await db.execute(preview_stmt)).scalar_one_or_none() or title_content
        results.append(
            SessionSummary(
                session_id=sess.session_id,
                title=title_content[:120],
                preview=preview_content[:120],
                updated_at=sess.updated_at,
            )
        )
    return results


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session_detail(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionDetail:
    stmt = select(ChatSession).where(ChatSession.session_id == session_id)
    session_obj = (await db.execute(stmt)).scalar_one_or_none()
    if session_obj is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session_obj.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="forbidden")

    title_stmt = (
        select(ChatMessage.content)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.role == "user",
        )
        .order_by(
            ChatMessage.timestamp.asc(),
            case((ChatMessage.role == "user", 0), else_=1).asc(),
        )
        .limit(1)
    )
    title_content = (await db.execute(title_stmt)).scalar_one_or_none() or ""

    message_stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(
            ChatMessage.timestamp.asc(),
            case((ChatMessage.role == "user", 0), else_=1).asc(),
        )
    )
    messages = (await db.execute(message_stmt)).scalars().all()

    return SessionDetail(
        session_id=session_id,
        title=title_content[:120],
        updated_at=session_obj.updated_at,
        messages=[
            ChatMessageSchema(
                message_id=str(msg.message_id),
                role=msg.role,
                content=msg.content,
                timestamp=msg.timestamp,
            )
            for msg in messages
        ],
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    删除指定会话及其所有消息记录（级联删除）。

    Raises:
        403: session 不属于当前用户
        404: session 不存在
    """
    stmt = select(ChatSession).where(ChatSession.session_id == session_id)
    session_obj = (await db.execute(stmt)).scalar_one_or_none()
    if session_obj is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session_obj.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="forbidden")

    await db.delete(session_obj)
    await db.commit()


async def _run_agent_with_hitl_resolution(
    *,
    db: AsyncSession,
    current_user: User,
    body: AgentRequest,
    trace_emitter=None,
) -> AgentResponse:
    if str(current_user.user_id) != body.user_id:
        raise HTTPException(status_code=403, detail="user_id mismatch")

    pending = None
    if body.hitl_reply is not None:
        pending = hitl_manager.get(body.hitl_reply.request_id)
        if pending is None:
            raise HTTPException(status_code=404, detail="HITL request not found or expired")
        if pending.session_id != body.session_id:
            raise HTTPException(status_code=403, detail="HITL request does not belong to this session")
        resolved = hitl_manager.resolve(body.hitl_reply.request_id, body.hitl_reply.approved)
        if not resolved:
            raise HTTPException(status_code=404, detail="HITL request not found or expired")

    return await run_agent(
        db=db,
        user=current_user,
        request=body,
        hitl_context=pending,
        trace_emitter=trace_emitter,
    )
