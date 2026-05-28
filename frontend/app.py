"""PyQt6 desktop frontend for the Student Productivity Agent project."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
from pathlib import Path
import re
import sys
from typing import Any
from uuid import uuid4

from PyQt6.QtCore import (
    QDate,
    QEvent,
    QObject,
    QPoint,
    QSize,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
    QRadialGradient,
    QTextCharFormat,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCalendarWidget,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from .api_client import BackendApiClient, BackendApiError
    from .i18n import UI_TEXTS
    from .schedule_utils import (
        event_sort_key,
        events_by_date,
        format_event_time,
        next_event_date,
    )
    from .styles import APP_STYLE
except ImportError:
    from api_client import BackendApiClient, BackendApiError  # type: ignore
    from i18n import UI_TEXTS  # type: ignore
    from schedule_utils import event_sort_key, events_by_date, format_event_time, next_event_date  # type: ignore
    from styles import APP_STYLE  # type: ignore


APP_TITLE = {
    "en": "Student Productivity Agent",
    "zh": "学生生产力助手",
}

HOME_CORE_FEATURES = [
    {
        "title": {"en": "Agentic Loop", "zh": "智能体循环"},
        "detail": {
            "en": "Turn natural language goals into reasoning, tool use, observation, and self-correction.",
            "zh": "把自然语言目标转成推理、工具调用、观察反馈和自我修正流程。",
        },
    },
    {
        "title": {"en": "Schedule Intelligence", "zh": "日程智能"},
        "detail": {
            "en": "Sync Blackboard deadlines and local plans, then surface conflicts before they hurt your week.",
            "zh": "同步 Blackboard 截止时间和本地计划，提前发现冲突，不让它们打乱一周安排。",
        },
    },
    {
        "title": {"en": "Campus Knowledge", "zh": "校园知识检索"},
        "detail": {
            "en": "Search handbook-style content with RAG answers, citations, and a fast student-friendly interface.",
            "zh": "用 RAG 检索校园手册内容，返回带引用的答案，并通过更适合学生使用的界面呈现。",
        },
    },
]

HOME_SKILLS = [
    {
        "icon": "CHAT",
        "title": {"en": "Main Chat", "zh": "主聊天区"},
        "detail": {
            "en": "A chat-first workspace for tasks, questions, and tool-driven execution.",
            "zh": "围绕任务、提问和工具执行组织的聊天式主工作区。",
        },
    },
    {
        "icon": "MAIL",
        "title": {"en": "Email Delivery", "zh": "邮件发送"},
        "detail": {
            "en": "Send summaries, task results, and exported conversations to the user's SUSTech mailbox.",
            "zh": "将对话总结、任务结果和导出的会话发送到用户的南科大邮箱。",
        },
    },
    {
        "icon": "HITL",
        "title": {"en": "Safe Approval", "zh": "安全授权"},
        "detail": {
            "en": "Intercept high-risk file and schedule actions before the agent executes them.",
            "zh": "在智能体执行高风险文件或日程操作前先进行人工授权。",
        },
    },
    {
        "icon": "SYNC",
        "title": {"en": "Scheduler", "zh": "日程同步"},
        "detail": {
            "en": "Combine Blackboard, campus events, and personal tasks into one dashboard.",
            "zh": "把 Blackboard、校历事件和个人任务汇总到一个日程仪表盘中。",
        },
    },
    {
        "icon": "RAG",
        "title": {"en": "Campus QA", "zh": "校园问答"},
        "detail": {
            "en": "Use handbook retrieval and citations to answer degree, dorm, and policy questions.",
            "zh": "通过手册检索和引用回答学分、宿舍、政策等校园问题。",
        },
    },
    {
        "icon": "FILES",
        "title": {"en": "Study Copilot", "zh": "学习辅助"},
        "detail": {
            "en": "Prepare for uploaded notes, slides, and documents to become future study tools.",
            "zh": "为后续接入讲义、课件和文档解析打下基础，支持学习辅助功能。",
        },
    },
]

HOME_BANNER = {
    "title": {
        "en": "Plan, search, and act from one student workspace",
        "zh": "在一个学生工作台里完成计划、检索与执行",
    },
    "detail": {
        "en": "Start from the homepage, sign in, and move into a dashboard built for agent workflows instead of a generic chat box.",
        "zh": "从主页进入登录，再进入一个围绕 agent workflow 设计的主控制台，而不只是普通聊天框。",
    },
}

PROFILE = {
    "name": {"en": "SUSTech Student", "zh": "南科大学生"},
    "major": {"en": "Software Engineering", "zh": "软件工程"},
    "focus": {
        "en": "Schedule planning, campus QA, study support",
        "zh": "日程规划、校园问答、学习辅助",
    },
}

HITL_REQUEST = {
    "action": {"en": "Pending Action", "zh": "待处理操作"},
    "risk": {"en": "low", "zh": "低"},
    "reason": {"en": "No reason provided", "zh": "未提供原因"},
}


class ApiWorker(QThread):
    """Run a single blocking API call on a background thread and emit the result."""

    finished = pyqtSignal(object)
    errored = pyqtSignal(str)

    def __init__(self, fn, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            result = self._fn()
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.errored.emit(str(exc))


class AgentStreamWorker(QThread):
    finished = pyqtSignal(object)
    errored = pyqtSignal(str)
    trace_streamed = pyqtSignal(dict)

    def __init__(
        self,
        client: "BackendApiClient",
        *,
        user_id: str,
        session_id: str,
        message: str,
        attachments: list[dict[str, Any]] | None = None,
        hitl_reply: dict[str, Any] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._user_id = user_id
        self._session_id = session_id
        self._message = message
        self._attachments = attachments or []
        self._hitl_reply = hitl_reply

    def run(self) -> None:
        try:

            def on_event(event: dict[str, Any]) -> None:
                if event.get("event") != "trace":
                    return
                data = event.get("data")
                if isinstance(data, dict):
                    self.trace_streamed.emit(data)

            result = self._client.run_agent_stream(
                user_id=self._user_id,
                session_id=self._session_id,
                message=self._message,
                attachments=self._attachments,
                hitl_reply=self._hitl_reply,
                on_event=on_event,
            )
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.errored.emit(str(exc))


class BlackboardSyncDialog(QDialog):
    cancelled = pyqtSignal()

    def __init__(
        self, title: str, cancel_label: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self._cancel_button = QPushButton(cancel_label)
        self._cancel_button.clicked.connect(self.cancelled.emit)
        button_row.addWidget(self._cancel_button)

        layout.addWidget(self._status_label)
        layout.addWidget(self._progress)
        layout.addLayout(button_row)

    def set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def set_progress(self, processed: int, total: int | None) -> None:
        if total is None or total <= 0:
            self._progress.setRange(0, 0)
            return
        self._progress.setRange(0, total)
        self._progress.setValue(max(0, min(processed, total)))

    def set_cancellable(self, enabled: bool) -> None:
        self._cancel_button.setEnabled(enabled)


def localized(value, language: str):
    """Resolve bilingual values into a concrete string/list for the current language."""
    if isinstance(value, dict) and "en" in value and "zh" in value:
        return value[language]
    return value


class StarfieldBackground(QWidget):
    """Paint a subtle animated starfield behind the PyQt interface."""

    def __init__(self) -> None:
        super().__init__()
        self._phase = 0.0
        self._stars: list[tuple[float, float, float, int, float]] = []
        for index in range(150):
            x = ((index * 73) % 997) / 997
            y = ((index * 191) % 991) / 991
            radius = 0.8 + ((index * 17) % 4) * 0.32
            alpha = 55 + ((index * 43) % 130)
            phase = ((index * 29) % 360) * math.pi / 180
            self._stars.append((x, y, radius, alpha, phase))

        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.055) % (math.pi * 2)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width = max(1, self.width())
        height = max(1, self.height())

        sky = QLinearGradient(0, 0, width, height)
        sky.setColorAt(0.0, QColor("#020611"))
        sky.setColorAt(0.45, QColor("#071323"))
        sky.setColorAt(1.0, QColor("#0b1025"))
        painter.fillRect(self.rect(), sky)

        for cx, cy, radius, color in (
            (width * 0.18, height * 0.14, width * 0.42, QColor(34, 211, 238, 32)),
            (width * 0.75, height * 0.28, width * 0.38, QColor(139, 92, 246, 30)),
            (width * 0.50, height * 0.86, width * 0.46, QColor(59, 130, 246, 22)),
        ):
            nebula = QRadialGradient(cx, cy, radius)
            nebula.setColorAt(0.0, color)
            nebula.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(nebula))
            painter.drawEllipse(
                int(cx - radius),
                int(cy - radius),
                int(radius * 2),
                int(radius * 2),
            )

        for x, y, star_radius, alpha, phase in self._stars:
            twinkle = 0.62 + 0.38 * math.sin(self._phase + phase)
            star_alpha = max(18, min(210, int(alpha * twinkle)))
            color = QColor(225, 242, 255, star_alpha)
            painter.setPen(QPen(color, star_radius))
            painter.drawPoint(int(x * width), int(y * height))

        painter.setPen(QPen(QColor(34, 211, 238, 18), 1))
        for index in range(0, 42, 3):
            first = self._stars[index]
            second = self._stars[(index + 17) % len(self._stars)]
            painter.drawLine(
                int(first[0] * width),
                int(first[1] * height),
                int(second[0] * width),
                int(second[1] * height),
            )


class InfoCard(QFrame):
    def __init__(self, title: str, body: str, object_name: str = "PanelCard") -> None:
        super().__init__()
        self.setObjectName(object_name)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        body_label = QLabel(body)
        body_label.setObjectName("BodyText")
        body_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(body_label)


class InlineTracePanel(QWidget):
    """Collapsible '思考过程' section rendered inside an agent message card."""

    def __init__(self) -> None:
        super().__init__()
        self._expanded = False
        self._trace_widgets: list[QFrame] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toggle header row ─────────────────────────────────────────────────
        toggle_btn = QPushButton()
        toggle_btn.setObjectName("TraceToggleButton")
        toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle_btn.setFlat(True)
        toggle_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        toggle_btn.setFixedHeight(36)
        self._toggle_btn = toggle_btn
        self._update_toggle_label()
        toggle_btn.clicked.connect(self._toggle)
        root.addWidget(toggle_btn)

        # ── Collapsible body ──────────────────────────────────────────────────
        self._body = QWidget()
        self._body.setObjectName("TraceInlineBody")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 6, 0, 0)
        self._body_layout.setSpacing(6)
        self._body.setVisible(False)
        root.addWidget(self._body)

    # ── Public API ────────────────────────────────────────────────────────────
    def set_trace_events(self, events: list[dict[str, str]], status_fn) -> None:
        """Rebuild body with the given trace event dicts."""
        # Clear existing
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._trace_widgets.clear()

        for event in events:
            item_frame = QFrame()
            item_frame.setObjectName(
                f"TraceItem{event.get('status', 'pending').capitalize()}"
            )
            item_layout = QVBoxLayout(item_frame)
            item_layout.setContentsMargins(12, 8, 12, 8)
            item_layout.setSpacing(3)

            phase_lbl = QLabel(
                f"{event.get('phase', '')}  ·  {status_fn(event.get('status', 'pending'))}"
            )
            phase_lbl.setObjectName("CardTitle")
            title_lbl = QLabel(event.get("title", ""))
            title_lbl.setObjectName("SectionTitle")
            detail_lbl = QLabel(event.get("detail", ""))
            detail_lbl.setObjectName("MutedText")
            detail_lbl.setWordWrap(True)

            item_layout.addWidget(phase_lbl)
            item_layout.addWidget(title_lbl)
            if event.get("detail", "").strip():
                item_layout.addWidget(detail_lbl)

            self._body_layout.addWidget(item_frame)
            self._trace_widgets.append(item_frame)

        self._update_toggle_label()
        self.setVisible(bool(events))

    # ── Private ───────────────────────────────────────────────────────────────
    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._update_toggle_label()

    def _update_toggle_label(self) -> None:
        n = len(self._trace_widgets)
        chevron = "∧" if self._expanded else "∨"
        if n == 0:
            txt = f"✦  思考过程  {chevron}"
        else:
            txt = f"✦  查看思考过程（{n} 步）  {chevron}"
        self._toggle_btn.setText(txt)


_SPINNER_FRAMES = ["|", "/", "-", "\\"]


class ThinkingIndicator(QWidget):
    """Animated 'thinking' bubble shown while waiting for the agent."""

    def __init__(self, sender_label: str) -> None:
        super().__init__()
        now = datetime.now(timezone.utc).astimezone().strftime("%H:%M")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 8, 24, 8)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("AgentMessageCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 14, 18, 14)
        card_layout.setSpacing(10)

        header = QLabel(f"{sender_label}  ·  {now}")
        header.setObjectName("BubbleTimeLabel")
        card_layout.addWidget(header)

        self._spinner_label = QLabel()
        self._spinner_label.setObjectName("AgentMessageText")
        self._frame = 0
        self._update_text()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(80)

        card_layout.addWidget(self._spinner_label)
        outer.addWidget(card)
        outer.addSpacing(12)

    def _tick(self) -> None:
        self._frame = (self._frame + 1) % len(_SPINNER_FRAMES)
        self._update_text()

    def _update_text(self) -> None:
        self._spinner_label.setText(f"{_SPINNER_FRAMES[self._frame]}  Thinking...")


class BubbleWidget(QWidget):
    def __init__(
        self, sender: str, sender_label: str, text: str, message_type_label: str
    ) -> None:
        super().__init__()
        now = datetime.now(timezone.utc).astimezone().strftime("%H:%M")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 8, 24, 8)
        outer.setSpacing(0)

        if sender == "user":
            # ── User: flat, no card, left-aligned ────────────────────────────
            header = QLabel(f"{sender_label}  ·  {now}")
            header.setObjectName("BubbleTimeLabel")

            text_label = QLabel(text)
            text_label.setObjectName("UserMessageText")
            text_label.setWordWrap(True)
            text_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )

            outer.addWidget(header)
            outer.addSpacing(6)
            outer.addWidget(text_label)
            outer.addSpacing(16)
            self._trace_panel: InlineTracePanel | None = None

        else:
            # ── Agent: subtle bordered card, left-aligned ─────────────────────
            card = QFrame()
            card.setObjectName("AgentMessageCard")
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 14, 18, 14)
            card_layout.setSpacing(10)

            header = QLabel(f"{sender_label}  ·  {now}")
            header.setObjectName("BubbleTimeLabel")
            card_layout.addWidget(header)

            # Inline collapsible trace panel (hidden until events are supplied)
            self._trace_panel = InlineTracePanel()
            self._trace_panel.setVisible(False)
            card_layout.addWidget(self._trace_panel)

            text_label = QLabel(text)
            text_label.setObjectName("AgentMessageText")
            text_label.setWordWrap(True)
            text_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            card_layout.addWidget(text_label)

            outer.addWidget(card)
            outer.addSpacing(12)

    def set_trace_events(self, events: list[dict[str, str]], status_fn) -> None:
        """Push trace events into the embedded InlineTracePanel (agent only)."""
        if self._trace_panel is not None:
            self._trace_panel.set_trace_events(events, status_fn)


class ScheduleResultWidget(QWidget):
    def __init__(
        self,
        sender_label: str,
        title: str,
        intro: str,
        events: list[dict[str, str]],
        conflicts: list[dict[str, str]],
        texts: dict[str, str],
    ) -> None:
        super().__init__()
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 10)

        card = QFrame()
        card.setObjectName("AgentResultCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        sender_title = QLabel(sender_label)
        sender_title.setObjectName("CardTitle")
        type_chip = QLabel(texts["message_type_schedule"])
        type_chip.setObjectName("MessageTypeChip")
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        intro_label = QLabel(intro)
        intro_label.setObjectName("BodyText")
        intro_label.setWordWrap(True)

        header_row.addWidget(sender_title)
        header_row.addWidget(type_chip)
        header_row.addStretch(1)
        layout.addLayout(header_row)
        layout.addWidget(title_label)
        if intro.strip():
            layout.addWidget(intro_label)

        if events:
            events_title = QLabel(texts["chat_schedule_events_section"])
            events_title.setObjectName("CardTitle")
            layout.addWidget(events_title)
            for event in events[:3]:
                event_card = QFrame()
                event_card.setObjectName("ResultSubCard")
                event_layout = QVBoxLayout(event_card)
                event_layout.setContentsMargins(12, 10, 12, 10)
                event_layout.setSpacing(4)
                event_title = QLabel(event["title"])
                event_title.setObjectName("SectionTitle")
                event_meta = QLabel(f"{event['time']}  |  {event['source']}")
                event_meta.setObjectName("MutedText")
                event_detail = QLabel(event["detail"])
                event_detail.setObjectName("BodyText")
                event_detail.setWordWrap(True)
                event_layout.addWidget(event_title)
                event_layout.addWidget(event_meta)
                event_layout.addWidget(event_detail)
                layout.addWidget(event_card)

        if conflicts:
            conflicts_title = QLabel(texts["chat_schedule_conflicts_section"])
            conflicts_title.setObjectName("CardTitle")
            layout.addWidget(conflicts_title)
            for conflict in conflicts[:3]:
                conflict_card = QFrame()
                conflict_card.setObjectName("MiniConflictCard")
                conflict_layout = QVBoxLayout(conflict_card)
                conflict_layout.setContentsMargins(12, 10, 12, 10)
                conflict_layout.setSpacing(4)
                conflict_title = QLabel(conflict["title"])
                conflict_title.setObjectName("SectionTitle")
                conflict_detail = QLabel(conflict["detail"])
                conflict_detail.setObjectName("BodyText")
                conflict_detail.setWordWrap(True)
                conflict_layout.addWidget(conflict_title)
                conflict_layout.addWidget(conflict_detail)
                layout.addWidget(conflict_card)

        outer.addWidget(card, 1)


class EncyclopediaResultWidget(QWidget):
    def __init__(
        self,
        sender_label: str,
        title: str,
        intro: str,
        query: str,
        answer_markdown: str,
        citations: list[str],
        texts: dict[str, str],
    ) -> None:
        super().__init__()
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 10)

        card = QFrame()
        card.setObjectName("AgentResultCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        sender_title = QLabel(sender_label)
        sender_title.setObjectName("CardTitle")
        type_chip = QLabel(texts["message_type_encyclopedia"])
        type_chip.setObjectName("MessageTypeChip")
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        intro_label = QLabel(intro)
        intro_label.setObjectName("BodyText")
        intro_label.setWordWrap(True)
        query_label = QLabel(query)
        query_label.setObjectName("ResultQueryLabel")
        query_label.setWordWrap(True)

        answer_title = QLabel(texts["chat_encyclopedia_answer_section"])
        answer_title.setObjectName("CardTitle")
        answer_browser = QTextBrowser()
        answer_browser.setObjectName("ResultMarkdown")
        answer_browser.setOpenExternalLinks(False)
        answer_browser.setMarkdown(answer_markdown)
        answer_browser.setMinimumHeight(150)
        answer_browser.setMaximumHeight(240)

        header_row.addWidget(sender_title)
        header_row.addWidget(type_chip)
        header_row.addStretch(1)
        layout.addLayout(header_row)
        layout.addWidget(title_label)
        if intro.strip():
            layout.addWidget(intro_label)
        if query.strip():
            layout.addWidget(query_label)
        layout.addWidget(answer_title)
        layout.addWidget(answer_browser)

        if citations:
            citations_title = QLabel(texts["chat_encyclopedia_sources_section"])
            citations_title.setObjectName("CardTitle")
            layout.addWidget(citations_title)
            for citation in citations[:4]:
                citation_label = QLabel(f"- {citation}")
                citation_label.setObjectName("MutedText")
                citation_label.setWordWrap(True)
                layout.addWidget(citation_label)

        outer.addWidget(card, 1)


class LibraryResultWidget(QWidget):
    def __init__(
        self,
        sender_label: str,
        title: str,
        intro: str,
        query_time: str,
        query_location: str,
        query_capacity: Any,
        rooms: list[dict[str, Any]],
        texts: dict[str, str],
    ) -> None:
        super().__init__()
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 10)

        card = QFrame()
        card.setObjectName("AgentResultCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        sender_title = QLabel(sender_label)
        sender_title.setObjectName("CardTitle")
        type_chip = QLabel(texts["message_type_library"])
        type_chip.setObjectName("MessageTypeChip")
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        intro_label = QLabel(intro)
        intro_label.setObjectName("BodyText")
        intro_label.setWordWrap(True)

        capacity_text = (
            texts["library_capacity_any"]
            if not query_capacity
            else texts["library_capacity_min"].format(capacity=query_capacity)
        )
        query_label = QLabel(
            texts["chat_library_query_line"].format(
                time=query_time or texts["library_time_any"],
                location=query_location or texts["library_location_any"],
                capacity=capacity_text,
                count=len(rooms),
            )
        )
        query_label.setObjectName("ResultQueryLabel")
        query_label.setWordWrap(True)

        header_row.addWidget(sender_title)
        header_row.addWidget(type_chip)
        header_row.addStretch(1)
        layout.addLayout(header_row)
        layout.addWidget(title_label)
        if intro.strip():
            layout.addWidget(intro_label)
        layout.addWidget(query_label)

        if rooms:
            rooms_title = QLabel(texts["chat_library_rooms_section"])
            rooms_title.setObjectName("CardTitle")
            layout.addWidget(rooms_title)
            for room in rooms[:5]:
                room_card = QFrame()
                room_card.setObjectName("ResultSubCard")
                room_layout = QVBoxLayout(room_card)
                room_layout.setContentsMargins(12, 10, 12, 10)
                room_layout.setSpacing(4)

                room_name = str(
                    room.get("room_name") or room.get("room_id") or "Library room"
                )
                location = str(room.get("location") or "")
                capacity = room.get("capacity") or texts["library_capacity_unknown"]
                slots = room.get("time_slots") or []
                slot_text = " · ".join(str(slot) for slot in slots)

                room_title = QLabel(room_name)
                room_title.setObjectName("SectionTitle")
                room_meta = QLabel(
                    texts["chat_library_room_meta"].format(
                        location=location or texts["library_location_unknown"],
                        capacity=capacity,
                    )
                )
                room_meta.setObjectName("MutedText")
                room_slots = QLabel(
                    texts["chat_library_room_slots"].format(slots=slot_text)
                )
                room_slots.setObjectName("BodyText")
                room_slots.setWordWrap(True)
                room_layout.addWidget(room_title)
                room_layout.addWidget(room_meta)
                room_layout.addWidget(room_slots)
                layout.addWidget(room_card)
        else:
            empty_label = QLabel(texts["chat_library_no_rooms"])
            empty_label.setObjectName("MutedText")
            empty_label.setWordWrap(True)
            layout.addWidget(empty_label)

        outer.addWidget(card, 1)


class TraceItem(QFrame):
    def __init__(
        self,
        phase: str,
        title: str,
        detail: str,
        status: str,
        status_label: str,
    ) -> None:
        super().__init__()
        self.setObjectName(f"TraceItem{status.capitalize()}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(5)

        phase_label = QLabel(f"{phase}  |  {status_label}")
        phase_label.setObjectName("CardTitle")
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        detail_label = QLabel(detail)
        detail_label.setObjectName("MutedText")
        detail_label.setWordWrap(True)

        layout.addWidget(phase_label)
        layout.addWidget(title_label)
        layout.addWidget(detail_label)


class HitlDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        texts: dict[str, str],
        request_payload: dict[str, str | list[str]],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(texts["hitl_dialog_title"])
        self.setMinimumWidth(520)
        self.setStyleSheet(APP_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        title = QLabel(str(request_payload["action"]))
        title.setObjectName("TitleLabel")
        risk = QLabel(texts["risk_level"].format(risk=request_payload["risk"]))
        risk.setObjectName("SubtitleLabel")
        reason = QLabel(str(request_payload["reason"]))
        reason.setObjectName("BodyText")
        reason.setWordWrap(True)

        payload_card = QFrame()
        payload_card.setObjectName("PanelCard")
        payload_layout = QVBoxLayout(payload_card)
        payload_layout.setContentsMargins(16, 14, 16, 14)
        payload_layout.setSpacing(8)
        payload_title = QLabel(texts["planned_changes"])
        payload_title.setObjectName("SectionTitle")
        payload_layout.addWidget(payload_title)

        for item in request_payload["payload"]:
            bullet = QLabel(f"- {item}")
            bullet.setObjectName("BodyText")
            bullet.setWordWrap(True)
            payload_layout.addWidget(bullet)

        button_row = QHBoxLayout()
        reject_button = QPushButton(texts["reject"])
        approve_button = QPushButton(texts["approve_once"])
        approve_button.setObjectName("PrimaryButton")
        reject_button.clicked.connect(self.reject)
        approve_button.clicked.connect(self.accept)
        button_row.addStretch(1)
        button_row.addWidget(reject_button)
        button_row.addWidget(approve_button)

        layout.addWidget(title)
        layout.addWidget(risk)
        layout.addWidget(reason)
        layout.addWidget(payload_card)
        layout.addLayout(button_row)


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        texts: dict[str, str],
        cas_state: dict[str, Any],
        api_state: dict[str, Any],
        workdir_state: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self.texts = texts
        self.intent: str | None = None
        _workdir = workdir_state or {}

        self.setWindowTitle(texts["settings_dialog_title"])
        self.setMinimumWidth(620)
        self.setStyleSheet(APP_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        title = QLabel(texts["settings_dialog_title"])
        title.setObjectName("TitleLabel")
        subtitle = QLabel(texts["settings_dialog_subtitle"])
        subtitle.setObjectName("SubtitleLabel")
        subtitle.setWordWrap(True)

        cas_card = QFrame()
        cas_card.setObjectName("PanelCard")
        cas_layout = QVBoxLayout(cas_card)
        cas_layout.setContentsMargins(16, 16, 16, 16)
        cas_layout.setSpacing(10)
        cas_title = QLabel(texts["settings_cas_title"])
        cas_title.setObjectName("SectionTitle")
        cas_body = QLabel(texts["settings_cas_body"])
        cas_body.setObjectName("MutedText")
        cas_body.setWordWrap(True)
        cas_form = QFormLayout()
        cas_form.setContentsMargins(0, 0, 0, 0)
        cas_form.setSpacing(10)
        self.cas_account_input = QLineEdit(str(cas_state.get("username", "")))
        self.cas_password_input = QLineEdit(str(cas_state.get("password", "")))
        self.cas_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        cas_form.addRow(texts["settings_cas_account"], self.cas_account_input)
        cas_form.addRow(texts["settings_cas_password"], self.cas_password_input)
        cas_button = QPushButton(texts["settings_save_cas"])
        cas_button.setObjectName("PrimaryButton")
        cas_button.clicked.connect(self._accept_cas)
        cas_layout.addWidget(cas_title)
        cas_layout.addWidget(cas_body)
        cas_layout.addLayout(cas_form)
        cas_layout.addWidget(cas_button, 0, Qt.AlignmentFlag.AlignLeft)

        api_card = QFrame()
        api_card.setObjectName("PanelCard")
        api_layout = QVBoxLayout(api_card)
        api_layout.setContentsMargins(16, 16, 16, 16)
        api_layout.setSpacing(10)
        api_title = QLabel(texts["settings_api_title"])
        api_title.setObjectName("SectionTitle")
        api_body = QLabel(texts["settings_api_body"])
        api_body.setObjectName("MutedText")
        api_body.setWordWrap(True)
        api_form = QFormLayout()
        api_form.setContentsMargins(0, 0, 0, 0)
        api_form.setSpacing(10)
        self.api_key_input = QLineEdit(str(api_state.get("api_key", "")))
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_form.addRow(texts["settings_api_key"], self.api_key_input)
        api_button = QPushButton(texts["settings_save_api"])
        api_button.setObjectName("PrimaryButton")
        api_button.clicked.connect(self._accept_api)
        api_layout.addWidget(api_title)
        api_layout.addWidget(api_body)
        api_layout.addLayout(api_form)
        api_layout.addWidget(api_button, 0, Qt.AlignmentFlag.AlignLeft)

        # ── Working Directory card ──────────────────────────────────────────
        workdir_card = QFrame()
        workdir_card.setObjectName("PanelCard")
        workdir_layout = QVBoxLayout(workdir_card)
        workdir_layout.setContentsMargins(16, 16, 16, 16)
        workdir_layout.setSpacing(10)
        workdir_title = QLabel(texts["settings_workdir_title"])
        workdir_title.setObjectName("SectionTitle")
        workdir_body = QLabel(texts["settings_workdir_body"])
        workdir_body.setObjectName("MutedText")
        workdir_body.setWordWrap(True)

        workdir_row = QHBoxLayout()
        workdir_row.setSpacing(8)
        self.workdir_input = QLineEdit(str(_workdir.get("path", "")))
        self.workdir_input.setPlaceholderText(str(Path.home() / "Desktop"))
        browse_button = QPushButton(texts["settings_workdir_browse"])
        browse_button.clicked.connect(self._browse_workdir)
        workdir_row.addWidget(self.workdir_input, 1)
        workdir_row.addWidget(browse_button)

        workdir_save = QPushButton(texts["settings_save_workdir"])
        workdir_save.setObjectName("PrimaryButton")
        workdir_save.clicked.connect(self._accept_workdir)
        workdir_layout.addWidget(workdir_title)
        workdir_layout.addWidget(workdir_body)
        workdir_layout.addLayout(workdir_row)
        workdir_layout.addWidget(workdir_save, 0, Qt.AlignmentFlag.AlignLeft)

        close_row = QHBoxLayout()
        close_button = QPushButton(texts["settings_close"])
        close_button.clicked.connect(self.reject)
        close_row.addStretch(1)
        close_row.addWidget(close_button)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(cas_card)
        layout.addWidget(api_card)
        layout.addWidget(workdir_card)
        layout.addLayout(close_row)

    def _accept_cas(self) -> None:
        self.intent = "cas"
        self.accept()

    def _accept_api(self) -> None:
        self.intent = "api"
        self.accept()

    def _accept_workdir(self) -> None:
        self.intent = "workdir"
        self.accept()

    def _browse_workdir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            self.texts["settings_workdir_title"],
            self.workdir_input.text() or str(Path.home()),
        )
        if directory:
            self.workdir_input.setText(directory)

    def payload(self) -> dict[str, str]:
        return {
            "cas_username": self.cas_account_input.text().strip(),
            "cas_password": self.cas_password_input.text(),
            "api_key": self.api_key_input.text().strip(),
            "working_dir": self.workdir_input.text().strip(),
        }


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._configure_platform_window_behavior()
        self.api_client = BackendApiClient.from_env()
        self.language = "en"
        self.current_username: str | None = None
        self.current_user_id_value: str | None = None
        self.remote_profile: dict[str, str] | None = None
        self.pending_hitl_request: dict[str, Any] | None = None
        self.registered_users = {}
        self.current_user = self._default_user_profile()
        self.cas_settings = {
            "username": "",
            "password": "",
            "saved": False,
        }
        self.api_settings = {
            "api_key": "",
            "saved": False,
        }
        self.working_dir_settings = {
            "path": "",
            "saved": False,
        }
        self.material_records: list[dict[str, Any]] = []
        self.selected_mode = "agent_chat"
        self.mode_button: QPushButton | None = None
        self.mode_menu: QMenu | None = None
        self.mode_actions: dict[str, Any] = {}
        self.resource_files = []
        self.conversations: list[dict[str, Any]] = []
        self.active_conversation_id: str | None = None
        self.session_id = self._new_session_id()
        self.chat_messages: list[dict[str, Any]] = []
        self.trace_events: list[dict[str, str]] = []
        self.schedule_events: list[dict[str, str]] = []
        self.frontend_schedule_events: list[dict[str, str]] = []
        self.conflicts: list[dict[str, str]] = []
        self.selected_schedule_day: date | None = None
        self._highlighted_schedule_dates: set[date] = set()
        self.response_stream_state: dict[str, Any] | None = None
        self.response_stream_timer = QTimer(self)
        self.response_stream_timer.setInterval(45)
        self.response_stream_timer.timeout.connect(self._advance_response_stream)
        self._active_workers: list[QThread] = []
        self.active_agent_worker: AgentStreamWorker | None = None

        self._reset_dynamic_state()
        self._build_root()
        self._show_home()

    def _configure_platform_window_behavior(self) -> None:
        if sys.platform != "darwin":
            return

        # Native macOS fullscreen has caused pointer hit-testing to drift on some
        # Retina/scaled-display setups. Keep the standard title bar controls, but
        # disable the dedicated fullscreen button so the app stays in regular window
        # coordinates.
        flags = self.windowFlags()
        flags |= Qt.WindowType.CustomizeWindowHint
        flags |= Qt.WindowType.WindowTitleHint
        flags |= Qt.WindowType.WindowCloseButtonHint
        flags |= Qt.WindowType.WindowMinimizeButtonHint
        flags |= Qt.WindowType.WindowMaximizeButtonHint
        flags &= ~Qt.WindowType.WindowFullscreenButtonHint
        self.setWindowFlags(flags)

    def ui(self, key: str, **kwargs) -> str:
        text = UI_TEXTS[self.language][key]
        return text.format(**kwargs) if kwargs else text

    def local(self, value):
        return localized(value, self.language)

    def app_title(self) -> str:
        return self.local(APP_TITLE)

    def backend_status_text(self) -> str:
        if self.api_client.enabled and self.api_client.base_url:
            return self.ui("backend_mode_rest", host=self.api_client.base_url)
        return self.ui("backend_disconnected_title")

    def _new_session_id(self) -> str:
        return f"sess_{uuid4().hex[:12]}"

    def current_user_id(self) -> str:
        return self.current_user_id_value or self.current_username or "local_student"

    def _message_placeholder_for_mode(self) -> str:
        return self.ui("message_placeholder")

    def _mode_label(self, mode: str) -> str:
        return {
            "agent_chat": self.ui("mode_agent_chat"),
            "scheduler": self.ui("mode_scheduler"),
            "encyclopedia": self.ui("mode_encyclopedia"),
        }.get(mode, self.ui("mode_agent_chat"))

    def _set_selected_mode(self, mode: str) -> None:
        if mode not in {"agent_chat", "scheduler", "encyclopedia"}:
            mode = "agent_chat"
        self.selected_mode = mode
        self._refresh_mode_selector()
        if (
            hasattr(self, "center_tabs")
            and hasattr(self, "schedule_tab")
            and mode == "scheduler"
        ):
            self.center_tabs.setCurrentWidget(self.schedule_tab)
        elif hasattr(self, "center_tabs") and hasattr(self, "chat_tab"):
            self.center_tabs.setCurrentWidget(self.chat_tab)

    def _refresh_mode_selector(self) -> None:
        if self.mode_button is not None:
            self.mode_button.setText(f"{self._mode_label(self.selected_mode)}  v")
        for mode, action in self.mode_actions.items():
            action.setChecked(mode == self.selected_mode)
        if hasattr(self, "message_input"):
            self.message_input.setPlaceholderText(self._message_placeholder_for_mode())

    def _open_mode_menu(self) -> None:
        if self.mode_menu is None or self.mode_button is None:
            return
        position = self.mode_button.mapToGlobal(
            QPoint(0, self.mode_button.height() + 6)
        )
        self.mode_menu.exec(position)

    def _response_chunk_size(self, text: str, cursor: int) -> int:
        remaining = max(0, len(text) - cursor)
        if remaining > 180:
            return 24
        if remaining > 90:
            return 18
        if remaining > 32:
            return 12
        return 8

    def _show_thinking_indicator(self) -> None:
        """Insert an animated thinking bubble at the end of the chat."""
        if not hasattr(self, "chat_layout"):
            return
        sender_label = self._sender_label("agent")
        indicator = ThinkingIndicator(sender_label)
        indicator.setObjectName("_ThinkingIndicator")
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, indicator)
        self._scroll_chat_to_bottom()

    def _remove_thinking_indicator(self) -> None:
        """Remove the thinking indicator from the chat layout."""
        if not hasattr(self, "chat_layout"):
            return
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if (
                item
                and item.widget()
                and item.widget().objectName() == "_ThinkingIndicator"
            ):
                w = self.chat_layout.takeAt(i).widget()
                if w is not None:
                    w.deleteLater()
                return

    def _scroll_chat_to_bottom(self) -> None:
        if not hasattr(self, "chat_scroll_area"):
            return

        def _do_scroll() -> None:
            bar = self.chat_scroll_area.verticalScrollBar()
            bar.setValue(bar.maximum())

        # The chat bubble height can continue growing after layout rebuilds,
        # especially while the typewriter effect is still revealing content.
        QTimer.singleShot(0, _do_scroll)
        QTimer.singleShot(30, _do_scroll)
        QTimer.singleShot(120, _do_scroll)

    def _finalize_response_stream(self, *, open_dialog: bool) -> None:
        state = self.response_stream_state or {}
        self.response_stream_timer.stop()
        self.response_stream_state = None
        self.pending_hitl_request = state.get("pending_hitl_request")
        self._sync_active_conversation()
        self._refresh_generation_controls()
        if (
            open_dialog
            and self.pending_hitl_request
            and state.get("auto_open_hitl", True)
        ):
            self.open_hitl_dialog()

    def _flush_response_stream(self, *, open_dialog: bool) -> None:
        if not self.response_stream_state:
            return

        state = self.response_stream_state
        assistant_index = state.get("assistant_index")
        assistant_text = str(state.get("assistant_text", ""))
        if assistant_index is not None and 0 <= assistant_index < len(
            self.chat_messages
        ):
            self.chat_messages[assistant_index]["text"] = assistant_text

        trace_index = int(state.get("trace_index", 0))
        trace_queue = list(state.get("trace_queue", []))
        if trace_index < len(trace_queue):
            self.trace_events.extend(trace_queue[trace_index:])

        extra_index = int(state.get("extra_index", 0))
        extra_messages = list(state.get("extra_messages", []))
        if extra_index < len(extra_messages):
            self.chat_messages.extend(extra_messages[extra_index:])

        self._load_chat_messages(self.chat_messages)
        self._load_trace_events(self.trace_events)
        self._finalize_response_stream(open_dialog=open_dialog)

    def _agent_response_active(self) -> bool:
        return self.active_agent_worker is not None or bool(self.response_stream_state)

    def _refresh_generation_controls(self) -> None:
        if not hasattr(self, "send_button"):
            return
        if self._agent_response_active():
            self.send_button.setText("x")
            self.send_button.setToolTip(self.ui("cancel_generation_tooltip"))
            return
        self.send_button.setText("↑")
        self.send_button.setToolTip(self.ui("send"))

    def _cancel_agent_generation(self) -> None:
        if self.response_stream_state:
            self.response_stream_timer.stop()
            self.response_stream_state = None
            self._sync_active_conversation()
        worker = self.active_agent_worker
        self.active_agent_worker = None
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
            worker.terminate()
            worker.wait(1000)
        if worker in self._active_workers:
            self._active_workers.remove(worker)
        self._remove_thinking_indicator()
        self.chat_messages.append(
            self._create_text_message("agent", self.ui("generation_cancelled"))
        )
        self._load_chat_messages(self.chat_messages)
        self._sync_active_conversation()
        self._refresh_generation_controls()

    def _advance_response_stream(self) -> None:
        if not self.response_stream_state:
            self.response_stream_timer.stop()
            return

        state = self.response_stream_state
        chat_changed = False
        trace_changed = False

        trace_queue = list(state.get("trace_queue", []))
        trace_index = int(state.get("trace_index", 0))
        if trace_index < len(trace_queue):
            self.trace_events.append(trace_queue[trace_index])
            state["trace_index"] = trace_index + 1
            trace_changed = True

        assistant_index = state.get("assistant_index")
        assistant_text = str(state.get("assistant_text", ""))
        cursor = int(state.get("assistant_cursor", 0))
        if assistant_index is not None and cursor < len(assistant_text):
            next_cursor = min(
                len(assistant_text),
                cursor + self._response_chunk_size(assistant_text, cursor),
            )
            state["assistant_cursor"] = next_cursor
            if 0 <= assistant_index < len(self.chat_messages):
                self.chat_messages[assistant_index]["text"] = assistant_text[
                    :next_cursor
                ]
                chat_changed = True

        extra_messages = list(state.get("extra_messages", []))
        extra_index = int(state.get("extra_index", 0))
        assistant_done = assistant_index is None or int(
            state.get("assistant_cursor", 0)
        ) >= len(assistant_text)
        trace_done = int(state.get("trace_index", 0)) >= len(trace_queue)
        if assistant_done and trace_done and extra_index < len(extra_messages):
            self.chat_messages.append(extra_messages[extra_index])
            state["extra_index"] = extra_index + 1
            chat_changed = True

        if chat_changed:
            self._load_chat_messages(self.chat_messages)
            self._scroll_chat_to_bottom()
        if trace_changed:
            self._load_trace_events(self.trace_events)

        trace_done = int(state.get("trace_index", 0)) >= len(trace_queue)
        assistant_done = assistant_index is None or int(
            state.get("assistant_cursor", 0)
        ) >= len(assistant_text)
        extras_done = int(state.get("extra_index", 0)) >= len(extra_messages)
        if trace_done and assistant_done and extras_done:
            self._finalize_response_stream(open_dialog=True)

    def _queue_response_stream(
        self,
        *,
        assistant_text: str,
        trace_items: list[dict[str, str]] | None = None,
        extra_messages: list[dict[str, Any]] | None = None,
        pending_hitl_request: dict[str, Any] | None = None,
        auto_open_hitl: bool = True,
    ) -> None:
        self._flush_response_stream(open_dialog=False)

        normalized_trace = list(trace_items or [])
        queued_messages = [dict(item) for item in (extra_messages or [])]
        assistant_index: int | None = None
        initial_cursor = 0
        if assistant_text:
            initial_cursor = min(
                len(assistant_text), self._response_chunk_size(assistant_text, 0)
            )
            self.chat_messages.append(
                self._create_text_message("agent", assistant_text[:initial_cursor])
            )
            assistant_index = len(self.chat_messages) - 1
            self._load_chat_messages(self.chat_messages)

        self.response_stream_state = {
            "assistant_index": assistant_index,
            "assistant_text": assistant_text,
            "assistant_cursor": initial_cursor,
            "trace_queue": normalized_trace,
            "trace_index": 0,
            "extra_messages": queued_messages,
            "extra_index": 0,
            "pending_hitl_request": pending_hitl_request,
            "auto_open_hitl": auto_open_hitl,
        }

        if not assistant_text and not normalized_trace and not queued_messages:
            self._finalize_response_stream(open_dialog=auto_open_hitl)
            return

        self.response_stream_timer.start()

    def _default_user_profile(self) -> dict[str, str]:
        return {
            "name": self.local(PROFILE["name"]),
            "major": self.local(PROFILE["major"]),
            "focus": self.local(PROFILE["focus"]),
        }

    def _build_new_chat_messages(self) -> list[dict[str, Any]]:
        return [
            {
                "kind": "text",
                "sender": "agent",
                "text": self.ui("welcome_message"),
            }
        ]

    def _create_text_message(self, sender: str, text: str) -> dict[str, Any]:
        return {
            "kind": "text",
            "sender": sender,
            "text": text,
        }

    def _create_schedule_message(
        self,
        *,
        intro: str,
        events: list[dict[str, str]],
        conflicts: list[dict[str, str]],
    ) -> dict[str, Any]:
        return {
            "kind": "schedule",
            "sender": "agent",
            "text": intro,
            "payload": {
                "events": [dict(item) for item in events],
                "conflicts": [dict(item) for item in conflicts],
            },
        }

    def _create_encyclopedia_message(
        self,
        *,
        intro: str,
        query: str,
        answer_markdown: str,
        citations: list[str],
    ) -> dict[str, Any]:
        return {
            "kind": "encyclopedia",
            "sender": "agent",
            "text": intro,
            "payload": {
                "query": query,
                "answer_markdown": answer_markdown,
                "citations": list(citations),
            },
        }

    def _build_response_cards(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        ui_payload = response.get("ui_payload", {})
        if not isinstance(ui_payload, dict):
            return cards

        schedule_payload = ui_payload.get("schedule")
        if isinstance(schedule_payload, dict):
            events = schedule_payload.get("events", [])
            conflicts = schedule_payload.get("conflicts", [])
            normalized_events: list[dict[str, str]] = []
            normalized_conflicts: list[dict[str, str]] = []
            if isinstance(events, list) and events:
                normalized_events = self._normalize_schedule_events(events)
                self.schedule_events = self._merge_schedule_event_lists(
                    normalized_events,
                    self.frontend_schedule_events,
                )
            if isinstance(conflicts, list) and conflicts:
                normalized_conflicts = self._normalize_conflicts(conflicts)
                self.conflicts = normalized_conflicts
            if normalized_events or normalized_conflicts:
                cards.append(
                    self._create_schedule_message(
                        intro=self.ui("schedule_card_intro"),
                        events=normalized_events or self.schedule_events,
                        conflicts=normalized_conflicts or self.conflicts,
                    )
                )
                self._refresh_schedule_views()

        encyclopedia_payload = ui_payload.get("encyclopedia")
        if isinstance(encyclopedia_payload, dict):
            answer_markdown = str(
                encyclopedia_payload.get("answer_markdown", "")
            ).strip()
            citations = encyclopedia_payload.get("citations", [])
            cards.append(
                self._create_encyclopedia_message(
                    intro=self.ui("encyclopedia_card_intro"),
                    query=str(encyclopedia_payload.get("query", "")).strip(),
                    answer_markdown=answer_markdown,
                    citations=(
                        [str(item) for item in citations]
                        if isinstance(citations, list)
                        else []
                    ),
                )
            )

        library_payload = ui_payload.get("library")
        if isinstance(library_payload, dict):
            rooms = library_payload.get("rooms", [])
            cards.append(
                self._create_library_message(
                    intro=self.ui("library_card_intro"),
                    query_time=str(library_payload.get("query_time") or ""),
                    query_location=str(library_payload.get("query_location") or ""),
                    query_capacity=library_payload.get("query_capacity"),
                    rooms=rooms if isinstance(rooms, list) else [],
                )
            )

        return cards

    def _create_library_message(
        self,
        *,
        intro: str,
        query_time: str,
        query_location: str,
        query_capacity: Any,
        rooms: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "kind": "library",
            "sender": "agent",
            "text": intro,
            "payload": {
                "query_time": query_time,
                "query_location": query_location,
                "query_capacity": query_capacity,
                "rooms": list(rooms),
            },
        }

    def _create_conversation(
        self,
        *,
        session_id: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        trace: list[dict[str, str]] | None = None,
        pending_hitl_request: dict[str, Any] | None = None,
        title: str | None = None,
        remote_updated_at: str | None = None,
        messages_loaded: bool = True,
    ) -> dict[str, Any]:
        return {
            "session_id": session_id or self._new_session_id(),
            "messages": (
                list(messages)
                if messages is not None
                else self._build_new_chat_messages()
            ),
            "trace": list(trace or []),
            "pending_hitl_request": pending_hitl_request,
            "title": title,
            "remote_updated_at": remote_updated_at,
            "messages_loaded": messages_loaded,
        }

    @staticmethod
    def _clean_optional_text(value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        return "" if text.lower() == "none" else text

    def _conversation_has_user_content(self, conversation: dict[str, Any]) -> bool:
        for item in conversation.get("messages", []):
            if item.get("sender") == "user" and str(item.get("text", "")).strip():
                return True
        return False

    def _conversation_is_visible(self, conversation: dict[str, Any]) -> bool:
        return any(
            (
                self._conversation_has_user_content(conversation),
                bool(conversation.get("trace")),
                bool(self._clean_optional_text(conversation.get("title"))),
                bool(self._clean_optional_text(conversation.get("remote_updated_at"))),
            )
        )

    def _conversation_is_deletable(self, conversation: dict[str, Any] | None) -> bool:
        return bool(conversation and self._conversation_is_visible(conversation))

    def _derive_conversation_title(self, conversation: dict[str, Any]) -> str:
        title = self._clean_optional_text(conversation.get("title"))
        if title:
            return title[:32] + ("..." if len(title) > 32 else "")
        for item in conversation["messages"]:
            if item.get("sender") == "user" and str(item.get("text", "")).strip():
                title = str(item.get("text", "")).strip().replace("\n", " ")
                return title[:32] + ("..." if len(title) > 32 else "")
        return self.ui("new_chat")

    def _conversation_meta(self, conversation: dict[str, Any]) -> str:
        updated_at = self._clean_optional_text(conversation.get("remote_updated_at"))
        if updated_at:
            return self.ui(
                "conversation_meta_remote",
                updated=self._format_remote_timestamp(updated_at),
            )
        return self.ui(
            "conversation_meta",
            messages=len(conversation["messages"]),
            trace=len(conversation["trace"]),
        )

    def _format_remote_timestamp(self, value: str) -> str:
        text = str(value).strip()
        if not text:
            return ""
        try:
            normalized = text.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            china_tz = timezone(timedelta(hours=8))
            return dt.astimezone(china_tz).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            if "T" in text:
                text = text.replace("T", " ")
            if "+" in text:
                text = text.split("+", 1)[0]
            return text[:16] if len(text) > 16 else text

    def _normalize_backend_chat_history(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in messages:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "")).lower()
            content = str(item.get("content", ""))
            if role not in {"user", "assistant"}:
                continue
            normalized.append(
                self._create_text_message(
                    "user" if role == "user" else "agent", content
                )
            )
        return normalized

    def _resource_display_name(self, resource_name: str) -> str:
        return Path(resource_name).name or resource_name

    def _resource_meta(self, resource_name: str) -> str:
        display_name = self._resource_display_name(resource_name)
        suffix = (
            display_name.rsplit(".", 1)[-1].upper() if "." in display_name else "FILE"
        )
        return f"{suffix}  |  {self.ui('resource_ready')}"

    def _active_conversation(self) -> dict[str, Any] | None:
        if not self.active_conversation_id:
            return None
        for conversation in self.conversations:
            if conversation["session_id"] == self.active_conversation_id:
                return conversation
        return None

    def _sync_active_conversation(self) -> None:
        conversation = self._active_conversation()
        if conversation is None:
            return
        conversation["messages"] = list(self.chat_messages)
        conversation["trace"] = list(self.trace_events)
        conversation["pending_hitl_request"] = self.pending_hitl_request
        conversation["messages_loaded"] = True

    def _move_active_conversation_to_top(self) -> None:
        conversation = self._active_conversation()
        if conversation is None:
            return
        self.conversations = [conversation] + [
            item
            for item in self.conversations
            if item["session_id"] != conversation["session_id"]
        ]

    def _activate_conversation(self, session_id: str) -> None:
        for conversation in self.conversations:
            if conversation["session_id"] != session_id:
                continue

            self.active_conversation_id = session_id
            self.session_id = session_id
            self.chat_messages = list(conversation["messages"])
            self.trace_events = list(conversation["trace"])
            self.pending_hitl_request = conversation.get("pending_hitl_request")

            if hasattr(self, "chat_layout"):
                self._load_chat_messages(self.chat_messages)
            if hasattr(self, "trace_layout"):
                self._load_trace_events(self.trace_events)
            if hasattr(self, "history_list"):
                self._refresh_conversation_list()
            if (
                not conversation.get("messages_loaded", True)
                and self.api_client.enabled
                and self.api_client.authenticated
                and self._clean_optional_text(conversation.get("remote_updated_at"))
            ):
                self._load_remote_conversation(session_id)
            break

    def _load_remote_conversation(self, session_id: str) -> None:
        def _on_done(payload):
            messages = payload.get("messages", [])
            normalized_messages = (
                self._normalize_backend_chat_history(messages)
                if isinstance(messages, list)
                else []
            )
            updated_at = self._clean_optional_text(payload.get("updated_at"))
            title = self._clean_optional_text(payload.get("title"))

            for conversation in self.conversations:
                if conversation["session_id"] != session_id:
                    continue
                conversation["messages"] = normalized_messages
                conversation["messages_loaded"] = True
                conversation["remote_updated_at"] = updated_at or conversation.get(
                    "remote_updated_at"
                )
                if title:
                    conversation["title"] = title
                if self.active_conversation_id == session_id:
                    self.chat_messages = list(normalized_messages)
                    self.trace_events = []
                    self.pending_hitl_request = None
                    self._load_chat_messages(self.chat_messages)
                    self._load_trace_events(self.trace_events)
                    self._refresh_conversation_list()
                break

        self._start_worker(
            lambda: self.api_client.get_session_detail(session_id),
            _on_done,
        )

    def _initialize_default_conversations(self) -> None:
        conversation = self._create_conversation(
            session_id=self.session_id,
            messages=self._build_new_chat_messages(),
            trace=[],
        )
        self.conversations = [conversation]
        self.active_conversation_id = conversation["session_id"]
        self.chat_messages = list(conversation["messages"])
        self.trace_events = []
        self.pending_hitl_request = None

    def _normalize_backend_trace_events(
        self, events: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        normalized = []
        for item in events:
            status = str(item.get("status", "running")).lower()
            if status not in {"done", "running", "pending", "error"}:
                status = "running"
            normalized.append(
                {
                    "phase": str(item.get("phase", "Observation")),
                    "title": str(item.get("title", "")),
                    "detail": str(item.get("detail", "")),
                    "status": status,
                }
            )
        return normalized

    def _normalize_schedule_events(
        self, events: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        normalized = []
        for item in events:
            normalized.append(
                {
                    "title": str(item.get("title", "")),
                    "time": str(item.get("time", "")),
                    "source": str(item.get("source", "")),
                    "detail": str(item.get("detail", "")),
                }
            )
        return normalized

    def _merge_schedule_event_lists(
        self,
        *event_lists: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        merged: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for events in event_lists:
            for item in events:
                if not isinstance(item, dict):
                    continue
                event = self._normalize_schedule_events([item])[0]
                key = self._schedule_event_key(event)
                if not key[0] or not key[1] or key in seen:
                    continue
                seen.add(key)
                merged.append(event)
        return sorted(merged, key=event_sort_key)

    @staticmethod
    def _schedule_event_key(event: dict[str, Any]) -> tuple[str, str]:
        return (
            str(event.get("title", "")).strip().lower(),
            str(event.get("time", "")).strip(),
        )

    def _normalize_conflicts(
        self, conflicts: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        normalized = []
        for item in conflicts:
            normalized.append(
                {
                    "title": str(item.get("title", "")),
                    "detail": str(item.get("detail", "")),
                }
            )
        return normalized

    def _add_frontend_schedule_event_from_reply(
        self, text: str
    ) -> dict[str, str] | None:
        event = self._extract_schedule_event_from_reply(text)
        if event is None:
            return None

        already_present = self._schedule_event_key(event) in {
            self._schedule_event_key(existing) for existing in self.schedule_events
        }
        self.frontend_schedule_events = self._merge_schedule_event_lists(
            self.frontend_schedule_events,
            [event],
        )
        self.schedule_events = self._merge_schedule_event_lists(
            self.schedule_events,
            [event],
        )

        event_days = sorted(events_by_date([event]))
        if event_days:
            self.selected_schedule_day = event_days[0]
        self._refresh_schedule_views()
        return None if already_present else event

    def _extract_schedule_event_from_reply(self, text: str) -> dict[str, str] | None:
        plain_text = self._plain_schedule_reply_text(text)
        if not plain_text or not self._looks_like_schedule_add_reply(plain_text):
            return None

        title = self._extract_reply_schedule_title(plain_text)
        schedule_time = self._extract_reply_schedule_time(plain_text)
        if not title or not schedule_time:
            return None

        return {
            "title": title,
            "time": schedule_time,
            "source": self.local({"en": "Local Plan", "zh": "本地计划"}),
            "detail": self._extract_reply_schedule_detail(plain_text),
        }

    @staticmethod
    def _plain_schedule_reply_text(text: str) -> str:
        plain = re.sub(r"[*_`#>]", "", text or "")
        plain = plain.replace("（", "(").replace("）", ")")
        plain = plain.replace("：", ":")
        plain = plain.replace("－", "-").replace("—", "-").replace("–", "-")
        return "\n".join(line.strip() for line in plain.splitlines() if line.strip())

    @staticmethod
    def _looks_like_schedule_add_reply(text: str) -> bool:
        lower_text = text.lower()
        negative_markers = (
            "没有加入",
            "未加入",
            "没有添加",
            "未添加",
            "添加失败",
            "保存失败",
            "not added",
            "failed to add",
            "could not add",
        )
        if any(marker in lower_text or marker in text for marker in negative_markers):
            return False
        chinese_add = any(
            marker in text
            for marker in (
                "加入日程",
                "加入到日程",
                "添加到日程",
                "添加进日程",
                "新增日程",
            )
        )
        chinese_saved = any(word in text for word in ("日程", "日历", "安排")) and any(
            marker in text
            for marker in (
                "已保存",
                "保存成功",
                "已安排",
                "已添加",
                "添加成功",
                "已新增",
                "已为你",
                "已经",
                "成功",
            )
        )
        english_add = "schedule" in lower_text and any(
            marker in lower_text
            for marker in ("added", "saved", "scheduled", "created")
        )
        english_calendar = "calendar" in lower_text and any(
            marker in lower_text
            for marker in ("added", "saved", "scheduled", "created")
        )
        return chinese_add or chinese_saved or english_add or english_calendar

    def _extract_reply_schedule_title(self, text: str) -> str:
        for line in self._schedule_reply_lines(text):
            label_match = re.search(
                r"(?:事件名称|名称|标题|title|name)\s*:\s*(.+)",
                line,
                re.IGNORECASE,
            )
            if label_match:
                title = self._clean_reply_field(label_match.group(1))
                if title:
                    return title

        quoted_match = re.search(
            r"[\"'“”‘’](.{2,80}?)[\"'“”‘’].*(?:日程|日历|schedule|calendar)",
            text,
            re.IGNORECASE,
        )
        if quoted_match:
            title = self._clean_reply_field(quoted_match.group(1))
            if title:
                return title

        patterns = [
            r"将\s*(.+?)\s*(?:加入|添加|保存|安排).*?(?:日程|日历)",
            r"把\s*(.+?)\s*(?:加入|添加|保存|安排).*?(?:日程|日历)",
            r"(?:日程|日历)\s*(?:已)?(?:添加|新增|保存|安排)\s*:?\s*(.+)",
            r"为你(?:安排|添加|新增)(?:了)?\s*(.+)",
            r"(?:已安排|安排了|已添加|添加了)\s*(.+)",
            r"(?:added|saved|scheduled)\s+(.+?)\s+(?:to|in)\s+(?:the\s+)?(?:schedule|calendar)",
            r"(?:scheduled|created)\s+(.+?)\s+(?:for|on)\s+",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                title = self._cleanup_inferred_schedule_title(
                    self._remove_reply_schedule_time_text(match.group(1))
                )
                if title:
                    return title
        return self._infer_reply_schedule_title_from_time_context(text)

    def _infer_reply_schedule_title_from_time_context(self, text: str) -> str:
        candidates = self._schedule_reply_lines(text) + [text]
        for candidate in candidates:
            if not self._parse_reply_schedule_time(candidate):
                continue
            title = self._cleanup_inferred_schedule_title(
                self._remove_reply_schedule_time_text(candidate)
            )
            if title:
                return title
        return ""

    def _extract_reply_schedule_time(self, text: str) -> str:
        candidates: list[str] = []
        for line in self._schedule_reply_lines(text):
            label_match = re.search(
                r"(?:时间|日期|开始时间|time|when)\s*:\s*(.+)",
                line,
                re.IGNORECASE,
            )
            if label_match:
                candidates.append(label_match.group(1))
        candidates.append(text)

        for candidate in candidates:
            schedule_time = self._parse_reply_schedule_time(candidate)
            if schedule_time:
                return schedule_time
        return ""

    def _extract_reply_schedule_detail(self, text: str) -> str:
        detail_parts: list[str] = []
        for line in self._schedule_reply_lines(text):
            label_match = re.search(
                r"(?:地点|位置|location|详情|备注|说明|detail|note)\s*:\s*(.+)",
                line,
                re.IGNORECASE,
            )
            if label_match:
                value = self._clean_reply_field(label_match.group(1))
                if value:
                    detail_parts.append(value)
        if detail_parts:
            return " | ".join(detail_parts)
        return self.local(
            {"en": "Added from the chat response.", "zh": "从聊天回复自动识别。"}
        )

    @staticmethod
    def _schedule_reply_lines(text: str) -> list[str]:
        lines: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            line = re.sub(r"^[\-•\s]+", "", line)
            if line:
                lines.append(line)
        return lines

    @staticmethod
    def _clean_reply_field(value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value or "").strip()
        cleaned = cleaned.strip(" -:;!！。.'\"")
        return cleaned

    def _cleanup_inferred_schedule_title(self, value: str) -> str:
        cleaned = self._clean_reply_field(value)
        cleaned = re.sub(r"[✅📌]+", " ", cleaned)
        cleaned = re.sub(
            r"(?:事件详情|事件|详情|名称|标题|时间|日期|状态|备注|说明|地点|位置)\s*:?",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"(?:日程已添加|日历已添加|已成功|成功|我已经|已经|已将|已把|已为你|已添加|添加成功|已新增|帮你|为你|给你|请|将|把|并)",
            " ",
            cleaned,
        )
        cleaned = re.sub(
            r"(?:加入到?日程|添加到?日程|添加进日程|新增日程|保存到日程|安排到日程|安排进日程|加入日历|添加到?日历)",
            " ",
            cleaned,
        )
        cleaned = re.sub(
            r"(?:加入|添加|新增|保存|安排在?|已保存|保存成功|日程|日历)", " ", cleaned
        )
        cleaned = re.sub(
            r"\b(?:added|saved|scheduled|created|calendar|schedule|event|for|on|from|to|at|in|your|the|a|an)\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:;!！。，,.'\"的在到")
        return cleaned

    def _parse_reply_schedule_time(self, text: str) -> str:
        normalized = self._plain_schedule_reply_text(text)
        date_info = self._reply_schedule_base_day(normalized)
        if date_info is None:
            return ""

        base_day, date_start, date_end = date_info
        parsed_time = self._parse_reply_time_from_contexts(
            self._time_context_candidates(normalized, date_start, date_end),
            base_day,
        )
        return parsed_time or base_day.isoformat()

    def _parse_reply_time_from_contexts(
        self, contexts: list[str], base_day: date
    ) -> str:
        for context in contexts:
            range_match = self._reply_time_range_pattern().search(context)
            if range_match:
                start = self._build_reply_datetime(
                    base_day,
                    range_match.group(1),
                    range_match.group(2),
                    context,
                    range_match.group(3),
                )
                end = self._build_reply_datetime(
                    base_day,
                    range_match.group(4),
                    range_match.group(5),
                    context,
                    range_match.group(6),
                )
                if start is None or end is None:
                    continue
                if end <= start:
                    end += timedelta(days=1)
                return f"{start.isoformat()}~{end.isoformat()}"

        for context in contexts:
            time_match = self._reply_single_time_pattern().search(context)
            if not time_match:
                continue
            start = self._build_reply_datetime(
                base_day,
                time_match.group(1),
                time_match.group(2),
                context,
                time_match.group(3),
            )
            if start is None:
                continue
            return start.isoformat()
        return ""

    def _reply_schedule_base_day(self, text: str) -> tuple[date, int, int] | None:
        chinese_match = re.search(
            r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日", text
        )
        if chinese_match:
            parsed = self._safe_date(
                int(chinese_match.group(1) or date.today().year),
                int(chinese_match.group(2)),
                int(chinese_match.group(3)),
            )
            if parsed:
                return parsed, chinese_match.start(), chinese_match.end()

        iso_match = re.search(r"(?<!\d)(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?!\d)", text)
        if iso_match:
            parsed = self._safe_date(
                int(iso_match.group(1)),
                int(iso_match.group(2)),
                int(iso_match.group(3)),
            )
            if parsed:
                return parsed, iso_match.start(), iso_match.end()

        month_pattern = (
            r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
            r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        )
        english_match = re.search(
            rf"\b{month_pattern}\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,\s*(\d{{4}}))?\b",
            text,
            re.IGNORECASE,
        )
        if english_match:
            month = self._english_month_number(english_match.group(1))
            parsed = self._safe_date(
                int(english_match.group(3) or date.today().year),
                month,
                int(english_match.group(2)),
            )
            if parsed:
                return parsed, english_match.start(), english_match.end()

        english_reverse_match = re.search(
            rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{month_pattern}(?:\s+(\d{{4}}))?\b",
            text,
            re.IGNORECASE,
        )
        if english_reverse_match:
            month = self._english_month_number(english_reverse_match.group(2))
            parsed = self._safe_date(
                int(english_reverse_match.group(3) or date.today().year),
                month,
                int(english_reverse_match.group(1)),
            )
            if parsed:
                return (
                    parsed,
                    english_reverse_match.start(),
                    english_reverse_match.end(),
                )

        relative_markers = [
            ("day after tomorrow", 2),
            ("tomorrow", 1),
            ("today", 0),
            ("大后天", 3),
            ("后天", 2),
            ("明天", 1),
            ("明日", 1),
            ("今天", 0),
            ("今日", 0),
        ]
        for marker, offset in relative_markers:
            match = re.search(re.escape(marker), text, re.IGNORECASE)
            if match:
                return date.today() + timedelta(days=offset), match.start(), match.end()
        return None

    @staticmethod
    def _safe_date(year: int, month: int, day: int) -> date | None:
        try:
            return date(year, month, day)
        except ValueError:
            return None

    @staticmethod
    def _english_month_number(month_text: str) -> int:
        month_key = month_text[:3].lower()
        return {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }.get(month_key, 1)

    @staticmethod
    def _time_context_candidates(
        text: str, date_start: int, date_end: int
    ) -> list[str]:
        before = text[:date_start]
        after = text[date_end:]
        return [after, before, f"{before} {after}"]

    def _remove_reply_schedule_time_text(self, text: str) -> str:
        cleaned = self._plain_schedule_reply_text(text)
        cleaned = re.sub(
            r"(?:(\d{4})\s*年\s*)?\d{1,2}\s*月\s*\d{1,2}\s*日", " ", cleaned
        )
        cleaned = re.sub(r"(?<!\d)\d{4}[-/]\d{1,2}[-/]\d{1,2}(?!\d)", " ", cleaned)
        cleaned = re.sub(
            r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
            r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
            r"\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{4})?\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
            r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:\s+\d{4})?\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"(?:周[一二三四五六日天]|星期[一二三四五六日天]|today|tomorrow|day after tomorrow|今天|今日|明天|明日|后天|大后天)",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = self._reply_time_range_pattern().sub(" ", cleaned)
        cleaned = self._reply_single_time_pattern().sub(" ", cleaned)
        return cleaned

    @staticmethod
    def _reply_time_range_pattern() -> re.Pattern[str]:
        marker_word = r"(?:上午|早上|下午|晚上|中午|am|pm|a\.m\.|p\.m\.)"
        marker = rf"({marker_word})?"
        prefix = rf"(?:{marker_word}\s*)?"
        token = rf"{prefix}([01]?\d|2[0-3])(?:\s*(?:[:：]|点|时)\s*([0-5]?\d)?)?(?:\s*分)?\s*{marker}(?!\d)"
        return re.compile(
            rf"(?<![\d/-]){token}\s*(?:-|~|到|至|to|until)\s*{token}", re.IGNORECASE
        )

    @staticmethod
    def _reply_single_time_pattern() -> re.Pattern[str]:
        marker_word = r"(?:上午|早上|下午|晚上|中午|am|pm|a\.m\.|p\.m\.)"
        marker = rf"({marker_word})?"
        prefix = rf"(?:{marker_word}\s*)?"
        return re.compile(
            rf"(?<![\d/-]){prefix}([01]?\d|2[0-3])(?:\s*(?:[:：]|点|时)\s*([0-5]?\d)?)?(?:\s*分)?\s*{marker}(?!\d)",
            re.IGNORECASE,
        )

    @staticmethod
    def _build_reply_datetime(
        base_day: date,
        hour_text: str,
        minute_text: str | None,
        context: str,
        marker: str | None = None,
    ) -> datetime | None:
        try:
            hour = int(hour_text)
            minute = int(minute_text or 0)
        except ValueError:
            return None
        time_context = f"{context} {marker or ''}".lower()
        if (
            any(
                token in time_context
                for token in ("下午", "晚上", "中午", "pm", "p.m.")
            )
            and 1 <= hour < 12
        ):
            hour += 12
        elif (
            any(token in time_context for token in ("上午", "早上", "am", "a.m."))
            and hour == 12
        ):
            hour = 0
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return datetime(base_day.year, base_day.month, base_day.day, hour, minute)

    def _normalize_hitl_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "request_id": str(payload.get("request_id", "")),
            "action": str(payload.get("action", self.local(HITL_REQUEST["action"]))),
            "risk": str(payload.get("risk", self.local(HITL_REQUEST["risk"]))),
            "reason": str(payload.get("reason", self.local(HITL_REQUEST["reason"]))),
            "payload": [str(item) for item in payload.get("payload", [])],
        }

    def _selected_material_attachments(self) -> list[dict[str, Any]]:
        if not hasattr(self, "resource_list") or not self.material_records:
            return []

        attachments: list[dict[str, Any]] = []
        for item in self.resource_list.selectedItems():
            row = self.resource_list.row(item)
            if row < 0 or row >= len(self.material_records):
                continue
            material = self.material_records[row]
            attachments.append(
                {
                    "file_id": str(material.get("file_id", "")),
                    "file_name": str(material.get("file_name", "")),
                    "file_type": str(material.get("file_type", "")),
                }
            )
        return [item for item in attachments if item["file_id"]]

    def _sync_remote_sessions(self) -> None:
        if not (self.api_client.enabled and self.api_client.authenticated):
            return

        def _on_done(summaries):
            if not summaries:
                return
            existing = {
                conversation["session_id"]: conversation
                for conversation in self.conversations
            }
            merged: list[dict[str, Any]] = []
            seen: set[str] = set()
            for item in summaries:
                session_id = str(item.get("session_id", "")).strip()
                if not session_id:
                    continue
                title = self._clean_optional_text(item.get("title"))
                preview = self._clean_optional_text(item.get("preview"))
                updated_at = self._clean_optional_text(item.get("updated_at"))
                if not (title or preview or updated_at):
                    continue
                conversation = existing.get(session_id)
                if conversation is None:
                    conversation = self._create_conversation(
                        session_id=session_id,
                        messages=[],
                        trace=[],
                        title=title or preview,
                        remote_updated_at=updated_at,
                        messages_loaded=False,
                    )
                else:
                    conversation["title"] = (
                        title or preview or conversation.get("title")
                    )
                    conversation["remote_updated_at"] = updated_at
                merged.append(conversation)
                seen.add(session_id)
            active = self._active_conversation()
            if active and active["session_id"] not in seen:
                merged.insert(0, active)
            if merged:
                self.conversations = merged
                if active and active["session_id"] in {
                    item["session_id"] for item in merged
                }:
                    self.active_conversation_id = active["session_id"]
                else:
                    self.active_conversation_id = merged[0]["session_id"]
                self._refresh_conversation_list()

        self._start_worker(self.api_client.list_sessions, _on_done)

    def _build_root(self) -> None:
        self.setWindowTitle(self.app_title())
        self.resize(1560, 940)

        root = StarfieldBackground()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(0)

        self.stack = QStackedWidget()
        self.home_page = self._build_home_page()
        self.auth_page = self._build_auth_page()
        self.dashboard_page = self._build_dashboard_page()
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.auth_page)
        self.stack.addWidget(self.dashboard_page)
        root_layout.addWidget(self.stack)

        self._load_chat_messages(self.chat_messages)
        self._load_trace_events(self.trace_events)
        self._load_resource_files()
        self._refresh_schedule_views()
        self._refresh_profile_views()

    def _reset_dynamic_state(self) -> None:
        self._initialize_default_conversations()
        self.frontend_schedule_events = []
        self.schedule_events = []
        self.conflicts = []
        self.selected_schedule_day = None
        self._highlighted_schedule_dates = set()

        if self.remote_profile:
            self.current_user = {
                "name": str(
                    self.remote_profile.get(
                        "name", self.current_username or self.local(PROFILE["name"])
                    )
                ),
                "major": str(
                    self.remote_profile.get("major", self.local(PROFILE["major"]))
                ),
                "focus": self.ui("authenticated_focus"),
            }
            return

        if self.current_username:
            record = self.registered_users.get(self.current_username)
            major = (
                self.local(record["major"]) if record else self.local(PROFILE["major"])
            )
            self.current_user = {
                "name": (
                    str(self.local(record["display_name"]))
                    if record and "display_name" in record
                    else self.current_username
                ),
                "major": major,
                "focus": self.ui("authenticated_focus"),
            }
        else:
            self.current_user = self._default_user_profile()

    def _load_resource_files(self) -> None:
        if not hasattr(self, "resource_list"):
            return
        self.resource_list.clear()
        for resource in self.resource_files:
            display_name = self._resource_display_name(resource)
            item = QListWidgetItem(
                f"{display_name}\n{self._resource_meta(resource)}", self.resource_list
            )
            item.setToolTip(resource)
            item.setSizeHint(QSize(0, 58))
        self._refresh_profile_views()

    def _refresh_conversation_list(self) -> None:
        if not hasattr(self, "history_list"):
            return

        self._sync_active_conversation()
        self.history_list.blockSignals(True)
        self.history_list.clear()
        visible_conversations = [
            item for item in self.conversations if self._conversation_is_visible(item)
        ]
        if not visible_conversations:
            item = QListWidgetItem(self.ui("empty_history"), self.history_list)
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.history_list.blockSignals(False)
            self._refresh_history_actions()
            return

        selected_row = -1
        for index, conversation in enumerate(visible_conversations):
            title = self._derive_conversation_title(conversation)
            item = QListWidgetItem(
                f"{title}\n{self._conversation_meta(conversation)}", self.history_list
            )
            item.setData(Qt.ItemDataRole.UserRole, conversation["session_id"])
            item.setToolTip(title)
            item.setSizeHint(QSize(0, 62))
            if conversation["session_id"] == self.active_conversation_id:
                selected_row = index

        if selected_row >= 0:
            self.history_list.setCurrentRow(selected_row)
        else:
            self.history_list.clearSelection()
        self.history_list.blockSignals(False)
        self._refresh_history_actions()
        self._refresh_profile_views()

    def _refresh_history_actions(self) -> None:
        if not hasattr(self, "delete_chat_button"):
            return
        self.delete_chat_button.setEnabled(
            self._conversation_is_deletable(self._active_conversation())
        )

    def handle_history_selection(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return

        self._flush_response_stream(open_dialog=False)
        session_id = current.data(Qt.ItemDataRole.UserRole)
        if not session_id or session_id == self.active_conversation_id:
            return
        self._activate_conversation(str(session_id))

    def toggle_language(self) -> None:
        self._flush_response_stream(open_dialog=False)
        current_page = (
            self.stack.currentWidget().objectName()
            if hasattr(self, "stack")
            else "HomePage"
        )
        auth_tab_index = (
            self.auth_tabs.currentIndex() if hasattr(self, "auth_tabs") else 0
        )
        login_username = (
            self.login_username_input.text()
            if hasattr(self, "login_username_input")
            else ""
        )
        register_username = (
            self.register_username_input.text()
            if hasattr(self, "register_username_input")
            else ""
        )
        register_display_name = (
            self.register_display_name_input.text()
            if hasattr(self, "register_display_name_input")
            else ""
        )
        register_major = (
            self.register_major_input.text()
            if hasattr(self, "register_major_input")
            else ""
        )

        chat_message = (
            self.message_input.toPlainText()
            if hasattr(self, "message_input") and self.message_input is not None
            else ""
        )

        self.language = "zh" if self.language == "en" else "en"
        self._reset_dynamic_state()
        self._build_root()

        self.login_username_input.setText(login_username)
        self.register_username_input.setText(register_username)
        self.register_display_name_input.setText(register_display_name)
        self.register_major_input.setText(register_major)

        if current_page == "DashboardPage":
            self.stack.setCurrentWidget(self.dashboard_page)
            if (
                hasattr(self, "message_input")
                and self.message_input is not None
                and chat_message
            ):
                self.message_input.setPlainText(chat_message)
            if self.current_username and self.api_client.authenticated:
                self.sync_bootstrap_data(record_trace=False)
        elif current_page == "AuthPage":
            self._show_auth(auth_tab_index)
        else:
            self._show_home()

    def _build_home_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("HomePage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        nav_bar = QFrame()
        nav_bar.setObjectName("HomeNavBar")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(20, 16, 20, 16)
        nav_layout.setSpacing(10)

        brand = QLabel(self.app_title())
        brand.setObjectName("HomeBrand")
        subtitle = QLabel(self.ui("home_subtitle"))
        subtitle.setObjectName("SubtitleLabel")
        subtitle.setWordWrap(True)
        brand_group = QVBoxLayout()
        brand_group.setSpacing(4)
        brand_group.addWidget(brand)
        brand_group.addWidget(subtitle)

        lang_button = QPushButton(self.ui("lang_button"))
        lang_button.clicked.connect(self.toggle_language)
        login_button = QPushButton(self.ui("login"))
        login_button.clicked.connect(lambda: self._show_auth(0))
        register_button = QPushButton(self.ui("register"))
        register_button.setObjectName("PrimaryButton")
        register_button.clicked.connect(lambda: self._show_auth(1))

        nav_layout.addLayout(brand_group, 1)
        nav_layout.addWidget(lang_button)
        nav_layout.addWidget(login_button)
        nav_layout.addWidget(register_button)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 16, 24, 32)
        content_layout.setSpacing(28)

        hero = QFrame()
        hero.setObjectName("HomeHeroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(36, 36, 36, 36)
        hero_layout.setSpacing(16)

        hero_kicker = QLabel(self.ui("home_kicker"))
        hero_kicker.setObjectName("AuthKicker")
        hero_title = QLabel(self.app_title())
        hero_title.setObjectName("HomeHeroTitle")
        hero_title.setWordWrap(True)
        hero_subtitle = QLabel(self.ui("home_hero_subtitle"))
        hero_subtitle.setObjectName("HomeHeroSubtitle")
        hero_subtitle.setWordWrap(True)

        hero_buttons = QHBoxLayout()
        hero_buttons.setSpacing(10)
        start_button = QPushButton(self.ui("start_now"))
        start_button.setObjectName("PrimaryButton")
        start_button.clicked.connect(lambda: self._show_auth(0))
        create_button = QPushButton(self.ui("create_account"))
        create_button.clicked.connect(lambda: self._show_auth(1))
        hero_buttons.addWidget(start_button)
        hero_buttons.addWidget(create_button)
        hero_buttons.addStretch(1)

        hero_layout.addWidget(hero_kicker)
        hero_layout.addWidget(hero_title)
        hero_layout.addWidget(hero_subtitle)
        hero_layout.addLayout(hero_buttons)

        feature_grid = QGridLayout()
        feature_grid.setHorizontalSpacing(16)
        feature_grid.setVerticalSpacing(16)
        for index, item in enumerate(HOME_CORE_FEATURES):
            card = QFrame()
            card.setObjectName("HomeFeatureCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(22, 22, 22, 22)
            card_layout.setSpacing(10)
            card_title = QLabel(self.local(item["title"]))
            card_title.setObjectName("SectionTitle")
            card_detail = QLabel(self.local(item["detail"]))
            card_detail.setObjectName("BodyText")
            card_detail.setWordWrap(True)
            card_layout.addWidget(card_title)
            card_layout.addWidget(card_detail)
            feature_grid.addWidget(card, 0, index)

        section_title = QLabel(self.ui("home_section_title"))
        section_title.setObjectName("HomeSectionTitle")

        skills_grid = QGridLayout()
        skills_grid.setHorizontalSpacing(16)
        skills_grid.setVerticalSpacing(16)
        for index, item in enumerate(HOME_SKILLS):
            card = QFrame()
            card.setObjectName("HomeSkillCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(22, 22, 22, 22)
            card_layout.setSpacing(10)
            icon = QLabel(item["icon"])
            icon.setObjectName("SkillIcon")
            icon.setFixedWidth(60)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title = QLabel(self.local(item["title"]))
            title.setObjectName("SectionTitle")
            detail = QLabel(self.local(item["detail"]))
            detail.setObjectName("MutedText")
            detail.setWordWrap(True)
            card_layout.addWidget(icon)
            card_layout.addWidget(title)
            card_layout.addWidget(detail)
            skills_grid.addWidget(card, index // 3, index % 3)

        banner = QFrame()
        banner.setObjectName("HomeBannerCard")
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(28, 28, 28, 28)
        banner_layout.setSpacing(12)
        banner_title = QLabel(self.local(HOME_BANNER["title"]))
        banner_title.setObjectName("HomeSectionTitle")
        banner_detail = QLabel(self.local(HOME_BANNER["detail"]))
        banner_detail.setObjectName("BodyText")
        banner_detail.setWordWrap(True)
        banner_button = QPushButton(self.ui("enter_login"))
        banner_button.setObjectName("PrimaryButton")
        banner_button.clicked.connect(lambda: self._show_auth(0))
        banner_layout.addWidget(banner_title)
        banner_layout.addWidget(banner_detail)
        banner_layout.addWidget(banner_button, 0, Qt.AlignmentFlag.AlignLeft)

        content_layout.addWidget(hero)
        content_layout.addLayout(feature_grid)
        content_layout.addWidget(section_title)
        content_layout.addLayout(skills_grid)
        content_layout.addWidget(banner)
        content_layout.addStretch(1)

        scroll_area.setWidget(content)
        layout.addWidget(nav_bar)
        layout.addWidget(scroll_area, 1)
        return page

    def _build_auth_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("AuthPage")
        layout = QHBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(22)

        hero = QFrame()
        hero.setObjectName("AuthHeroFrame")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 28, 28, 28)
        hero_layout.setSpacing(14)

        kicker = QLabel(self.ui("auth_kicker"))
        kicker.setObjectName("AuthKicker")
        title = QLabel(self.app_title())
        title.setObjectName("HeroTitle")
        title.setWordWrap(True)
        body = QLabel(self.ui("auth_body"))
        body.setObjectName("HeroBody")
        body.setWordWrap(True)

        hero_layout.addWidget(kicker)
        hero_layout.addWidget(title)
        hero_layout.addWidget(body)

        summary_card = QFrame()
        summary_card.setObjectName("FeaturePill")
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(18, 16, 18, 16)
        summary_layout.setSpacing(8)
        summary_title = QLabel(self.ui("auth_capabilities_title"))
        summary_title.setObjectName("SectionTitle")
        summary_body = QLabel(self.ui("auth_capabilities_body"))
        summary_body.setObjectName("BodyText")
        summary_body.setWordWrap(True)
        summary_layout.addWidget(summary_title)
        summary_layout.addWidget(summary_body)
        hero_layout.addWidget(summary_card)

        hero_layout.addStretch(1)

        auth_card = QFrame()
        auth_card.setObjectName("AuthCard")
        auth_layout = QVBoxLayout(auth_card)
        auth_layout.setContentsMargins(26, 26, 26, 26)
        auth_layout.setSpacing(14)

        auth_title = QLabel(self.ui("welcome_back"))
        auth_title.setObjectName("AuthTitle")
        auth_subtitle = QLabel(self.ui("auth_subtitle"))
        auth_subtitle.setObjectName("HeroBody")
        auth_subtitle.setWordWrap(True)

        self.auth_tabs = QTabWidget()
        self.auth_tabs.addTab(self._build_login_tab(), self.ui("login"))
        self.auth_tabs.addTab(self._build_register_tab(), self.ui("register"))

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)
        back_home_button = QPushButton(self.ui("back_home"))
        back_home_button.clicked.connect(self._show_home)
        lang_button = QPushButton(self.ui("lang_button"))
        lang_button.clicked.connect(self.toggle_language)
        bottom_row.addWidget(back_home_button)
        bottom_row.addStretch(1)
        bottom_row.addWidget(lang_button)

        auth_layout.addWidget(auth_title)
        auth_layout.addWidget(auth_subtitle)
        auth_layout.addWidget(self.auth_tabs, 1)
        auth_layout.addLayout(bottom_row)

        layout.addWidget(hero, 6)
        layout.addWidget(auth_card, 5)
        return page

    def _build_login_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        self.login_username_input = QLineEdit()
        self.login_username_input.setObjectName("AuthInput")
        self.login_username_input.setPlaceholderText(self.ui("username"))
        self.login_password_input = QLineEdit()
        self.login_password_input.setObjectName("AuthInput")
        self.login_password_input.setPlaceholderText(self.ui("password"))
        self.login_password_input.setEchoMode(QLineEdit.EchoMode.Password)

        password_button = QPushButton(self.ui("sign_in"))
        password_button.setObjectName("PrimaryButton")
        password_button.clicked.connect(self.handle_password_login)

        layout.addWidget(self.login_username_input)
        layout.addWidget(self.login_password_input)
        layout.addWidget(password_button)
        layout.addStretch(1)
        return tab

    def _build_register_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self.register_username_input = QLineEdit()
        self.register_username_input.setObjectName("AuthInput")
        self.register_username_input.setPlaceholderText(self.ui("username"))
        self.register_display_name_input = QLineEdit()
        self.register_display_name_input.setObjectName("AuthInput")
        self.register_display_name_input.setPlaceholderText(self.ui("display_name"))
        self.register_major_input = QLineEdit()
        self.register_major_input.setObjectName("AuthInput")
        self.register_major_input.setPlaceholderText(self.ui("major"))
        self.register_password_input = QLineEdit()
        self.register_password_input.setObjectName("AuthInput")
        self.register_password_input.setPlaceholderText(self.ui("password"))
        self.register_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.register_confirm_input = QLineEdit()
        self.register_confirm_input.setObjectName("AuthInput")
        self.register_confirm_input.setPlaceholderText(self.ui("confirm_password"))
        self.register_confirm_input.setEchoMode(QLineEdit.EchoMode.Password)

        register_button = QPushButton(self.ui("create_account"))
        register_button.setObjectName("PrimaryButton")
        register_button.clicked.connect(self.handle_register)

        layout.addWidget(self.register_username_input)
        layout.addWidget(self.register_display_name_input)
        layout.addWidget(self.register_major_input)
        layout.addWidget(self.register_password_input)
        layout.addWidget(self.register_confirm_input)
        layout.addWidget(register_button)
        layout.addStretch(1)
        return tab

    def _build_dashboard_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("DashboardPage")
        root_layout = QVBoxLayout(page)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Slim top header bar
        header_bar = QFrame()
        header_bar.setObjectName("AppHeaderBar")
        header_bar_layout = QHBoxLayout(header_bar)
        header_bar_layout.setContentsMargins(0, 0, 0, 0)
        header_bar_layout.setSpacing(0)
        header_bar_layout.addLayout(self._build_header())
        root_layout.addWidget(header_bar)

        body_layout = QHBoxLayout()
        body_layout.setSpacing(0)
        body_layout.setContentsMargins(0, 0, 0, 0)

        sidebar = self._build_sidebar()
        center = self._build_center_panel()
        body_layout.addWidget(sidebar, 24)
        body_layout.addWidget(center, 76)
        root_layout.addLayout(body_layout)
        return page

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        title = QLabel(self.app_title())
        title.setObjectName("HomeBrand")

        lang_button = QPushButton(self.ui("lang_button"))
        lang_button.clicked.connect(self.toggle_language)
        settings_button = QPushButton(self.ui("settings_button"))
        settings_button.clicked.connect(self.open_settings_dialog)
        logout_button = QPushButton(self.ui("log_out"))
        logout_button.clicked.connect(self.logout)
        auth_button = self._build_header_hitl_button()

        layout.addWidget(title)
        layout.addStretch(1)
        layout.addWidget(auth_button)
        layout.addWidget(lang_button)
        layout.addWidget(settings_button)
        layout.addWidget(logout_button)
        return layout

    def _build_sidebar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("SidebarFrame")
        frame.setMinimumWidth(300)
        frame.setMaximumWidth(360)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)

        history_card = QFrame()
        history_card.setObjectName("PanelCard")
        history_layout = QVBoxLayout(history_card)
        history_layout.setContentsMargins(18, 18, 18, 18)
        history_layout.setSpacing(10)

        history_title = QLabel(self.ui("conversation_history"))
        history_title.setObjectName("SectionTitle")
        new_chat_button = QPushButton(self.ui("new_chat"))
        new_chat_button.setObjectName("SidebarActionButton")
        new_chat_button.clicked.connect(self.start_new_chat)
        delete_chat_button = QPushButton(self.ui("delete_chat"))
        delete_chat_button.setObjectName("SidebarActionButton")
        delete_chat_button.clicked.connect(self.delete_current_chat)
        self.delete_chat_button = delete_chat_button
        history_hint = QLabel(self.ui("conversation_history_hint"))
        history_hint.setObjectName("MutedText")
        history_hint.setWordWrap(True)
        self.history_list = QListWidget()
        self.history_list.setObjectName("ConversationList")
        self.history_list.currentItemChanged.connect(self.handle_history_selection)

        history_actions = QHBoxLayout()
        history_actions.setSpacing(8)
        history_actions.addWidget(delete_chat_button)
        history_actions.addWidget(new_chat_button)

        history_layout.addWidget(history_title)
        history_layout.addWidget(history_hint)
        history_layout.addLayout(history_actions)
        history_layout.addWidget(self.history_list)

        resources_card = QFrame()
        resources_card.setObjectName("PanelCard")
        resources_layout = QVBoxLayout(resources_card)
        resources_layout.setContentsMargins(18, 18, 18, 18)
        resources_layout.setSpacing(10)

        resources_title = QLabel(self.ui("read_materials"))
        resources_title.setObjectName("SectionTitle")
        resources_hint = QLabel(self.ui("read_materials_hint"))
        resources_hint.setObjectName("MutedText")
        resources_hint.setWordWrap(True)

        self.resource_list = QListWidget()
        self.resource_list.setObjectName("ResourceList")
        self.resource_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._load_resource_files()

        add_button = QPushButton(self.ui("add_resource"))
        add_button.setObjectName("SidebarActionButton")
        add_button.clicked.connect(self._add_resource_files)

        sync_bb_button = QPushButton(self.ui("sync_blackboard"))
        sync_bb_button.setObjectName("SidebarActionButton")
        sync_bb_button.clicked.connect(self._sync_blackboard_materials)

        resources_buttons = QVBoxLayout()
        resources_buttons.setSpacing(8)
        resources_buttons.addWidget(add_button)
        resources_buttons.addWidget(sync_bb_button)

        resources_layout.addWidget(resources_title)
        resources_layout.addWidget(resources_hint)
        resources_layout.addWidget(self.resource_list)
        resources_layout.addLayout(resources_buttons)

        layout.addWidget(history_card, 1)
        layout.addWidget(resources_card, 1)
        self._refresh_conversation_list()
        return frame

    def _build_center_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("CenterFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        self.center_tabs = QTabWidget()
        self.chat_tab = self._build_chat_tab()
        self.schedule_tab = self._build_schedule_tab()
        self.center_tabs.addTab(self.chat_tab, self.ui("tab_agent_chat"))
        self.center_tabs.addTab(self.schedule_tab, self.ui("tab_schedule"))
        layout.addWidget(self.center_tabs, 1)
        return frame

    def _build_chat_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Chat messages scroll area (seamless, no card wrapper) ──────────────
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setObjectName("ChatScrollArea")
        self.chat_scroll_area = scroll_area
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(0, 16, 0, 16)
        self.chat_layout.setSpacing(0)
        self.chat_layout.addStretch(1)
        scroll_area.setWidget(self.chat_container)
        layout.addWidget(scroll_area, 1)

        # ── Composer bar (floating rounded card at the bottom) ─────────────────
        composer_card = QFrame()
        composer_card.setObjectName("ChatComposerCard")
        composer_outer = QVBoxLayout(composer_card)
        composer_outer.setContentsMargins(16, 10, 16, 10)
        composer_outer.setSpacing(6)

        self.mode_button = None
        self.mode_menu = None
        self.mode_actions = {}

        # Input + send button on same row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.message_input = QTextEdit()
        self.message_input.setObjectName("ChatComposer")
        self.message_input.setPlaceholderText(self._message_placeholder_for_mode())
        self.message_input.setFixedHeight(80)
        self.message_input.installEventFilter(self)
        send_button = QPushButton("↑")
        send_button.setObjectName("SendButton")
        send_button.setToolTip(self.ui("send"))
        send_button.clicked.connect(self.handle_send_or_cancel)
        self.send_button = send_button
        input_row.addWidget(self.message_input, 1)
        input_row.addWidget(send_button, 0, Qt.AlignmentFlag.AlignBottom)

        # Mode selector + clear button row below input
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self._refresh_mode_selector()
        clear_button = QPushButton(self.ui("clear_draft"))
        clear_button.clicked.connect(self.message_input.clear)
        action_row.addStretch(1)
        action_row.addWidget(clear_button)

        composer_outer.addLayout(input_row)
        composer_outer.addLayout(action_row)
        layout.addWidget(composer_card)
        self._refresh_generation_controls()
        return tab

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if (
            hasattr(self, "message_input")
            and watched is self.message_input
            and event.type() == QEvent.Type.KeyPress
        ):
            key = event.key()
            modifiers = event.modifiers()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if modifiers & Qt.KeyboardModifier.ShiftModifier:
                    self.handle_send_or_cancel()
                    return True
                return False
        return super().eventFilter(watched, event)

    def _build_schedule_tab(self) -> QWidget:
        tab = QWidget()
        outer_layout = QVBoxLayout(tab)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        schedule_scroll = QScrollArea()
        schedule_scroll.setObjectName("SchedulePageScroll")
        schedule_scroll.setWidgetResizable(True)
        schedule_scroll.setFrameShape(QFrame.Shape.NoFrame)

        schedule_content = QWidget()
        schedule_content.setObjectName("SchedulePageContent")
        layout = QVBoxLayout(schedule_content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        header = QFrame()
        header.setObjectName("PanelCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 16, 16, 16)
        header_layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title = QLabel(self.ui("schedule_title"))
        title.setObjectName("SectionTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)

        body = QLabel(self.ui("calendar_hint"))
        body.setObjectName("MutedText")
        body.setWordWrap(True)
        self.schedule_summary_label = QLabel()
        self.schedule_summary_label.setObjectName("BadgeLabel")

        header_layout.addLayout(title_row)
        header_layout.addWidget(body)
        header_layout.addWidget(
            self.schedule_summary_label, 0, Qt.AlignmentFlag.AlignLeft
        )

        content = QVBoxLayout()
        content.setSpacing(14)

        calendar_panel = QFrame()
        calendar_panel.setObjectName("PanelCard")
        calendar_panel.setMinimumHeight(500)
        calendar_layout = QVBoxLayout(calendar_panel)
        calendar_layout.setContentsMargins(16, 16, 16, 16)
        calendar_layout.setSpacing(10)

        calendar_title = QLabel(self.ui("calendar_title"))
        calendar_title.setObjectName("CardTitle")
        self.schedule_calendar = QCalendarWidget()
        self.schedule_calendar.setObjectName("ScheduleCalendar")
        self.schedule_calendar.setGridVisible(True)
        self.schedule_calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.schedule_calendar.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        self.schedule_calendar.setMinimumHeight(420)
        self.schedule_calendar.selectionChanged.connect(
            self._on_schedule_selection_changed
        )
        calendar_layout.addWidget(calendar_title)
        calendar_layout.addWidget(self.schedule_calendar, 1)

        detail_panel = QFrame()
        detail_panel.setObjectName("PanelCard")
        detail_panel.setMinimumHeight(260)
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.setSpacing(0)

        detail_scroll = QScrollArea()
        detail_scroll.setObjectName("ScheduleDetailScroll")
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        detail_content = QWidget()
        detail_content.setObjectName("ScheduleDetailContent")
        detail_content_layout = QVBoxLayout(detail_content)
        detail_content_layout.setContentsMargins(0, 0, 0, 0)
        detail_content_layout.setSpacing(14)

        self.selected_day_label = QLabel()
        self.selected_day_label.setObjectName("SectionTitle")
        self.daily_schedule_list = QListWidget()
        self.daily_schedule_list.setObjectName("DailyScheduleList")
        self._configure_schedule_list(self.daily_schedule_list)

        upcoming_title = QLabel(self.ui("upcoming_events"))
        upcoming_title.setObjectName("CardTitle")
        self.upcoming_schedule_list = QListWidget()
        self.upcoming_schedule_list.setObjectName("DailyScheduleList")
        self._configure_schedule_list(self.upcoming_schedule_list)

        conflicts_title = QLabel(self.ui("conflict_notifications"))
        conflicts_title.setObjectName("CardTitle")
        self.schedule_conflict_list = QListWidget()
        self.schedule_conflict_list.setObjectName("ScheduleConflictList")
        self._configure_schedule_list(self.schedule_conflict_list)

        daily_section = QFrame()
        daily_section.setObjectName("ScheduleSection")
        daily_layout = QVBoxLayout(daily_section)
        daily_layout.setContentsMargins(0, 0, 0, 0)
        daily_layout.setSpacing(8)
        daily_layout.addWidget(self.selected_day_label)
        daily_layout.addWidget(self.daily_schedule_list)

        upcoming_section = QFrame()
        upcoming_section.setObjectName("ScheduleSection")
        upcoming_layout = QVBoxLayout(upcoming_section)
        upcoming_layout.setContentsMargins(0, 0, 0, 0)
        upcoming_layout.setSpacing(8)
        upcoming_layout.addWidget(upcoming_title)
        upcoming_layout.addWidget(self.upcoming_schedule_list)

        conflicts_section = QFrame()
        conflicts_section.setObjectName("ScheduleSection")
        conflicts_layout = QVBoxLayout(conflicts_section)
        conflicts_layout.setContentsMargins(0, 0, 0, 0)
        conflicts_layout.setSpacing(8)
        conflicts_layout.addWidget(conflicts_title)
        conflicts_layout.addWidget(self.schedule_conflict_list)

        detail_content_layout.addWidget(daily_section)
        detail_content_layout.addWidget(upcoming_section)
        detail_content_layout.addWidget(conflicts_section)
        detail_content_layout.addStretch(1)
        detail_scroll.setWidget(detail_content)
        detail_layout.addWidget(detail_scroll, 1)

        content.addWidget(calendar_panel)
        content.addWidget(detail_panel, 1)

        layout.addWidget(header)
        layout.addLayout(content, 1)
        schedule_scroll.setWidget(schedule_content)
        outer_layout.addWidget(schedule_scroll, 1)
        self._refresh_schedule_views()
        return tab

    def _build_header_hitl_button(self) -> QPushButton:
        open_dialog_button = QPushButton(self.ui("open_authorization_dialog"))
        open_dialog_button.setObjectName("HeaderHitlButton")
        open_dialog_button.setMinimumWidth(210)
        open_dialog_button.setFixedHeight(32)
        open_dialog_button.clicked.connect(self.open_hitl_dialog)
        return open_dialog_button

    def _sender_label(self, sender: str) -> str:
        return self.ui("you") if sender == "user" else self.ui("agent")

    def _status_label(self, status: str) -> str:
        return self.ui(f"status_{status}")

    def _load_chat_messages(self, messages: list[dict[str, Any]]) -> None:
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for message in messages:
            kind = str(message.get("kind", "text"))
            sender = str(message.get("sender", "agent"))
            if kind == "schedule":
                payload = message.get("payload", {})
                widget = ScheduleResultWidget(
                    self._sender_label(sender),
                    self.ui("chat_schedule_card_title"),
                    str(message.get("text", "")),
                    (
                        list(payload.get("events", []))
                        if isinstance(payload, dict)
                        else []
                    ),
                    (
                        list(payload.get("conflicts", []))
                        if isinstance(payload, dict)
                        else []
                    ),
                    UI_TEXTS[self.language],
                )
            elif kind == "encyclopedia":
                payload = message.get("payload", {})
                widget = EncyclopediaResultWidget(
                    self._sender_label(sender),
                    self.ui("chat_encyclopedia_card_title"),
                    str(message.get("text", "")),
                    str(payload.get("query", "")) if isinstance(payload, dict) else "",
                    (
                        str(payload.get("answer_markdown", ""))
                        if isinstance(payload, dict)
                        else ""
                    ),
                    (
                        [str(item) for item in payload.get("citations", [])]
                        if isinstance(payload, dict)
                        else []
                    ),
                    UI_TEXTS[self.language],
                )
            elif kind == "library":
                payload = message.get("payload", {})
                rooms = payload.get("rooms", []) if isinstance(payload, dict) else []
                widget = LibraryResultWidget(
                    self._sender_label(sender),
                    self.ui("chat_library_card_title"),
                    str(message.get("text", "")),
                    (
                        str(payload.get("query_time", ""))
                        if isinstance(payload, dict)
                        else ""
                    ),
                    (
                        str(payload.get("query_location", ""))
                        if isinstance(payload, dict)
                        else ""
                    ),
                    (
                        payload.get("query_capacity")
                        if isinstance(payload, dict)
                        else None
                    ),
                    rooms if isinstance(rooms, list) else [],
                    UI_TEXTS[self.language],
                )
            else:
                widget = BubbleWidget(
                    sender,
                    self._sender_label(sender),
                    str(message.get("text", "")),
                    self.ui("message_type_chat"),
                )
            self.chat_layout.insertWidget(self.chat_layout.count() - 1, widget)

        # Attach current trace events to the last agent BubbleWidget
        self._attach_inline_trace()
        self._refresh_conversation_list()
        self._scroll_chat_to_bottom()

    def _load_trace_events(self, events: list[dict[str, str]]) -> None:
        if not hasattr(self, "trace_layout"):
            self._attach_inline_trace()
            self._sync_active_conversation()
            return

        while self.trace_layout.count() > 1:
            item = self.trace_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for event in events:
            self.trace_layout.insertWidget(
                self.trace_layout.count() - 1,
                TraceItem(
                    event["phase"],
                    event["title"],
                    event["detail"],
                    event["status"],
                    self._status_label(event["status"]),
                ),
            )
        # Also refresh the inline trace in the last agent chat bubble
        self._attach_inline_trace()
        self._sync_active_conversation()

    def _attach_inline_trace(self) -> None:
        """Find the last BubbleWidget for an agent message and push trace events into it."""
        if not hasattr(self, "chat_layout") or not self.trace_events:
            return
        last_bubble: BubbleWidget | None = None
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if item and isinstance(item.widget(), BubbleWidget):
                w = item.widget()
                if hasattr(w, "_trace_panel") and w._trace_panel is not None:  # type: ignore[union-attr]
                    last_bubble = w  # type: ignore[assignment]
        if last_bubble is not None:
            last_bubble.set_trace_events(self.trace_events, self._status_label)

    def _refresh_schedule_views(self) -> None:
        if not hasattr(self, "schedule_calendar"):
            return

        grouped = events_by_date(self.schedule_events)
        self._apply_schedule_date_marks(grouped)

        if hasattr(self, "schedule_summary_label"):
            self.schedule_summary_label.setText(
                self.ui(
                    "schedule_summary",
                    days=len(grouped),
                    events=len(self.schedule_events),
                )
            )

        if self.selected_schedule_day is None:
            self.selected_schedule_day = (
                next_event_date(self.schedule_events) or date.today()
            )

        selected_qdate = self._qdate_from_day(self.selected_schedule_day)
        if self.schedule_calendar.selectedDate() != selected_qdate:
            self.schedule_calendar.setSelectedDate(selected_qdate)

        self._render_selected_day_schedule(self.selected_schedule_day, grouped)
        self._render_upcoming_schedule(grouped)
        self._render_schedule_conflicts()

    def _apply_schedule_date_marks(
        self, grouped: dict[date, list[dict[str, Any]]]
    ) -> None:
        empty_format = QTextCharFormat()
        for marked_day in self._highlighted_schedule_dates:
            self.schedule_calendar.setDateTextFormat(
                self._qdate_from_day(marked_day), empty_format
            )

        event_format = QTextCharFormat()
        event_format.setBackground(QColor(59, 130, 246, 100))
        event_format.setForeground(QColor("#f0f4ff"))
        event_format.setFontWeight(QFont.Weight.Bold)

        conflict_format = QTextCharFormat()
        conflict_format.setBackground(QColor(239, 68, 68, 100))
        conflict_format.setForeground(QColor("#f0f4ff"))
        conflict_format.setFontWeight(QFont.Weight.Bold)

        conflict_days = self._conflict_dates(grouped)
        for day_value in grouped:
            fmt = conflict_format if day_value in conflict_days else event_format
            self.schedule_calendar.setDateTextFormat(
                self._qdate_from_day(day_value), fmt
            )
        self._highlighted_schedule_dates = set(grouped)

    def _conflict_dates(self, grouped: dict[date, list[dict[str, Any]]]) -> set[date]:
        conflict_days: set[date] = set()
        for conflict in self.conflicts:
            detail = f"{conflict.get('title', '')} {conflict.get('detail', '')}"
            for day_value in grouped:
                if day_value.isoformat() in detail:
                    conflict_days.add(day_value)
        return conflict_days

    def _on_schedule_selection_changed(self) -> None:
        if not hasattr(self, "schedule_calendar"):
            return
        self.selected_schedule_day = self._day_from_qdate(
            self.schedule_calendar.selectedDate()
        )
        self._render_selected_day_schedule(
            self.selected_schedule_day, events_by_date(self.schedule_events)
        )

    def _render_selected_day_schedule(
        self,
        selected_day: date,
        grouped: dict[date, list[dict[str, Any]]],
    ) -> None:
        if not hasattr(self, "daily_schedule_list"):
            return

        self.selected_day_label.setText(
            self.ui(
                "selected_day",
                date=self._qdate_from_day(selected_day).toString("yyyy-MM-dd ddd"),
            )
        )
        self.daily_schedule_list.clear()
        day_events = grouped.get(selected_day, [])
        if not day_events:
            self._add_placeholder_item(
                self.daily_schedule_list, self.ui("no_events_for_day")
            )
            self._fit_schedule_list_to_contents(
                self.daily_schedule_list, min_height=74, max_height=150
            )
            return

        for event in day_events:
            self._add_schedule_item(
                self.daily_schedule_list,
                self._format_schedule_item(event, selected_day),
            )
        self._fit_schedule_list_to_contents(
            self.daily_schedule_list, min_height=120, max_height=240
        )

    def _render_upcoming_schedule(
        self, grouped: dict[date, list[dict[str, Any]]]
    ) -> None:
        if not hasattr(self, "upcoming_schedule_list"):
            return

        self.upcoming_schedule_list.clear()
        today = date.today()
        upcoming: list[tuple[date, dict[str, Any]]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for day_value in sorted(day for day in grouped if day >= today):
            for event in grouped[day_value]:
                key = (
                    str(event.get("title", "")),
                    str(event.get("time", "")),
                    str(event.get("source", "")),
                    str(event.get("detail", "")),
                )
                if key in seen:
                    continue
                seen.add(key)
                upcoming.append((day_value, event))

        if not upcoming:
            self._add_placeholder_item(
                self.upcoming_schedule_list, self.ui("no_upcoming_events")
            )
            self._fit_schedule_list_to_contents(
                self.upcoming_schedule_list, min_height=74, max_height=150
            )
            return

        for day_value, event in sorted(
            upcoming, key=lambda item: event_sort_key(item[1])
        )[:5]:
            self._add_schedule_item(
                self.upcoming_schedule_list,
                self._format_schedule_item(event, day_value),
            )
        self._fit_schedule_list_to_contents(
            self.upcoming_schedule_list, min_height=96, max_height=190
        )

    def _render_schedule_conflicts(self) -> None:
        if not hasattr(self, "schedule_conflict_list"):
            return

        self.schedule_conflict_list.clear()
        if not self.conflicts:
            self._add_placeholder_item(
                self.schedule_conflict_list, self.ui("no_conflicts")
            )
            self._fit_schedule_list_to_contents(
                self.schedule_conflict_list, min_height=74, max_height=150
            )
            return

        for conflict in self.conflicts[:5]:
            title = str(conflict.get("title", "")).strip() or self.ui(
                "conflict_notifications"
            )
            detail = str(conflict.get("detail", "")).strip()
            text = f"{title}\n{detail}" if detail else title
            self._add_schedule_item(self.schedule_conflict_list, text)
        self._fit_schedule_list_to_contents(
            self.schedule_conflict_list, min_height=96, max_height=180
        )

    def _format_schedule_item(
        self, event: dict[str, Any], selected_day: date | None = None
    ) -> str:
        title = str(event.get("title", "")).strip() or self.ui("upcoming_events")
        source = str(event.get("source", "")).strip()
        time_text = format_event_time(event, selected_day)
        detail = str(event.get("detail", "")).strip()
        meta = " | ".join(part for part in [time_text, source] if part)
        lines = [title]
        if meta:
            lines.append(meta)
        if detail:
            lines.append(detail)
        return "\n".join(lines)

    def _add_placeholder_item(self, list_widget: QListWidget, text: str) -> None:
        item = self._add_schedule_item(list_widget, text)
        item.setFlags(Qt.ItemFlag.NoItemFlags)

    def _add_schedule_item(
        self, list_widget: QListWidget, text: str
    ) -> QListWidgetItem:
        item = QListWidgetItem(text, list_widget)
        item.setSizeHint(QSize(0, self._schedule_item_height(text)))
        return item

    def _configure_schedule_list(self, list_widget: QListWidget) -> None:
        list_widget.setWordWrap(True)
        list_widget.setUniformItemSizes(False)
        list_widget.setTextElideMode(Qt.TextElideMode.ElideNone)
        list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_widget.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)

    def _fit_schedule_list_to_contents(
        self,
        list_widget: QListWidget,
        *,
        min_height: int,
        max_height: int,
    ) -> None:
        content_height = 18
        for index in range(list_widget.count()):
            content_height += list_widget.item(index).sizeHint().height() + 6
        height = max(min_height, min(max_height, content_height))
        list_widget.setMinimumHeight(height)
        list_widget.setMaximumHeight(height)

    @staticmethod
    def _schedule_item_height(text: str) -> int:
        explicit_lines = text.count("\n") + 1
        wrapped_lines = sum(
            max(1, (len(line) + 42) // 43) for line in text.splitlines() or [""]
        )
        line_count = max(explicit_lines, wrapped_lines)
        return max(46, min(150, 24 + line_count * 22))

    @staticmethod
    def _qdate_from_day(day_value: date) -> QDate:
        return QDate(day_value.year, day_value.month, day_value.day)

    @staticmethod
    def _day_from_qdate(qdate: QDate) -> date:
        return date(qdate.year(), qdate.month(), qdate.day())

    def _refresh_profile_views(self) -> None:
        if hasattr(self, "header_user_label"):
            self.header_user_label.setText(
                self.ui("signed_in_as", name=self.current_user["name"])
            )
        if hasattr(self, "backend_mode_label"):
            self.backend_mode_label.setText(self.backend_status_text())

    def open_settings_dialog(self) -> None:
        dialog = SettingsDialog(
            self,
            UI_TEXTS[self.language],
            self.cas_settings,
            self.api_settings,
            self.working_dir_settings,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.intent:
            return

        payload = dialog.payload()
        if dialog.intent == "cas":
            cas_account = payload["cas_username"] or None
            cas_password = payload["cas_password"] or None
            if cas_account is None and cas_password is None:
                QMessageBox.warning(
                    self,
                    self.ui("settings_dialog_title"),
                    self.ui("settings_missing_cas"),
                )
                return

            if self.api_client.enabled and self.api_client.authenticated:
                try:
                    self.api_client.update_credentials(
                        cas_account=cas_account,
                        cas_password=cas_password,
                    )
                except BackendApiError as exc:
                    QMessageBox.warning(
                        self,
                        self.ui("settings_dialog_title"),
                        self.ui("trace_backend_unavailable_detail", error=str(exc)),
                    )
                    return

            self.cas_settings = {
                "username": cas_account or self.cas_settings.get("username", ""),
                "password": cas_password or self.cas_settings.get("password", ""),
                "saved": True,
            }
            QMessageBox.information(
                self,
                self.ui("settings_saved_title"),
                self.ui("settings_cas_saved"),
            )
            return

        if dialog.intent == "workdir":
            workdir = payload["working_dir"]
            if not workdir:
                QMessageBox.warning(
                    self,
                    self.ui("settings_dialog_title"),
                    self.ui("settings_missing_workdir"),
                )
                return

            if self.api_client.enabled and self.api_client.authenticated:
                try:
                    self.api_client.update_credentials(working_dir=workdir)
                except BackendApiError as exc:
                    QMessageBox.warning(
                        self,
                        self.ui("settings_dialog_title"),
                        self.ui("trace_backend_unavailable_detail", error=str(exc)),
                    )
                    return

            self.working_dir_settings = {"path": workdir, "saved": True}
            QMessageBox.information(
                self,
                self.ui("settings_saved_title"),
                self.ui("settings_workdir_saved"),
            )
            return

        if not payload["api_key"]:
            QMessageBox.warning(
                self,
                self.ui("settings_dialog_title"),
                self.ui("settings_missing_api"),
            )
            return

        if self.api_client.enabled and self.api_client.authenticated:
            try:
                self.api_client.update_credentials(llm_api_key=payload["api_key"])
            except BackendApiError as exc:
                QMessageBox.warning(
                    self,
                    self.ui("settings_dialog_title"),
                    self.ui("trace_backend_unavailable_detail", error=str(exc)),
                )
                return

        self.api_settings = {
            "api_key": payload["api_key"],
            "saved": True,
        }
        QMessageBox.information(
            self,
            self.ui("settings_saved_title"),
            self.ui("settings_api_saved"),
        )

    def _show_home(self) -> None:
        self.stack.setCurrentWidget(self.home_page)

    def _show_auth(self, tab_index: int = 0) -> None:
        self.auth_tabs.setCurrentIndex(tab_index)
        self.stack.setCurrentWidget(self.auth_page)

    def _complete_login(
        self,
        username: str,
        *,
        user_id: str | None = None,
        display_name: str | None = None,
        major: str | None = None,
    ) -> None:
        self.current_username = username
        self.current_user_id_value = user_id or username
        if display_name or major:
            self.remote_profile = {
                "name": display_name or username,
                "major": major or self.local(PROFILE["major"]),
            }
        else:
            self.remote_profile = None
        self._reset_dynamic_state()
        self._build_root()
        self.stack.setCurrentWidget(self.dashboard_page)
        self.sync_bootstrap_data(record_trace=True)

    def sync_bootstrap_data(self, record_trace: bool) -> None:
        if not (
            self.api_client.enabled
            and self.api_client.authenticated
            and self.current_username
        ):
            return

        _record_trace = record_trace

        def _on_done(payload):
            self._apply_bootstrap_payload(payload)
            if _record_trace:
                self._append_trace(
                    self.local({"en": "Observation", "zh": "观察"}),
                    self.ui("trace_bootstrap_loaded_title"),
                    self.ui("trace_bootstrap_loaded_detail"),
                    "done",
                )

        def _on_error(err):
            if _record_trace:
                self._append_trace(
                    self.local({"en": "Observation", "zh": "观察"}),
                    self.ui("trace_backend_unavailable_title"),
                    self.ui("trace_backend_unavailable_detail", error=err),
                    "pending",
                )

        self._start_worker(self.api_client.bootstrap_dashboard, _on_done, _on_error)

    def _apply_bootstrap_payload(self, payload: dict[str, Any]) -> None:
        self._flush_response_stream(open_dialog=False)
        user_profile = payload.get("user_profile", {})
        display_name = str(
            user_profile.get("display_name")
            or self.current_username
            or self.local(PROFILE["name"])
        )
        major = str(user_profile.get("major") or self.local(PROFILE["major"]))
        self.current_user_id_value = str(
            user_profile.get("user_id") or self.current_user_id()
        )
        self.remote_profile = {
            "name": display_name,
            "major": major,
        }
        self.current_user = {
            "name": display_name,
            "major": major,
            "focus": self.ui("authenticated_focus"),
        }

        working_dir = user_profile.get("working_dir")
        if working_dir:
            self.working_dir_settings = {"path": str(working_dir), "saved": True}

        active_session_id = str(payload.get("active_session_id", "")).strip()
        chat_history = payload.get("chat_history", [])
        if active_session_id:
            normalized_messages = (
                self._normalize_backend_chat_history(chat_history)
                if isinstance(chat_history, list)
                else []
            )
            conversation = self._create_conversation(
                session_id=active_session_id,
                messages=normalized_messages,
                trace=[],
                pending_hitl_request=None,
                messages_loaded=True,
            )
            self.conversations = [conversation]
            self.active_conversation_id = active_session_id
            self.session_id = active_session_id
            self.chat_messages = list(normalized_messages)
            self.trace_events = []
            self.pending_hitl_request = None
            self._load_chat_messages(self.chat_messages)
            self._load_trace_events(self.trace_events)

        materials = payload.get("materials", [])
        if isinstance(materials, list):
            self.material_records = [
                item for item in materials if isinstance(item, dict)
            ]
            self.resource_files = [
                str(
                    item.get("file_name")
                    or item.get("name")
                    or item.get("file_id")
                    or "resource"
                )
                for item in materials
            ]
            self._load_resource_files()

        local_schedule = payload.get("local_schedule", {})
        if isinstance(local_schedule, dict):
            events = local_schedule.get("events", [])
            conflicts = local_schedule.get("conflicts", [])
            if isinstance(events, list):
                self.schedule_events = self._merge_schedule_event_lists(
                    self._normalize_schedule_events(events),
                    self.frontend_schedule_events,
                )
            if isinstance(conflicts, list):
                self.conflicts = self._normalize_conflicts(conflicts)
            self._refresh_schedule_views()

        self._sync_remote_sessions()
        self._refresh_profile_views()

    def _apply_agent_response(
        self,
        response: dict[str, Any],
        auto_open_hitl: bool = True,
        trace_already_streamed: bool = False,
    ) -> None:
        assistant_message = response.get("assistant_message", {})
        assistant_text = str(assistant_message.get("content", "")).strip()
        trace_items: list[dict[str, str]] = []
        trace = response.get("trace", [])
        if not trace_already_streamed and isinstance(trace, list) and trace:
            trace_items.extend(self._normalize_backend_trace_events(trace))

        error_payload = response.get("error")
        if isinstance(error_payload, dict):
            error_message = str(error_payload.get("message", "")).strip()
            if error_message:
                trace_items.append(
                    {
                        "phase": self.local({"en": "Reflection", "zh": "反思"}),
                        "title": str(error_payload.get("code", "backend_error")),
                        "detail": error_message,
                        "status": "error",
                    }
                )

        hitl_request = response.get("hitl_request")
        pending_hitl_request = (
            self._normalize_hitl_request(hitl_request)
            if isinstance(hitl_request, dict)
            else None
        )
        extra_messages = self._build_response_cards(response)
        if extra_messages:
            assistant_text = ""
        inferred_schedule_event = self._add_frontend_schedule_event_from_reply(
            assistant_text
        )
        if inferred_schedule_event and not any(
            item.get("kind") == "schedule" for item in extra_messages
        ):
            extra_messages.append(
                self._create_schedule_message(
                    intro=self.ui("schedule_card_intro"),
                    events=[inferred_schedule_event],
                    conflicts=self.conflicts,
                )
            )
        self._queue_response_stream(
            assistant_text=assistant_text,
            trace_items=trace_items,
            extra_messages=extra_messages,
            pending_hitl_request=pending_hitl_request,
            auto_open_hitl=auto_open_hitl,
        )
        self._sync_remote_sessions()

    def _start_worker(self, fn, on_finished, on_error=None) -> ApiWorker:
        """Start fn() on a background thread; call on_finished(result) or on_error(msg) on the main thread."""
        worker = ApiWorker(fn, parent=self)
        self._active_workers.append(worker)
        worker.finished.connect(on_finished)
        if on_error:
            worker.errored.connect(on_error)
        worker.finished.connect(
            lambda _: (
                self._active_workers.remove(worker)
                if worker in self._active_workers
                else None
            )
        )
        worker.errored.connect(
            lambda _: (
                self._active_workers.remove(worker)
                if worker in self._active_workers
                else None
            )
        )
        worker.start()
        return worker

    def _run_remote_agent(
        self,
        *,
        message: str,
        attachments: list[dict[str, Any]] | None = None,
        hitl_reply: dict[str, Any] | None = None,
        auto_open_hitl: bool = True,
    ) -> bool:
        if not (
            self.api_client.enabled
            and self.api_client.authenticated
            and self.current_username
        ):
            return False

        user_id = self.current_user_id()
        session_id = self.session_id
        _attachments = attachments or []
        _auto_open_hitl = auto_open_hitl

        self.trace_events = []
        self._load_trace_events(self.trace_events)

        worker = AgentStreamWorker(
            self.api_client,
            user_id=user_id,
            session_id=session_id,
            message=message,
            attachments=_attachments,
            hitl_reply=hitl_reply,
            parent=self,
        )
        self._active_workers.append(worker)
        self.active_agent_worker = worker

        def _on_trace(data: dict) -> None:
            if self.active_agent_worker is not worker:
                return
            phase = str(data.get("phase", "Observation"))
            title = str(data.get("title", ""))
            detail = str(data.get("detail", ""))
            status = str(data.get("status", "running"))
            self._append_trace(phase, title, detail, status)

        def _on_done(response):
            if self.active_agent_worker is not worker:
                return
            self.active_agent_worker = None
            self._remove_thinking_indicator()
            self._apply_agent_response(
                response,
                auto_open_hitl=_auto_open_hitl,
                trace_already_streamed=True,
            )
            self._refresh_generation_controls()

        def _on_error(err):
            if self.active_agent_worker is not worker:
                return
            self.active_agent_worker = None
            self._remove_thinking_indicator()
            self._append_trace(
                self.local({"en": "Observation", "zh": "观察"}),
                self.ui("trace_backend_unavailable_title"),
                self.ui("trace_backend_unavailable_detail", error=err),
                "pending",
            )
            self._refresh_generation_controls()

        worker.trace_streamed.connect(_on_trace)
        worker.finished.connect(_on_done)
        worker.errored.connect(_on_error)
        worker.finished.connect(
            lambda _: (
                self._active_workers.remove(worker)
                if worker in self._active_workers
                else None
            )
        )
        worker.errored.connect(
            lambda _: (
                self._active_workers.remove(worker)
                if worker in self._active_workers
                else None
            )
        )
        worker.start()
        return True

    def handle_password_login(self) -> None:
        username = self.login_username_input.text().strip()
        password = self.login_password_input.text()
        if not username or not password:
            QMessageBox.warning(
                self, self.ui("login_failed"), self.ui("enter_both_username_password")
            )
            return

        _username = username
        _default_major = self.local(PROFILE["major"])

        def _call():
            return self.api_client.login(_username, password)

        def _on_done(response):
            self._complete_login(
                _username,
                user_id=str(response.get("user_id", _username)),
                display_name=str(response.get("display_name", _username)),
                major=str(response.get("major", _default_major)),
            )

        def _on_error(err):
            QMessageBox.warning(
                self, self.ui("login_failed"), self.ui("login_error_body")
            )

        self._start_worker(_call, _on_done, _on_error)

    def handle_register(self) -> None:
        username = self.register_username_input.text().strip()
        display_name = self.register_display_name_input.text().strip()
        major = self.register_major_input.text().strip()
        password = self.register_password_input.text()
        confirm = self.register_confirm_input.text()

        if not username:
            QMessageBox.warning(
                self, self.ui("register_failed"), self.ui("choose_username")
            )
            return
        if not display_name:
            QMessageBox.warning(
                self, self.ui("register_failed"), self.ui("choose_display_name")
            )
            return
        if not major:
            QMessageBox.warning(
                self, self.ui("register_failed"), self.ui("choose_major")
            )
            return
        if not password or not confirm:
            QMessageBox.warning(
                self, self.ui("register_failed"), self.ui("enter_confirm_password")
            )
            return
        if password != confirm:
            QMessageBox.warning(
                self, self.ui("register_failed"), self.ui("passwords_do_not_match")
            )
            return

        _username = username
        _display_name = display_name
        _major = major

        def _call():
            return self.api_client.register(_username, password, _display_name, _major)

        def _on_done(response):
            self._complete_login(
                _username,
                user_id=str(response.get("user_id", _username)),
                display_name=str(response.get("display_name", _display_name)),
                major=str(response.get("major", _major)),
            )

        def _on_error(err):
            QMessageBox.warning(
                self, self.ui("register_failed"), self.ui("register_error_body")
            )

        self._start_worker(_call, _on_done, _on_error)

    def start_new_chat(self) -> None:
        self._flush_response_stream(open_dialog=False)
        conversation = self._active_conversation()
        if conversation is not None:
            has_user_messages = any(
                item["sender"] == "user" for item in conversation["messages"]
            )
            has_trace = bool(conversation["trace"])
            if not has_user_messages and not has_trace:
                self._activate_conversation(conversation["session_id"])
                if hasattr(self, "message_input"):
                    self.message_input.clear()
                return

        new_conversation = self._create_conversation()
        self.conversations.insert(0, new_conversation)
        self._activate_conversation(new_conversation["session_id"])
        if hasattr(self, "message_input"):
            self.message_input.clear()

    def delete_current_chat(self) -> None:
        self._flush_response_stream(open_dialog=False)
        conversation = self._active_conversation()
        if not self._conversation_is_deletable(conversation):
            self._refresh_history_actions()
            return

        result = QMessageBox.question(
            self,
            self.ui("delete_chat_confirm_title"),
            self.ui("delete_chat_confirm_body"),
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        session_id = str(conversation["session_id"])
        should_delete_remote = any(
            item.get("sender") == "user" for item in conversation.get("messages", [])
        )
        should_delete_remote = should_delete_remote or bool(
            self._clean_optional_text(conversation.get("remote_updated_at"))
        )
        should_delete_remote = should_delete_remote or bool(
            self._clean_optional_text(conversation.get("title"))
        )

        if (
            self.api_client.enabled
            and self.api_client.authenticated
            and should_delete_remote
        ):
            try:
                self.api_client.delete_session(session_id)
            except BackendApiError as exc:
                if "HTTP 404" not in str(exc):
                    QMessageBox.warning(
                        self,
                        self.ui("delete_chat_failed_title"),
                        self.ui("delete_chat_failed_body", details=str(exc)),
                    )
                    return

        self.conversations = [
            item for item in self.conversations if item["session_id"] != session_id
        ]
        if not self.conversations:
            self.session_id = self._new_session_id()
            replacement = self._create_conversation(session_id=self.session_id)
            self.conversations = [replacement]
        self._activate_conversation(self.conversations[0]["session_id"])

    def logout(self) -> None:
        self._flush_response_stream(open_dialog=False)
        if self.api_client.authenticated:
            try:
                self.api_client.logout()
            except BackendApiError:
                self.api_client.clear_token()
        self.current_username = None
        self.current_user_id_value = None
        self.remote_profile = None
        self.pending_hitl_request = None
        self.material_records = []
        self.resource_files = []
        self.session_id = self._new_session_id()
        self._reset_dynamic_state()
        self._build_root()
        self._show_home()

    def handle_send_or_cancel(self) -> None:
        if self._agent_response_active():
            self._cancel_agent_generation()
            return
        self.handle_send_message()

    def handle_send_message(self) -> None:
        self._flush_response_stream(open_dialog=False)
        text = self.message_input.toPlainText().strip()
        if not text:
            return

        attachments = self._selected_material_attachments()
        self.chat_messages.append(self._create_text_message("user", text))
        self._move_active_conversation_to_top()
        self._load_chat_messages(self.chat_messages)
        if self._run_remote_agent(message=text, attachments=attachments):
            self.message_input.clear()
            self._show_thinking_indicator()
            self._refresh_generation_controls()
            return

        QMessageBox.warning(
            self,
            self.ui("backend_disconnected_title"),
            self.ui("backend_disconnected_body"),
        )

    def _append_trace(self, phase: str, title: str, detail: str, status: str) -> None:
        event = {
            "phase": phase,
            "title": title,
            "detail": detail,
            "status": status,
        }
        self.trace_events.append(event)
        self._load_trace_events(self.trace_events)

    def open_hitl_dialog(self) -> None:
        self._flush_response_stream(open_dialog=False)
        if not self.pending_hitl_request:
            QMessageBox.information(
                self,
                self.ui("hitl_dialog_title"),
                self.ui("no_pending_hitl"),
            )
            return
        request_payload = self.pending_hitl_request
        dialog = HitlDialog(self, UI_TEXTS[self.language], request_payload)
        accepted = dialog.exec()

        request_id = (
            str(request_payload.get("request_id", "")).strip()
            if isinstance(request_payload, dict)
            else ""
        )
        if request_id and self._run_remote_agent(
            message="",
            hitl_reply={"request_id": request_id, "approved": bool(accepted)},
            auto_open_hitl=False,
        ):
            return

        detail = (
            self.ui("trace_hitl_approved")
            if accepted
            else self.ui("trace_hitl_pending")
        )
        self._append_trace(
            self.local({"en": "Tool Use", "zh": "工具调用"}),
            self.ui("trace_hitl_update_title"),
            detail,
            "done" if accepted else "pending",
        )

    def refresh_schedule_data(self) -> None:
        self._flush_response_stream(open_dialog=False)
        if not (
            self.api_client.enabled
            and self.api_client.authenticated
            and self.current_username
        ):
            return

        def _on_done(payload):
            events = payload.get("events", [])
            conflicts = payload.get("conflicts", [])
            if isinstance(events, list):
                self.schedule_events = self._merge_schedule_event_lists(
                    self._normalize_schedule_events(events),
                    self.frontend_schedule_events,
                )
            if isinstance(conflicts, list):
                self.conflicts = self._normalize_conflicts(conflicts)
            self._refresh_schedule_views()
            if hasattr(self, "center_tabs") and hasattr(self, "schedule_tab"):
                self.center_tabs.setCurrentWidget(self.schedule_tab)
            self._queue_response_stream(
                assistant_text="",
                trace_items=[
                    {
                        "phase": self.local({"en": "Observation", "zh": "观察"}),
                        "title": self.ui("trace_schedule_refresh_title"),
                        "detail": self.ui("trace_schedule_refresh_detail"),
                        "status": "done",
                    }
                ],
                extra_messages=[
                    self._create_schedule_message(
                        intro=self.ui("schedule_card_intro"),
                        events=self.schedule_events,
                        conflicts=self.conflicts,
                    )
                ],
            )

        def _on_error(err):
            QMessageBox.warning(
                self,
                self.ui("refresh_schedule_failed_title"),
                self.ui("refresh_schedule_failed_body", details=err),
            )
            self._append_trace(
                self.local({"en": "Observation", "zh": "观察"}),
                self.ui("refresh_schedule_failed_title"),
                err,
                "error",
            )

        self._start_worker(self.api_client.refresh_schedule, _on_done, _on_error)

    def _cleanup_bb_sync(self, result: int) -> None:
        timer = getattr(self, "_bb_sync_timer", None)
        if isinstance(timer, QTimer):
            timer.stop()
        self._bb_sync_polling = False
        job_id = getattr(self, "_bb_sync_job_id", None)
        if job_id:
            self._bb_sync_job_id = None

            def _call_cancel():
                return self.api_client.cancel_sync_blackboard_job(job_id)

            self._start_worker(_call_cancel, lambda _x: None, lambda _e: None)

    def _sync_blackboard_materials(self) -> None:
        if not (self.api_client.enabled and self.api_client.authenticated):
            QMessageBox.information(
                self,
                self.ui("sync_blackboard_unavailable_title"),
                self.ui("sync_blackboard_unavailable_body"),
            )
            return

        existing_names = {
            self._resource_display_name(resource).lower()
            for resource in self.resource_files
        }

        def _start_job():
            return self.api_client.start_sync_blackboard_job()

        def _on_job_started(payload):
            if not isinstance(payload, dict):
                QMessageBox.warning(
                    self,
                    self.ui("sync_blackboard_failed_title"),
                    self.ui("sync_blackboard_failed_body", details="invalid_response"),
                )
                return
            job_id = str(payload.get("job_id", "")).strip()
            if not job_id:
                QMessageBox.warning(
                    self,
                    self.ui("sync_blackboard_failed_title"),
                    self.ui("sync_blackboard_failed_body", details="missing_job_id"),
                )
                return

            self._bb_sync_job_id = job_id
            self._bb_sync_polling = False

            dialog = BlackboardSyncDialog(
                self.ui("sync_blackboard_progress_title"),
                self.ui("sync_blackboard_progress_cancel"),
                self,
            )
            self._bb_sync_dialog = dialog
            dialog.finished.connect(self._cleanup_bb_sync)

            def _cancel():
                dialog.set_cancellable(False)

                def _call_cancel():
                    return self.api_client.cancel_sync_blackboard_job(job_id)

                self._start_worker(_call_cancel, lambda _x: None, lambda _e: None)

            dialog.cancelled.connect(_cancel)
            dialog.set_status(
                self.ui(
                    "sync_blackboard_progress_body",
                    stage="fetching",
                    processed=0,
                    total="?",
                    added=0,
                    skipped_existing=0,
                    skipped_large=0,
                    skipped_unsup=0,
                    failed=0,
                    message="",
                )
            )
            dialog.show()

            timer = QTimer(self)
            timer.setInterval(800)
            timer.timeout.connect(
                lambda: self._poll_blackboard_sync_job(job_id, existing_names)
            )
            self._bb_sync_timer = timer
            timer.start()
            self._poll_blackboard_sync_job(job_id, existing_names)

        def _on_error(err):
            QMessageBox.warning(
                self,
                self.ui("sync_blackboard_failed_title"),
                self.ui("sync_blackboard_failed_body", details=err),
            )

        self._start_worker(_start_job, _on_job_started, _on_error)

    def _poll_blackboard_sync_job(self, job_id: str, existing_names: set[str]) -> None:
        if getattr(self, "_bb_sync_polling", False):
            return
        self._bb_sync_polling = True

        def _call():
            return self.api_client.get_sync_blackboard_job(job_id)

        def _on_done(payload):
            self._bb_sync_polling = False
            if not isinstance(payload, dict):
                return
            status = str(payload.get("status", "")).strip()
            stage = str(payload.get("stage", "")).strip() or status or "running"
            message = str(payload.get("message", "") or "")
            processed = int(payload.get("processed") or 0)
            total_raw = payload.get("total")
            total: int | None
            try:
                total = int(total_raw) if total_raw is not None else None
            except Exception:
                total = None

            dialog = getattr(self, "_bb_sync_dialog", None)
            if isinstance(dialog, BlackboardSyncDialog):
                added = int(payload.get("added") or 0)
                se = int(payload.get("skipped_existing") or 0)
                sl = int(payload.get("skipped_large") or 0)
                su = int(payload.get("skipped_unsupported") or 0)
                fc = int(payload.get("failed") or 0)
                dialog.set_status(
                    self.ui(
                        "sync_blackboard_progress_body",
                        stage=stage,
                        processed=processed,
                        total=total if total is not None else "?",
                        added=added,
                        skipped_existing=se,
                        skipped_large=sl,
                        skipped_unsup=su,
                        failed=fc,
                        message=message,
                    )
                )
                dialog.set_progress(processed, total)
                if status in {"done", "failed", "cancelled"}:
                    dialog.set_cancellable(False)

            if status not in {"done", "failed", "cancelled"}:
                return

            timer = getattr(self, "_bb_sync_timer", None)
            if isinstance(timer, QTimer):
                timer.stop()

            def _refresh():
                materials = self.api_client.list_materials()
                return materials

            def _on_refresh(materials):
                if not isinstance(materials, list):
                    materials = []
                new_items = [
                    item
                    for item in materials
                    if isinstance(item, dict)
                    and str(
                        item.get("file_name")
                        or item.get("name")
                        or item.get("file_id")
                        or ""
                    ).lower()
                    not in existing_names
                ]
                self.material_records = materials
                self.resource_files = [
                    str(
                        item.get("file_name")
                        or item.get("name")
                        or item.get("file_id")
                        or "resource"
                    )
                    for item in materials
                    if isinstance(item, dict)
                ]
                self._load_resource_files()

                self._bb_sync_job_id = None
                dialog = getattr(self, "_bb_sync_dialog", None)
                if isinstance(dialog, BlackboardSyncDialog):
                    dialog.close()

                added = int(payload.get("added") or 0)
                skipped_large = int(payload.get("skipped_large") or 0)
                total_raw = payload.get("total")
                try:
                    total_int = int(total_raw) if total_raw is not None else None
                except Exception:
                    total_int = None

                msg = str(message or "").strip()

                if status == "done":
                    msg_parts = msg.split(" | ") if msg else []
                    skipped_dl_names = ""
                    skipped_unsup_names = ""
                    failed_part_names = ""
                    for part in msg_parts:
                        part = part.strip()
                        if part.startswith("skipped_dl:"):
                            skipped_dl_names = part[len("skipped_dl:") :]
                        elif part.startswith("skipped_unsupported:"):
                            skipped_unsup_names = part[len("skipped_unsupported:") :]
                        elif part.startswith("failed:"):
                            failed_part_names = part[len("failed:") :]

                    all_skipped_text = []
                    if skipped_dl_names:
                        all_skipped_text.append(
                            self.ui("sync_bb_skipped_dl_label", names=skipped_dl_names)
                        )
                    if skipped_unsup_names:
                        all_skipped_text.append(
                            self.ui(
                                "sync_bb_skipped_unsup_label", names=skipped_unsup_names
                            )
                        )
                    if failed_part_names:
                        all_skipped_text.append(
                            self.ui("sync_bb_failed_label", names=failed_part_names)
                        )
                    skipped_block = "\n".join(all_skipped_text)

                    if added == 0 and all_skipped_text:
                        skipped_count = skipped_large
                        QMessageBox.warning(
                            self,
                            self.ui("sync_blackboard_all_skipped_title"),
                            self.ui(
                                "sync_blackboard_all_skipped_body",
                                skipped_count=skipped_count,
                                names=skipped_block,
                            ),
                        )
                    elif all_skipped_text:
                        QMessageBox.information(
                            self,
                            self.ui("sync_blackboard_done_title"),
                            self.ui(
                                "sync_blackboard_done_with_skipped_body",
                                count=added,
                                skipped_details=skipped_block,
                            ),
                        )
                    elif skipped_large > 0:
                        QMessageBox.information(
                            self,
                            self.ui("sync_blackboard_skipped_title"),
                            self.ui(
                                "sync_blackboard_skipped_body",
                                count=added,
                                skipped_count=skipped_large,
                                names=msg,
                            ),
                        )
                    else:
                        QMessageBox.information(
                            self,
                            self.ui("sync_blackboard_done_title"),
                            self.ui(
                                "sync_blackboard_done_body",
                                count=added,
                            ),
                        )
                elif status == "cancelled":
                    QMessageBox.information(
                        self,
                        self.ui("sync_blackboard_failed_title"),
                        self.ui("sync_blackboard_failed_body", details="cancelled"),
                    )
                else:
                    if total_int == 0 or str(message).strip() == "no_files_found":
                        QMessageBox.warning(
                            self,
                            self.ui("sync_blackboard_no_files_title"),
                            self.ui("sync_blackboard_no_files_body"),
                        )
                    else:
                        QMessageBox.warning(
                            self,
                            self.ui("sync_blackboard_failed_title"),
                            self.ui(
                                "sync_blackboard_failed_body",
                                details=message or "failed",
                            ),
                        )

            self._start_worker(_refresh, _on_refresh, lambda _err: None)

        def _on_error(_err):
            self._bb_sync_polling = False

        self._start_worker(_call, _on_done, _on_error)

    def _add_resource_files(self) -> None:
        selected_files, _selected_filter = QFileDialog.getOpenFileNames(
            self,
            self.ui("resource_dialog_title"),
            "",
            self.ui("resource_dialog_filter"),
        )
        if not selected_files:
            return

        existing_names = {
            self._resource_display_name(resource).lower()
            for resource in self.resource_files
        }
        files_to_upload: list[tuple[str, str]] = []  # (file_path, display_name)
        local_only: list[str] = []
        skipped_count = 0

        for file_path in selected_files:
            display_name = self._resource_display_name(file_path)
            if display_name.lower() in existing_names:
                skipped_count += 1
                continue
            if self.api_client.enabled and self.api_client.authenticated:
                files_to_upload.append((file_path, display_name))
            else:
                self.resource_files.insert(0, file_path)
                existing_names.add(display_name.lower())
                local_only.append(display_name)

        if local_only:
            self._load_resource_files()

        if not files_to_upload:
            if not local_only:
                QMessageBox.information(
                    self,
                    self.ui("resource_already_loaded_title"),
                    self.ui("resource_already_loaded_body"),
                )
            return

        _skipped_count = skipped_count

        def _upload_all():
            added: list[str] = []
            errors: list[str] = []
            for fp, dn in files_to_upload:
                try:
                    material = self.api_client.upload_material(fp)
                    added.append((dn, material))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{dn}: {exc}")
            # refresh list after uploads
            try:
                materials = self.api_client.list_materials()
            except Exception:  # noqa: BLE001
                materials = []
            return {"added": added, "errors": errors, "materials": materials}

        def _on_done(result):
            added = result["added"]
            errors = result["errors"]
            materials = result["materials"]
            for _dn, material in added:
                saved_name = str(material.get("file_name") or _dn)
                self.material_records.insert(0, material)
                self.resource_files.insert(0, saved_name)
            if materials:
                self.material_records = materials
                self.resource_files = [
                    str(
                        item.get("file_name")
                        or item.get("name")
                        or item.get("file_id")
                        or "resource"
                    )
                    for item in materials
                ]
            self._load_resource_files()
            added_names = [dn for dn, _ in added]
            all_added = local_only + added_names
            if all_added:
                preview = ", ".join(all_added[:2])
                if len(all_added) > 2:
                    preview = f"{preview}, +{len(all_added) - 2}"
                self._append_trace(
                    self.local({"en": "Observation", "zh": "观察"}),
                    self.ui("trace_loaded_materials_title"),
                    self.ui(
                        "trace_loaded_materials_detail",
                        count=len(all_added),
                        files=preview,
                    ),
                    "done",
                )
                QMessageBox.information(
                    self,
                    self.ui("resource_added_title"),
                    self.ui(
                        "resource_added_body",
                        count=len(all_added),
                        skipped=_skipped_count,
                    ),
                )
            if errors:
                QMessageBox.warning(
                    self,
                    self.ui("resource_upload_failed_title"),
                    self.ui(
                        "resource_upload_failed_body", details="\n".join(errors[:4])
                    ),
                )

        def _on_error(err):
            QMessageBox.warning(
                self,
                self.ui("resource_upload_failed_title"),
                self.ui("resource_upload_failed_body", details=err),
            )

        self._start_worker(_upload_all, _on_done, _on_error)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
