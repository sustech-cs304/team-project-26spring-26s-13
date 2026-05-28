"""
Frontend Relevant/components/trace_widget.py
Agent trace component: displays streamed execution steps.
"""

from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget


class TraceWidget(QWidget):
    """
    展示 Agent 每个执行步骤的 phase、title、detail 和 status。
    每次 Agent 响应返回时整体刷新（非流式，当前版本）。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """
        布局：
          QVBoxLayout
          ├── QLabel "Agent Trace"（标题）
          └── QListWidget（trace 步骤列表，只读）
        """
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Agent Trace"))
        self._list = QListWidget(self)
        self._list.setAlternatingRowColors(True)
        layout.addWidget(self._list)

    def update_trace(self, trace_items: list[dict]) -> None:
        """
        用新的 trace 数据整体刷新面板内容。
        每个 TraceItem 显示为一行："{phase} | {title} [{status}]"，展开后显示 detail。

        Args:
            trace_items: AgentResponse.trace 列表，每项包含
                         phase, title, detail, status, timestamp
        """
        self._list.clear()
        for item in trace_items:
            self.append_trace(item)

    def append_trace(self, trace_item: dict) -> None:
        """
        追加一条 trace（流式模式）。
        """
        phase = str(trace_item.get("phase", "Observation"))
        title = str(trace_item.get("title", ""))
        status = str(trace_item.get("status", "pending"))
        detail = str(trace_item.get("detail", ""))
        text = f"[{phase}] {title} ({status})"
        item = QListWidgetItem(text)
        if detail:
            item.setToolTip(detail)
        self._list.addItem(item)
        self._list.scrollToBottom()

    def clear(self) -> None:
        """清空 trace 面板（发送新消息时调用）。"""
        self._list.clear()
