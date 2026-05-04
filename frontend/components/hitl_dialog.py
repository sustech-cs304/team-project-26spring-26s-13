"""
Frontend Relevant/components/hitl_dialog.py
HITL 高风险操作授权弹窗。
收到后端返回的 hitl_request 时，由 DashboardPage 调用此弹窗。
用户点击后，通过 Signal 将审批结果回传给调用方。
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QWidget,
)


class HITLDialog(QDialog):
    """
    弹窗展示高风险操作详情，等待用户明确批准或拒绝。

    Signals:
        approved(request_id: str):  用户点击"批准"时 emit
        rejected(request_id: str):  用户点击"拒绝"时 emit
    """

    approved = pyqtSignal(str)  # str = request_id
    rejected = pyqtSignal(str)  # str = request_id

    def __init__(self, hitl_request: dict, parent: QWidget | None = None) -> None:
        """
        Args:
            hitl_request: AgentResponse.hitl_request dict，包含：
                          request_id, action, risk, reason, payload
            parent:       父 QWidget
        """
        super().__init__(parent)
        self._request_id: str = hitl_request["request_id"]
        self._setup_ui(hitl_request)

    def _setup_ui(self, req: dict) -> None:
        """
        构建弹窗 UI：风险等级标签、操作描述、原因说明、子操作列表、批准/拒绝按钮。

        布局结构：
          QVBoxLayout
          ├── QLabel  (风险等级，高危时红色)
          ├── QLabel  (操作名称)
          ├── QLabel  (原因说明)
          ├── QListWidget (payload 子操作列表，只读)
          └── QDialogButtonBox (批准 / 拒绝)
        """
        self.setWindowTitle("Action Authorization Required")
        layout = QVBoxLayout(self)

        risk = str(req.get("risk", "medium")).lower()
        risk_label = QLabel(f"Risk: {risk}", self)
        if risk == "high":
            risk_label.setStyleSheet("color: #d9534f; font-weight: 600;")
        layout.addWidget(risk_label)

        action = str(req.get("action", ""))
        reason = str(req.get("reason", ""))
        layout.addWidget(QLabel(f"Action: {action}", self))
        layout.addWidget(QLabel(f"Reason: {reason}", self))

        payload_list = QListWidget(self)
        for line in req.get("payload", []) or []:
            payload_list.addItem(str(line))
        layout.addWidget(payload_list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No,
            self,
        )
        yes_btn = buttons.button(QDialogButtonBox.StandardButton.Yes)
        no_btn = buttons.button(QDialogButtonBox.StandardButton.No)
        if yes_btn is not None:
            yes_btn.setText("Approve")
        if no_btn is not None:
            no_btn.setText("Reject")
        buttons.accepted.connect(self._on_approve)
        buttons.rejected.connect(self._on_reject)
        layout.addWidget(buttons)

    def _on_approve(self) -> None:
        """用户点击批准：emit approved signal，关闭弹窗。"""
        self.approved.emit(self._request_id)
        self.accept()

    def _on_reject(self) -> None:
        """用户点击拒绝：emit rejected signal，关闭弹窗。"""
        self.rejected.emit(self._request_id)
        self.reject()
