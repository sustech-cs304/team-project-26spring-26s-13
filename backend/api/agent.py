"""
backend/api/agent.py
Agent 核心路由：统一接收用户消息（含 HITL 审批）并返回 Agent 响应。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.postgres import User, get_db
from backend.schemas.agent import AgentRequest, AgentResponse, SessionSummary
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
    if str(current_user.user_id) != body.user_id:
        raise HTTPException(status_code=403, detail="user_id mismatch")

    # HITL 审批路径
    if body.hitl_reply is not None:
        pending = hitl_manager.get(body.hitl_reply.request_id)
        if pending is None:
            raise HTTPException(status_code=404, detail="HITL request not found or expired")
        # TODO: hitl_manager.resolve(body.hitl_reply.request_id, body.hitl_reply.approved)
        #       然后 run_agent(db, current_user, body, hitl_context=pending)

    # TODO: return await run_agent(db, current_user, body)
    raise NotImplementedError


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionSummary]:
    """
    返回当前用户的历史会话列表（按更新时间倒序）。
    用于前端"历史对话"入口。
    """
    # TODO: 从 chat_sessions 表查询，关联最新消息作为 preview
    raise NotImplementedError


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
    # TODO: 验证归属后 db.delete(session)
    raise NotImplementedError
