"""
Frontend Relevant/views/dashboard_page.py
主界面：三栏布局（左侧边栏 / 中间主区 / 右侧 Trace 面板）。
负责协调所有子组件，处理 AgentWorker 返回的数据并分发给对应组件。
"""

import uuid

from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import QHBoxLayout, QSplitter, QTabWidget, QWidget

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
        self._display_name = display_name
        self._setup_ui()
        self._load_bootstrap()

    def _setup_ui(self) -> None:
        """初始化三栏 QSplitter 布局，实例化所有子组件。"""
        def _safe_make(factory):
            try:
                return factory(self)
            except Exception:
                return QWidget(self)

        self.materials_widget = _safe_make(MaterialsWidget)
        self.chat_widget = _safe_make(ChatWidget)
        self.schedule_widget = _safe_make(ScheduleWidget)
        self.encyclopedia_widget = _safe_make(EncyclopediaWidget)
        self.trace_widget = _safe_make(TraceWidget)

        if hasattr(self.chat_widget, "message_submitted"):
            self.chat_widget.message_submitted.connect(self.send_message)

        self.center_tabs = QTabWidget(self)
        self.center_tabs.addTab(self.chat_widget, "Chat")
        self.center_tabs.addTab(self.schedule_widget, "Schedule")
        self.center_tabs.addTab(self.encyclopedia_widget, "Encyclopedia")

        splitter = QSplitter(self)
        splitter.addWidget(self.materials_widget)
        splitter.addWidget(self.center_tabs)
        splitter.addWidget(self.trace_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 2)

        layout = QHBoxLayout(self)
        layout.addWidget(splitter)

    def _load_bootstrap(self) -> None:
        """
        调用 api_client.get_bootstrap()，将数据分发给各组件：
        - user_profile  → 左侧用户卡片
        - materials     → MaterialsWidget
        - chat_history  → ChatWidget
        - local_schedule → ScheduleWidget
        """
        try:
            data = api_client.get_bootstrap()
        except Exception:
            return

        materials = data.get("materials", [])
        chat_history = data.get("chat_history", [])
        local_schedule = data.get("local_schedule", {})

        if hasattr(self.materials_widget, "load_materials"):
            self.materials_widget.load_materials(materials)
        if hasattr(self.chat_widget, "load_history"):
            self.chat_widget.load_history(chat_history)
        if hasattr(self.schedule_widget, "update_schedule"):
            self.schedule_widget.update_schedule(local_schedule)

    def send_message(self, message: str, attachments: list[dict] | None = None) -> None:
        """
        用户发送消息时调用（由 ChatWidget emit signal 触发）。
        创建 AgentWorker 在后台发请求，防止 UI 卡顿。
        同时禁用输入框直到响应返回。

        Args:
            message:     用户输入的消息文本
            attachments: 附件列表（可选）
        """
        if hasattr(self.chat_widget, "set_input_enabled"):
            self.chat_widget.set_input_enabled(False)
        if hasattr(self.trace_widget, "clear"):
            self.trace_widget.clear()

        self._current_worker = AgentWorker(
            session_id=self._session_id,
            user_id=self._user_id,
            message=message,
            attachments=attachments or [],
            stream_trace=True,
        )
        self._current_worker.trace_streamed.connect(self._on_trace_streamed)
        self._current_worker.response_ready.connect(self._on_agent_response)
        self._current_worker.error_occurred.connect(self._on_agent_error)
        self._current_worker.start()

    @pyqtSlot(dict)
    def _on_trace_streamed(self, trace_item: dict) -> None:
        if hasattr(self.trace_widget, "append_trace"):
            self.trace_widget.append_trace(trace_item)

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
        if hasattr(self.chat_widget, "set_input_enabled"):
            self.chat_widget.set_input_enabled(True)

        assistant = response.get("assistant_message") or {}
        if isinstance(assistant, dict):
            content = str(assistant.get("content", "")).strip()
            if content and hasattr(self.chat_widget, "add_message"):
                self.chat_widget.add_message("assistant", content)

        trace_items = response.get("trace", [])
        if isinstance(trace_items, list):
            self.trace_widget.update_trace(trace_items)

        route = response.get("route")
        if route == "scheduler":
            self.center_tabs.setCurrentWidget(self.schedule_widget)
        elif route == "encyclopedia":
            self.center_tabs.setCurrentWidget(self.encyclopedia_widget)
        elif route == "chat":
            self.center_tabs.setCurrentWidget(self.chat_widget)

        ui_payload = response.get("ui_payload") or {}
        schedule_data = ui_payload.get("schedule")
        encyclopedia_data = ui_payload.get("encyclopedia")

        if schedule_data and hasattr(self.schedule_widget, "update_schedule"):
            self.schedule_widget.update_schedule(schedule_data)
        if encyclopedia_data and hasattr(self.encyclopedia_widget, "show_result"):
            self.encyclopedia_widget.show_result(encyclopedia_data)

        hitl_request = response.get("hitl_request")
        if isinstance(hitl_request, dict):
            self._show_hitl_dialog(hitl_request)

    @pyqtSlot(str)
    def _on_agent_error(self, error_msg: str) -> None:
        """AgentWorker 报错时，在 ChatWidget 中显示错误消息。"""
        if hasattr(self.chat_widget, "set_input_enabled"):
            self.chat_widget.set_input_enabled(True)
        if hasattr(self.chat_widget, "add_message"):
            self.chat_widget.add_message("assistant", f"[Error] {error_msg}")

    def _show_hitl_dialog(self, hitl_request: dict) -> None:
        """
        弹出 HITLDialog，连接 approved/rejected signal。
        用户操作后通过 AgentWorker 发送 hitl_reply 请求。
        """
        dialog = HITLDialog(hitl_request, parent=self)
        dialog.approved.connect(lambda req_id: self._send_hitl_reply(req_id, True))
        dialog.rejected.connect(lambda req_id: self._send_hitl_reply(req_id, False))
        dialog.exec()

    def _send_hitl_reply(self, request_id: str, approved: bool) -> None:
        """
        HITL 审批后，复用 AgentWorker 发送审批结果。

        Args:
            request_id: hitl_request.request_id
            approved:   用户批准结果
        """
        self._current_worker = AgentWorker(
            session_id=self._session_id,
            user_id=self._user_id,
            message="",
            hitl_reply={"request_id": request_id, "approved": approved},
            stream_trace=True,
        )
        self._current_worker.trace_streamed.connect(self._on_trace_streamed)
        self._current_worker.response_ready.connect(self._on_agent_response)
        self._current_worker.error_occurred.connect(self._on_agent_error)
        self._current_worker.start()
