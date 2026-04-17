"""
God Xun-Frontend/views/dashboard_page.py
主界面：三栏布局（左侧边栏 / 中间主区 / 右侧 Trace 面板）。
负责协调所有子组件，处理 AgentWorker 返回的数据并分发给对应组件。
"""

import uuid

from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import QHBoxLayout, QSplitter, QWidget

from frontend.api.client import api_client
from frontend.components.chat_widget import ChatWidget
from frontend.components.encyclopedia_widget import EncyclopediaWidget
from frontend.components.hitl_dialog import HITLDialog
from frontend.components.materials_widget import MaterialsWidget
from frontend.components.schedule_widget import ScheduleWidget
from frontend.components.trace_widget import TraceWidget
from frontend.workers.agent_worker import AgentWorker


class DashboardPage(QWidget):
    """
    三栏主界面。

    布局（QSplitter）：
      ├── 左栏（LeftPanel）:    用户卡片 + 材料列表（MaterialsWidget）
      ├── 中栏（CenterPanel）:  QTabWidget
      │   ├── Tab "Chat":       ChatWidget
      │   ├── Tab "Schedule":   ScheduleWidget
      │   └── Tab "Encyclopedia": EncyclopediaWidget
      └── 右栏（RightPanel）:   TraceWidget
    """

    def __init__(self, user_id: str, display_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._user_id = user_id
        self._session_id = f"sess_{uuid.uuid4().hex[:8]}"
        self._current_worker: AgentWorker | None = None
        # TODO: self._setup_ui(); self._load_bootstrap()

    def _setup_ui(self) -> None:
        """初始化三栏 QSplitter 布局，实例化所有子组件。"""
        # TODO
        raise NotImplementedError

    def _load_bootstrap(self) -> None:
        """
        调用 api_client.get_bootstrap()，将数据分发给各组件：
        - user_profile  → 左侧用户卡片
        - materials     → MaterialsWidget
        - chat_history  → ChatWidget
        - local_schedule → ScheduleWidget
        """
        # TODO
        raise NotImplementedError

    def send_message(self, message: str, attachments: list[dict] | None = None) -> None:
        """
        用户发送消息时调用（由 ChatWidget emit signal 触发）。
        创建 AgentWorker 在后台发请求，防止 UI 卡顿。
        同时禁用输入框直到响应返回。

        Args:
            message:     用户输入的消息文本
            attachments: 附件列表（可选）
        """
        # TODO:
        # self._current_worker = AgentWorker(self._session_id, self._user_id, message, attachments)
        # self._current_worker.response_ready.connect(self._on_agent_response)
        # self._current_worker.error_occurred.connect(self._on_agent_error)
        # self._current_worker.start()
        raise NotImplementedError

    @pyqtSlot(dict)
    def _on_agent_response(self, response: dict) -> None:
        """
        AgentWorker 返回后，将数据分发给各子组件。

        分发规则：
          - assistant_message → ChatWidget.add_message()
          - trace             → TraceWidget.update_trace()
          - route == "scheduler"    → 切换到 Schedule tab
          - route == "encyclopedia" → 切换到 Encyclopedia tab
          - ui_payload.schedule     → ScheduleWidget.update_schedule()
          - ui_payload.encyclopedia → EncyclopediaWidget.show_result()
          - hitl_request != null    → 弹出 HITLDialog
        """
        # TODO
        raise NotImplementedError

    @pyqtSlot(str)
    def _on_agent_error(self, error_msg: str) -> None:
        """AgentWorker 报错时，在 ChatWidget 中显示错误消息。"""
        # TODO
        raise NotImplementedError

    def _show_hitl_dialog(self, hitl_request: dict) -> None:
        """
        弹出 HITLDialog，连接 approved/rejected signal。
        用户操作后通过 AgentWorker 发送 hitl_reply 请求。
        """
        # TODO:
        # dialog = HITLDialog(hitl_request, parent=self)
        # dialog.approved.connect(lambda req_id: self._send_hitl_reply(req_id, True))
        # dialog.rejected.connect(lambda req_id: self._send_hitl_reply(req_id, False))
        # dialog.exec()
        raise NotImplementedError

    def _send_hitl_reply(self, request_id: str, approved: bool) -> None:
        """
        HITL 审批后，复用 AgentWorker 发送审批结果。

        Args:
            request_id: hitl_request.request_id
            approved:   用户批准结果
        """
        # TODO:
        # worker = AgentWorker(
        #     session_id=self._session_id,
        #     user_id=self._user_id,
        #     message="",
        #     hitl_reply={"request_id": request_id, "approved": approved},
        # )
        # worker.response_ready.connect(self._on_agent_response)
        # worker.error_occurred.connect(self._on_agent_error)
        # worker.start()
        raise NotImplementedError
