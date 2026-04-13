"""
God Xun-Frontend/components/trace_widget.py
Thought Trace 面板：实时展示 Agent 的推理步骤。
"""

from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget


class TraceWidget(QWidget):
    """
    右侧 Thought Trace 面板，展示 Agent 每个推理步骤的 phase、title、detail 和 status。
    每次 Agent 响应返回时整体刷新（非流式，当前版本）。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # TODO: self._setup_ui()

    def _setup_ui(self) -> None:
        """
        布局：
          QVBoxLayout
          ├── QLabel "Thought Trace"（标题）
          └── QListWidget（trace 步骤列表，只读）
        """
        # TODO
        raise NotImplementedError

    def update_trace(self, trace_items: list[dict]) -> None:
        """
        用新的 trace 数据整体刷新面板内容。
        每个 TraceItem 显示为一行："{phase} | {title} [{status}]"，展开后显示 detail。

        Args:
            trace_items: AgentResponse.trace 列表，每项包含
                         phase, title, detail, status, timestamp
        """
        # TODO:
        # self._list.clear()
        # for item in trace_items:
        #     text = f"[{item['phase']}] {item['title']} ({item['status']})"
        #     list_item = QListWidgetItem(text)
        #     list_item.setToolTip(item.get("detail", ""))
        #     self._list.addItem(list_item)
        raise NotImplementedError

    def clear(self) -> None:
        """清空 trace 面板（发送新消息时调用）。"""
        # TODO: self._list.clear()
        raise NotImplementedError
