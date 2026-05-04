"""
backend/agent/hitl.py
HITL（Human-in-the-Loop）挂起状态管理器。
使用内存字典存储挂起的高风险操作，重启后状态丢失（当前 milestone 可接受）。

并发安全说明：
  FastAPI 在异步框架中运行，HITLManager 的操作需要线程安全保证。
  使用 threading.Lock 保护内部字典即可（或改用 asyncio.Lock）。
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Coroutine, Any

from backend.schemas.agent import HITLRequest, RiskLevel


@dataclass
class HITLPendingState:
    """
    一个挂起的 HITL 操作的完整上下文。
    Agent loop 在创建此对象后挂起等待；
    API 路由在收到审批回传后调用 resolve() 恢复执行。
    """

    request_id: str
    session_id: str
    action: str
    risk: RiskLevel

    # 审批结果（None=待定，True=批准，False=拒绝）
    approved: bool | None = None

    # threading.Event：Agent 线程在此 event 上 wait()，审批后 set()
    event: threading.Event = field(default_factory=threading.Event)

    # 审批后需要执行的回调（由 tools 注册，接受 approved: bool，返回 tool 执行结果字符串）
    # 签名：async def callback(approved: bool) -> str
    resume_callback: Callable[[bool], Coroutine[Any, Any, str]] | None = None

    created_at: float = field(default_factory=time.time)


class HITLManager:
    """
    全局单例，管理所有待审批的 HITL 操作。

    典型生命周期：
    1. tool 检测到高风险 → tool 调用 manager.create(...) 得到 HITLPendingState
    2. tool 在 state.event.wait(timeout=300) 上阻塞（5 分钟超时）
    3. 前端展示弹窗，用户点击批准/拒绝
    4. /api/agent/run 收到 hitl_reply → 调用 manager.resolve(request_id, approved)
    5. manager.resolve 设置 state.approved 并 state.event.set()
    6. tool 从 wait() 返回，读取 state.approved，继续或中止操作
    7. tool 执行完成后调用 manager.remove(request_id) 清理
    """

    def __init__(self) -> None:
        self._pending: dict[str, HITLPendingState] = {}
        self._lock = threading.Lock()

    def create(
        self,
        request_id: str,
        session_id: str,
        action: str,
        risk: RiskLevel,
        resume_callback: Callable[[bool], Coroutine[Any, Any, str]] | None = None,
    ) -> HITLPendingState:
        """
        创建并注册一个新的挂起 HITL 状态。
        同一 session 同时只允许一个挂起操作（旧的会被覆盖，记录 warning）。

        Args:
            request_id:       全局唯一 ID，格式 'hitl_{session_id}_{timestamp}'
            session_id:       所属会话
            action:           操作描述（展示给用户）
            risk:             风险等级
            resume_callback:  审批后执行的异步回调

        Returns:
            新创建的 HITLPendingState
        """
        state = HITLPendingState(
            request_id=request_id,
            session_id=session_id,
            action=action,
            risk=risk,
            resume_callback=resume_callback,
        )
        with self._lock:
            self._pending[request_id] = state
        return state

    def get(self, request_id: str) -> HITLPendingState | None:
        """根据 request_id 查询挂起状态，不存在返回 None。"""
        with self._lock:
            return self._pending.get(request_id)

    def resolve(self, request_id: str, approved: bool) -> bool:
        """
        设置审批结果并唤醒等待中的 Agent 线程。

        Args:
            request_id: 要解决的 HITL 请求 ID
            approved:   用户是否批准

        Returns:
            True 表示成功解决，False 表示 request_id 不存在（已超时清理）
        """
        with self._lock:
            state = self._pending.get(request_id)
        if state is None:
            return False
        state.approved = approved
        state.event.set()
        return True

    def remove(self, request_id: str) -> None:
        """操作完成后从内存中清理挂起状态。"""
        with self._lock:
            self._pending.pop(request_id, None)

    def to_schema(
        self, state: HITLPendingState, payload: list[str], reason: str
    ) -> HITLRequest:
        """
        将内部 HITLPendingState 转换为 API 响应中的 HITLRequest schema。

        Args:
            state:   挂起状态对象
            payload: 具体子操作列表（展示在弹窗详情中）
            reason:  为什么需要审批的说明

        Returns:
            HITLRequest（可直接放入 AgentResponse.hitl_request）
        """
        return HITLRequest(
            request_id=state.request_id,
            action=state.action,
            risk=state.risk,
            reason=reason,
            payload=payload,
        )


# 全局单例，所有模块直接 import 此对象
hitl_manager = HITLManager()
