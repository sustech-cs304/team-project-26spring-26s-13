"""
Frontend Relevant/components/chat_widget.py
主聊天区组件：展示对话历史，提供消息输入框。
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)


class ChatWidget(QWidget):
    """
    聊天区，包含消息列表和输入框。

    Signals:
        message_submitted(message: str, attachments: list[dict]):
            用户点击发送或按回车时 emit，由 DashboardPage 接收后创建 AgentWorker。
    """

    message_submitted = pyqtSignal(str, list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # TODO: self._setup_ui()

    def _setup_ui(self) -> None:
        """
        布局：
          QVBoxLayout
          ├── QListWidget  (消息历史，只读，自动滚动到底部)
          └── QHBoxLayout  (输入框 + 附件按钮 + 发送按钮)
        """
        # TODO
        raise NotImplementedError

    def add_message(self, role: str, content: str) -> None:
        """
        向消息列表追加一条消息。
        user 消息右对齐，assistant 消息左对齐（通过 Qt.AlignmentFlag 控制）。

        Args:
            role:    "user" 或 "assistant"
            content: 消息文本（支持简单 Markdown，或使用 QLabel 渲染）
        """
        # TODO
        raise NotImplementedError

    def load_history(self, messages: list[dict]) -> None:
        """
        批量加载历史消息（bootstrap 时调用）。

        Args:
            messages: chat_history list，每项包含 role, content
        """
        # TODO: for msg in messages: self.add_message(msg["role"], msg["content"])
        raise NotImplementedError

    def set_input_enabled(self, enabled: bool) -> None:
        """等待 Agent 响应时禁用输入框和发送按钮，响应返回后恢复。"""
        # TODO
        raise NotImplementedError

    def _on_send(self) -> None:
        """
        发送按钮点击处理：
        1. 读取输入框内容
        2. 立即在 ChatWidget 中显示用户消息
        3. 清空输入框，禁用输入
        4. emit message_submitted
        """
        # TODO
        raise NotImplementedError
