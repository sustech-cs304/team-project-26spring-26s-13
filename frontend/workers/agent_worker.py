"""
Frontend Relevant/workers/agent_worker.py
QThread Worker：在后台线程中调用 /api/agent/run，避免阻塞 UI 主线程。
结果和错误通过 Qt Signal 传递回主线程。

使用方式：
    worker = AgentWorker(session_id, user_id, message)
    worker.response_ready.connect(self.on_response)
    worker.error_occurred.connect(self.on_error)
    worker.start()
"""

from PyQt6.QtCore import QThread, pyqtSignal

from frontend.api.client import APIClient, APIError, api_client


class AgentWorker(QThread):
    """
    在独立线程中发起 agent/run 请求。
    支持普通消息和 HITL 审批两种调用模式。
    """

    # 成功时 emit，携带完整的 AgentResponse dict
    response_ready = pyqtSignal(dict)

    # 流式推送 trace item，供右侧 Thought Trace 实时更新
    trace_streamed = pyqtSignal(dict)

    # 失败时 emit，携带错误描述字符串
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        session_id: str,
        user_id: str,
        message: str,
        attachments: list[dict] | None = None,
        hitl_reply: dict | None = None,
        stream_trace: bool = True,
        client: APIClient | None = None,
    ) -> None:
        """
        Args:
            session_id:  当前会话 ID
            user_id:     当前用户 ID
            message:     用户消息（HITL 审批时为空字符串）
            attachments: 附件列表（可选）
            hitl_reply:  HITL 审批结果（可选）
            client:      APIClient 实例，默认使用全局单例 api_client
        """
        super().__init__()
        self.session_id = session_id
        self.user_id = user_id
        self.message = message
        self.attachments = attachments or []
        self.hitl_reply = hitl_reply
        self.stream_trace = stream_trace
        self._client = client or api_client

    def run(self) -> None:
        """
        在后台线程中执行，调用 API 后 emit 对应 signal。
        不要在此方法中更新任何 UI 组件（Qt 要求 UI 操作在主线程）。
        """
        try:
            if self.stream_trace:
                def on_event(event: dict) -> None:
                    if event.get("event") == "trace":
                        data = event.get("data")
                        if isinstance(data, dict):
                            self.trace_streamed.emit(data)

                response = self._client.agent_run_stream(
                    session_id=self.session_id,
                    user_id=self.user_id,
                    message=self.message,
                    attachments=self.attachments,
                    hitl_reply=self.hitl_reply,
                    on_event=on_event,
                )
            else:
                response = self._client.agent_run(
                    session_id=self.session_id,
                    user_id=self.user_id,
                    message=self.message,
                    attachments=self.attachments,
                    hitl_reply=self.hitl_reply,
                )
            self.response_ready.emit(response)
        except APIError as exc:
            self.error_occurred.emit(f"API Error {exc.status_code}: {exc.detail}")
        except Exception as exc:  # noqa: BLE001
            self.error_occurred.emit(str(exc))
