"""PyQt6 desktop God Xun-Frontend prototype for the Student Productivity Agent project."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any
from uuid import uuid4

from PyQt6.QtCore import QObject, QPoint, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
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
    from .mock_data import (
        APP_TITLE,
        AUTH_DEMO_ACCOUNTS,
        AUTH_FEATURES,
        CHAT_MESSAGES,
        CONFLICTS,
        ENCYCLOPEDIA_RESULTS,
        HITL_REQUEST,
        HOME_BANNER,
        HOME_CORE_FEATURES,
        HOME_SKILLS,
        PROFILE,
        RESOURCE_FILES,
        SCHEDULE_EVENTS,
        TRACE_EVENTS,
    )
    from .styles import APP_STYLE
except ImportError:
    from api_client import BackendApiClient, BackendApiError  # type: ignore
    from i18n import UI_TEXTS  # type: ignore
    from mock_data import (  # type: ignore
        APP_TITLE,
        AUTH_DEMO_ACCOUNTS,
        AUTH_FEATURES,
        CHAT_MESSAGES,
        CONFLICTS,
        ENCYCLOPEDIA_RESULTS,
        HITL_REQUEST,
        HOME_BANNER,
        HOME_CORE_FEATURES,
        HOME_SKILLS,
        PROFILE,
        RESOURCE_FILES,
        SCHEDULE_EVENTS,
        TRACE_EVENTS,
    )
    from styles import APP_STYLE  # type: ignore


class ApiWorker(QThread):
    """Run a single blocking API call on a background thread and emit the result."""

    finished = pyqtSignal(object)   # emits the return value (any type)
    errored = pyqtSignal(str)       # emits the error message string

    def __init__(self, fn, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            result = self._fn()
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.errored.emit(str(exc))


def localized(value, language: str):
    """Resolve bilingual values into a concrete string/list for the current language."""
    if isinstance(value, dict) and "en" in value and "zh" in value:
        return value[language]
    return value


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


class BubbleWidget(QWidget):
    def __init__(self, sender: str, sender_label: str, text: str, message_type_label: str) -> None:
        super().__init__()
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 10)

        bubble = QFrame()
        bubble.setObjectName("UserBubble" if sender == "user" else "AgentBubble")
        bubble.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(14, 12, 14, 12)
        bubble_layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        sender_title = QLabel(sender_label)
        sender_title.setObjectName("CardTitle")
        type_chip = QLabel(message_type_label)
        type_chip.setObjectName("MessageTypeChip")
        text_label = QLabel(text)
        text_label.setObjectName("BodyText")
        text_label.setWordWrap(True)
        text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        header_row.addWidget(sender_title)
        header_row.addWidget(type_chip)
        header_row.addStretch(1)
        bubble_layout.addLayout(header_row)
        bubble_layout.addWidget(text_label)

        if sender == "user":
            outer.addStretch(1)
            outer.addWidget(bubble, 0)
        else:
            outer.addWidget(bubble, 0)
            outer.addStretch(1)


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

        outer.addWidget(card, 0)
        outer.addStretch(1)


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

        outer.addWidget(card, 0)
        outer.addStretch(1)


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
    def __init__(self, parent: QWidget | None, texts: dict[str, str], request_payload: dict[str, str | list[str]]) -> None:
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
    ) -> None:
        super().__init__(parent)
        self.texts = texts
        self.intent: str | None = None

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

        close_row = QHBoxLayout()
        close_button = QPushButton(texts["settings_close"])
        close_button.clicked.connect(self.reject)
        close_row.addStretch(1)
        close_row.addWidget(close_button)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(cas_card)
        layout.addWidget(api_card)
        layout.addLayout(close_row)

    def _accept_cas(self) -> None:
        self.intent = "cas"
        self.accept()

    def _accept_api(self) -> None:
        self.intent = "api"
        self.accept()

    def payload(self) -> dict[str, str]:
        return {
            "cas_username": self.cas_account_input.text().strip(),
            "cas_password": self.cas_password_input.text(),
            "api_key": self.api_key_input.text().strip(),
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
        self.registered_users = {
            account["username"]: {
                "password": account["password"],
                "display_name": account.get("display_name", account["username"]),
                "major": account["major"],
            }
            for account in AUTH_DEMO_ACCOUNTS
        }
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
        self.material_records: list[dict[str, Any]] = []
        self.selected_mode = "agent_chat"
        self.mode_button: QPushButton | None = None
        self.mode_menu: QMenu | None = None
        self.mode_actions: dict[str, Any] = {}
        self.resource_files = list(RESOURCE_FILES)
        self.conversations: list[dict[str, Any]] = []
        self.active_conversation_id: str | None = None
        self.session_id = self._new_session_id()
        self.chat_messages: list[dict[str, Any]] = []
        self.trace_events: list[dict[str, str]] = []
        self.schedule_events: list[dict[str, str]] = []
        self.conflicts: list[dict[str, str]] = []
        self.response_stream_state: dict[str, Any] | None = None
        self.response_stream_timer = QTimer(self)
        self.response_stream_timer.setInterval(45)
        self.response_stream_timer.timeout.connect(self._advance_response_stream)
        self._active_workers: list[ApiWorker] = []

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
        return self.ui("backend_mode_mock")

    def _new_session_id(self) -> str:
        return f"sess_{uuid4().hex[:12]}"

    def current_user_id(self) -> str:
        return self.current_user_id_value or self.current_username or "local_student"

    def _message_placeholder_for_mode(self) -> str:
        return {
            "agent_chat": self.ui("message_placeholder_chat"),
            "scheduler": self.ui("message_placeholder_schedule"),
            "encyclopedia": self.ui("message_placeholder_encyclopedia"),
        }.get(self.selected_mode, self.ui("message_placeholder_chat"))

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
        position = self.mode_button.mapToGlobal(QPoint(0, self.mode_button.height() + 6))
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

    def _finalize_response_stream(self, *, open_dialog: bool) -> None:
        state = self.response_stream_state or {}
        self.response_stream_timer.stop()
        self.response_stream_state = None
        self.pending_hitl_request = state.get("pending_hitl_request")
        self._sync_active_conversation()
        if open_dialog and self.pending_hitl_request and state.get("auto_open_hitl", True):
            self.open_hitl_dialog()

    def _flush_response_stream(self, *, open_dialog: bool) -> None:
        if not self.response_stream_state:
            return

        state = self.response_stream_state
        assistant_index = state.get("assistant_index")
        assistant_text = str(state.get("assistant_text", ""))
        if assistant_index is not None and 0 <= assistant_index < len(self.chat_messages):
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
            next_cursor = min(len(assistant_text), cursor + self._response_chunk_size(assistant_text, cursor))
            state["assistant_cursor"] = next_cursor
            if 0 <= assistant_index < len(self.chat_messages):
                self.chat_messages[assistant_index]["text"] = assistant_text[:next_cursor]
                chat_changed = True

        extra_messages = list(state.get("extra_messages", []))
        extra_index = int(state.get("extra_index", 0))
        assistant_done = assistant_index is None or int(state.get("assistant_cursor", 0)) >= len(assistant_text)
        trace_done = int(state.get("trace_index", 0)) >= len(trace_queue)
        if assistant_done and trace_done and extra_index < len(extra_messages):
            self.chat_messages.append(extra_messages[extra_index])
            state["extra_index"] = extra_index + 1
            chat_changed = True

        if chat_changed:
            self._load_chat_messages(self.chat_messages)
        if trace_changed:
            self._load_trace_events(self.trace_events)

        trace_done = int(state.get("trace_index", 0)) >= len(trace_queue)
        assistant_done = assistant_index is None or int(state.get("assistant_cursor", 0)) >= len(assistant_text)
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
            initial_cursor = min(len(assistant_text), self._response_chunk_size(assistant_text, 0))
            self.chat_messages.append(self._create_text_message("agent", assistant_text[:initial_cursor]))
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

    def _build_localized_chat_messages(self) -> list[dict[str, Any]]:
        return [
            {
                "kind": "text",
                "sender": item["sender"],
                "text": self.local(item["text"]),
            }
            for item in CHAT_MESSAGES
        ]

    def _build_new_chat_messages(self) -> list[dict[str, Any]]:
        for item in CHAT_MESSAGES:
            if item["sender"] == "agent":
                return [{"kind": "text", "sender": "agent", "text": self.local(item["text"])}]
        return []

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

    def _generate_mock_response(self, prompt: str) -> dict[str, Any]:
        lowered = prompt.lower()
        route = "chat"
        assistant_text = self.ui("reply_generic")
        trace: list[dict[str, Any]] = [
            {
                "phase": self.local({"en": "Reasoning", "zh": "推理"}),
                "title": self.ui("trace_responded_main_chat_title"),
                "detail": self.ui(
                    "trace_responded_main_chat_detail",
                    prompt=prompt[:72] + ("..." if len(prompt) > 72 else ""),
                ),
                "status": "done",
            }
        ]
        ui_payload: dict[str, Any] = {"schedule": None, "encyclopedia": None}
        hitl_request: dict[str, Any] | None = None

        if any(keyword in lowered for keyword in ("delete", "overwrite", "modify", "删除", "覆盖", "修改")):
            route = "os_automation"
            assistant_text = self.ui("reply_hitl")
            trace = [
                {
                    "phase": self.local({"en": "Tool Use", "zh": "工具调用"}),
                    "title": self.ui("trace_hitl_update_title"),
                    "detail": self.ui("trace_hitl_pending"),
                    "status": "pending",
                }
            ]
            hitl_request = self._build_localized_hitl_request()
            hitl_request["request_id"] = f"hitl_mock_{uuid4().hex[:10]}"
        elif self.selected_mode == "scheduler":
            route = "scheduler"
            assistant_text = self.ui("reply_schedule")
            ui_payload["schedule"] = {
                "events": [dict(item) for item in self.schedule_events],
                "conflicts": [dict(item) for item in self.conflicts],
            }
        elif self.selected_mode == "encyclopedia":
            route = "encyclopedia"
            if "dorm" in lowered or "宿舍" in lowered:
                key = "dorm"
            elif "credit" in lowered or "学分" in lowered:
                key = "credit"
            else:
                key = "default"
            payload = ENCYCLOPEDIA_RESULTS.get(key, ENCYCLOPEDIA_RESULTS["default"])
            assistant_text = self.ui("reply_encyclopedia")
            ui_payload["encyclopedia"] = {
                "query": self.local(payload["query"]),
                "answer_markdown": self.local(payload["answer"]),
                "citations": self.local(payload["citations"]),
            }
            trace.append(
                {
                    "phase": self.local({"en": "Observation", "zh": "观察"}),
                    "title": self.ui("trace_rendered_encyclopedia_title"),
                    "detail": self.ui("trace_rendered_encyclopedia_detail", query=self.local(payload["query"])),
                    "status": "done",
                }
            )

        return {
            "session_id": self.session_id,
            "assistant_message": {"role": "assistant", "content": assistant_text},
            "trace": trace,
            "route": route,
            "ui_payload": ui_payload,
            "hitl_request": hitl_request,
            "error": None,
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
                self.schedule_events = normalized_events
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

        encyclopedia_payload = ui_payload.get("encyclopedia")
        if isinstance(encyclopedia_payload, dict):
            answer_markdown = str(encyclopedia_payload.get("answer_markdown", "")).strip()
            citations = encyclopedia_payload.get("citations", [])
            cards.append(
                self._create_encyclopedia_message(
                    intro=self.ui("encyclopedia_card_intro"),
                    query=str(encyclopedia_payload.get("query", "")).strip(),
                    answer_markdown=answer_markdown or self.local(ENCYCLOPEDIA_RESULTS["default"]["answer"]),
                    citations=[str(item) for item in citations] if isinstance(citations, list) else [],
                )
            )

        return cards

    def _create_conversation(
        self,
        *,
        session_id: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        trace: list[dict[str, str]] | None = None,
        pending_hitl_request: dict[str, Any] | None = None,
        title: str | None = None,
        remote_updated_at: str | None = None,
    ) -> dict[str, Any]:
        return {
            "session_id": session_id or self._new_session_id(),
            "messages": list(messages or self._build_new_chat_messages()),
            "trace": list(trace or []),
            "pending_hitl_request": pending_hitl_request,
            "title": title,
            "remote_updated_at": remote_updated_at,
        }

    def _derive_conversation_title(self, conversation: dict[str, Any]) -> str:
        title = str(conversation.get("title", "")).strip()
        if title:
            return title[:32] + ("..." if len(title) > 32 else "")
        for item in conversation["messages"]:
            if item.get("sender") == "user" and str(item.get("text", "")).strip():
                title = str(item.get("text", "")).strip().replace("\n", " ")
                return title[:32] + ("..." if len(title) > 32 else "")
        return self.ui("new_chat")

    def _conversation_meta(self, conversation: dict[str, Any]) -> str:
        updated_at = str(conversation.get("remote_updated_at", "")).strip()
        if updated_at:
            return self.ui("conversation_meta_remote", updated=self._format_remote_timestamp(updated_at))
        return self.ui(
            "conversation_meta",
            messages=len(conversation["messages"]),
            trace=len(conversation["trace"]),
        )

    def _format_remote_timestamp(self, value: str) -> str:
        if "T" in value:
            value = value.replace("T", " ")
        if "+" in value:
            value = value.split("+", 1)[0]
        return value[:16] if len(value) > 16 else value

    def _resource_display_name(self, resource_name: str) -> str:
        return Path(resource_name).name or resource_name

    def _resource_meta(self, resource_name: str) -> str:
        display_name = self._resource_display_name(resource_name)
        suffix = display_name.rsplit(".", 1)[-1].upper() if "." in display_name else "FILE"
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

    def _move_active_conversation_to_top(self) -> None:
        conversation = self._active_conversation()
        if conversation is None:
            return
        self.conversations = [conversation] + [
            item for item in self.conversations if item["session_id"] != conversation["session_id"]
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
            break

    def _initialize_default_conversations(self) -> None:
        conversation = self._create_conversation(
            session_id=self.session_id,
            messages=self._build_localized_chat_messages(),
            trace=self._build_localized_trace_events(),
        )
        self.conversations = [conversation]
        self.active_conversation_id = conversation["session_id"]
        self.chat_messages = list(conversation["messages"])
        self.trace_events = list(conversation["trace"])
        self.pending_hitl_request = None

    def _build_localized_trace_events(self) -> list[dict[str, str]]:
        return [
            {
                "phase": self.local(item["phase"]),
                "title": self.local(item["title"]),
                "detail": self.local(item["detail"]),
                "status": item["status"],
            }
            for item in TRACE_EVENTS
        ]

    def _build_localized_schedule_events(self) -> list[dict[str, str]]:
        return [
            {
                "title": self.local(item["title"]),
                "time": self.local(item["time"]),
                "source": self.local(item["source"]),
                "detail": self.local(item["detail"]),
            }
            for item in SCHEDULE_EVENTS
        ]

    def _build_localized_conflicts(self) -> list[dict[str, str]]:
        return [
            {
                "title": self.local(item["title"]),
                "detail": self.local(item["detail"]),
            }
            for item in CONFLICTS
        ]

    def _build_localized_hitl_request(self) -> dict[str, str | list[str]]:
        return {
            "action": self.local(HITL_REQUEST["action"]),
            "risk": self.local(HITL_REQUEST["risk"]),
            "reason": self.local(HITL_REQUEST["reason"]),
            "payload": self.local(HITL_REQUEST["payload"]),
        }

    def _normalize_backend_trace_events(self, events: list[dict[str, Any]]) -> list[dict[str, str]]:
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

    def _normalize_schedule_events(self, events: list[dict[str, Any]]) -> list[dict[str, str]]:
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

    def _normalize_conflicts(self, conflicts: list[dict[str, Any]]) -> list[dict[str, str]]:
        normalized = []
        for item in conflicts:
            normalized.append(
                {
                    "title": str(item.get("title", "")),
                    "detail": str(item.get("detail", "")),
                }
            )
        return normalized

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
            existing = {conversation["session_id"]: conversation for conversation in self.conversations}
            merged: list[dict[str, Any]] = []
            seen: set[str] = set()
            for item in summaries:
                session_id = str(item.get("session_id", "")).strip()
                if not session_id:
                    continue
                preview = str(item.get("preview", "")).strip()
                updated_at = str(item.get("updated_at", "")).strip()
                conversation = existing.get(session_id)
                if conversation is None:
                    placeholder_messages = (
                        [self._create_text_message("agent", preview)]
                        if preview
                        else self._build_new_chat_messages()
                    )
                    conversation = self._create_conversation(
                        session_id=session_id,
                        messages=placeholder_messages,
                        trace=[],
                        title=preview,
                        remote_updated_at=updated_at,
                    )
                else:
                    conversation["title"] = preview or conversation.get("title")
                    conversation["remote_updated_at"] = updated_at
                merged.append(conversation)
                seen.add(session_id)
            active = self._active_conversation()
            if active and active["session_id"] not in seen:
                merged.insert(0, active)
            if merged:
                self.conversations = merged
                if active and active["session_id"] in {item["session_id"] for item in merged}:
                    self.active_conversation_id = active["session_id"]
                else:
                    self.active_conversation_id = merged[0]["session_id"]
                self._refresh_conversation_list()

        self._start_worker(self.api_client.list_sessions, _on_done)

    def _build_root(self) -> None:
        self.setWindowTitle(self.app_title())
        self.resize(1560, 940)

        root = QWidget()
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
        self._refresh_profile_views()

    def _reset_dynamic_state(self) -> None:
        self._initialize_default_conversations()
        self.schedule_events = self._build_localized_schedule_events()
        self.conflicts = self._build_localized_conflicts()

        if self.remote_profile:
            self.current_user = {
                "name": str(self.remote_profile.get("name", self.current_username or self.local(PROFILE["name"]))),
                "major": str(self.remote_profile.get("major", self.local(PROFILE["major"]))),
                "focus": self.ui("authenticated_focus"),
            }
            return

        if self.current_username:
            record = self.registered_users.get(self.current_username)
            major = self.local(record["major"]) if record else self.local(PROFILE["major"])
            self.current_user = {
                "name": str(self.local(record["display_name"])) if record and "display_name" in record else self.current_username,
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
            item = QListWidgetItem(f"{display_name}\n{self._resource_meta(resource)}", self.resource_list)
            item.setToolTip(resource)
            item.setSizeHint(QSize(0, 58))
        self._refresh_profile_views()

    def _refresh_conversation_list(self) -> None:
        if not hasattr(self, "history_list"):
            return

        self._sync_active_conversation()
        self.history_list.blockSignals(True)
        self.history_list.clear()
        if not self.conversations:
            QListWidgetItem(self.ui("empty_history"), self.history_list)
            self.history_list.blockSignals(False)
            return

        selected_row = 0
        for index, conversation in enumerate(self.conversations):
            title = self._derive_conversation_title(conversation)
            item = QListWidgetItem(f"{title}\n{self._conversation_meta(conversation)}", self.history_list)
            item.setData(Qt.ItemDataRole.UserRole, conversation["session_id"])
            item.setToolTip(title)
            item.setSizeHint(QSize(0, 62))
            if conversation["session_id"] == self.active_conversation_id:
                selected_row = index

        self.history_list.setCurrentRow(selected_row)
        self.history_list.blockSignals(False)
        self._refresh_profile_views()

    def handle_history_selection(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return

        self._flush_response_stream(open_dialog=False)
        session_id = current.data(Qt.ItemDataRole.UserRole)
        if not session_id or session_id == self.active_conversation_id:
            return
        self._activate_conversation(str(session_id))

    def toggle_language(self) -> None:
        self._flush_response_stream(open_dialog=False)
        current_page = self.stack.currentWidget().objectName() if hasattr(self, "stack") else "HomePage"
        auth_tab_index = self.auth_tabs.currentIndex() if hasattr(self, "auth_tabs") else 0
        login_username = self.login_username_input.text() if hasattr(self, "login_username_input") else ""
        register_username = self.register_username_input.text() if hasattr(self, "register_username_input") else ""
        register_display_name = (
            self.register_display_name_input.text() if hasattr(self, "register_display_name_input") else ""
        )
        register_major = self.register_major_input.text() if hasattr(self, "register_major_input") else ""

        self.language = "zh" if self.language == "en" else "en"
        self._reset_dynamic_state()
        self._build_root()

        self.login_username_input.setText(login_username)
        self.register_username_input.setText(register_username)
        self.register_display_name_input.setText(register_display_name)
        self.register_major_input.setText(register_major)

        if current_page == "DashboardPage":
            self.stack.setCurrentWidget(self.dashboard_page)
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
        content_layout.setContentsMargins(8, 8, 8, 24)
        content_layout.setSpacing(24)

        hero = QFrame()
        hero.setObjectName("HomeHeroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 30, 28, 30)
        hero_layout.setSpacing(14)

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
        feature_grid.setHorizontalSpacing(14)
        feature_grid.setVerticalSpacing(14)
        for index, item in enumerate(HOME_CORE_FEATURES):
            card = QFrame()
            card.setObjectName("HomeFeatureCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 18, 18, 18)
            card_layout.setSpacing(8)
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
        skills_grid.setHorizontalSpacing(14)
        skills_grid.setVerticalSpacing(14)
        for index, item in enumerate(HOME_SKILLS):
            card = QFrame()
            card.setObjectName("HomeSkillCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 18, 18, 18)
            card_layout.setSpacing(8)
            icon = QLabel(item["icon"])
            icon.setObjectName("SkillIcon")
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
        banner_layout.setContentsMargins(24, 24, 24, 24)
        banner_layout.setSpacing(10)
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

        for item in AUTH_FEATURES:
            pill = QFrame()
            pill.setObjectName("FeaturePill")
            pill_layout = QVBoxLayout(pill)
            pill_layout.setContentsMargins(16, 14, 16, 14)
            pill_layout.setSpacing(6)
            pill_title = QLabel(self.local(item["title"]))
            pill_title.setObjectName("SectionTitle")
            pill_detail = QLabel(self.local(item["detail"]))
            pill_detail.setObjectName("MutedText")
            pill_detail.setWordWrap(True)
            pill_layout.addWidget(pill_title)
            pill_layout.addWidget(pill_detail)
            hero_layout.addWidget(pill)

        hero_layout.addStretch(1)
        demo_hint = QLabel(
            f"{self.ui('demo_account')}: {AUTH_DEMO_ACCOUNTS[0]['username']} / {AUTH_DEMO_ACCOUNTS[0]['password']}"
        )
        demo_hint.setObjectName("HintText")
        hero_layout.addWidget(demo_hint)

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

        footer = QLabel(self.ui("auth_footer"))
        footer.setObjectName("AuthFooter")
        footer.setWordWrap(True)

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
        auth_layout.addWidget(footer)
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

        helper = QLabel(
            self.ui(
                "login_helper",
                username=AUTH_DEMO_ACCOUNTS[0]["username"],
                password=AUTH_DEMO_ACCOUNTS[0]["password"],
            )
        )
        helper.setObjectName("HintText")
        helper.setWordWrap(True)

        layout.addWidget(self.login_username_input)
        layout.addWidget(self.login_password_input)
        layout.addWidget(password_button)
        layout.addWidget(helper)
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

        helper = QLabel(self.ui("register_helper"))
        helper.setObjectName("HintText")
        helper.setWordWrap(True)

        layout.addWidget(self.register_username_input)
        layout.addWidget(self.register_display_name_input)
        layout.addWidget(self.register_major_input)
        layout.addWidget(self.register_password_input)
        layout.addWidget(self.register_confirm_input)
        layout.addWidget(register_button)
        layout.addWidget(helper)
        return tab

    def _build_dashboard_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("DashboardPage")
        root_layout = QVBoxLayout(page)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(16)

        root_layout.addLayout(self._build_header())

        body_layout = QHBoxLayout()
        body_layout.setSpacing(16)

        sidebar = self._build_sidebar()
        center = self._build_center_panel()
        trace = self._build_trace_panel()

        body_layout.addWidget(sidebar, 24)
        body_layout.addWidget(center, 52)
        body_layout.addWidget(trace, 24)
        root_layout.addLayout(body_layout)
        return page

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(12)

        title_group = QVBoxLayout()
        title_group.setSpacing(4)
        title = QLabel(self.app_title())
        title.setObjectName("TitleLabel")
        subtitle = QLabel(self.ui("header_subtitle"))
        subtitle.setObjectName("SubtitleLabel")
        subtitle.setWordWrap(True)
        title_group.addWidget(title)
        title_group.addWidget(subtitle)

        self.header_user_label = QLabel()
        self.header_user_label.setObjectName("BadgeLabel")
        self.backend_mode_label = QLabel()
        self.backend_mode_label.setObjectName("BadgeLabel")

        lang_button = QPushButton(self.ui("lang_button"))
        lang_button.clicked.connect(self.toggle_language)
        settings_button = QPushButton(self.ui("settings_button"))
        settings_button.clicked.connect(self.open_settings_dialog)
        refresh_button = QPushButton(self.ui("refresh_mock"))
        refresh_button.clicked.connect(self.refresh_mock_content)
        refresh_schedule_button = QPushButton(self.ui("refresh_schedule"))
        refresh_schedule_button.clicked.connect(self.refresh_schedule_data)
        simulate_button = QPushButton(self.ui("simulate_hitl"))
        simulate_button.setObjectName("PrimaryButton")
        simulate_button.clicked.connect(self.open_hitl_dialog)
        logout_button = QPushButton(self.ui("log_out"))
        logout_button.clicked.connect(self.logout)

        layout.addLayout(title_group, 1)
        layout.addWidget(self.backend_mode_label)
        layout.addWidget(self.header_user_label)
        layout.addWidget(lang_button)
        layout.addWidget(settings_button)
        layout.addWidget(refresh_button)
        layout.addWidget(refresh_schedule_button)
        layout.addWidget(simulate_button)
        layout.addWidget(logout_button)
        return layout

    def _build_sidebar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("SidebarFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)

        workspace_card = QFrame()
        workspace_card.setObjectName("WorkspaceCard")
        workspace_layout = QVBoxLayout(workspace_card)
        workspace_layout.setContentsMargins(18, 18, 18, 18)
        workspace_layout.setSpacing(8)

        workspace_title = QLabel(self.ui("workspace_title"))
        workspace_title.setObjectName("CardTitle")
        self.workspace_name_label = QLabel()
        self.workspace_name_label.setObjectName("WorkspaceName")
        self.workspace_hint_label = QLabel()
        self.workspace_hint_label.setObjectName("BodyText")
        self.workspace_hint_label.setWordWrap(True)

        workspace_stats = QHBoxLayout()
        workspace_stats.setSpacing(8)
        self.workspace_conversation_chip = QLabel()
        self.workspace_conversation_chip.setObjectName("WorkspaceStat")
        self.workspace_material_chip = QLabel()
        self.workspace_material_chip.setObjectName("WorkspaceStat")
        self.workspace_trace_chip = QLabel()
        self.workspace_trace_chip.setObjectName("WorkspaceStat")
        workspace_stats.addWidget(self.workspace_conversation_chip)
        workspace_stats.addWidget(self.workspace_material_chip)
        workspace_stats.addWidget(self.workspace_trace_chip)
        workspace_stats.addStretch(1)

        workspace_layout.addWidget(workspace_title)
        workspace_layout.addWidget(self.workspace_name_label)
        workspace_layout.addWidget(self.workspace_hint_label)
        workspace_layout.addLayout(workspace_stats)

        history_card = QFrame()
        history_card.setObjectName("PanelCard")
        history_layout = QVBoxLayout(history_card)
        history_layout.setContentsMargins(18, 18, 18, 18)
        history_layout.setSpacing(10)

        history_header = QHBoxLayout()
        history_header.setSpacing(10)
        history_title = QLabel(self.ui("conversation_history"))
        history_title.setObjectName("SectionTitle")
        new_chat_button = QPushButton(self.ui("new_chat"))
        new_chat_button.setObjectName("PrimaryButton")
        new_chat_button.clicked.connect(self.start_new_chat)
        delete_chat_button = QPushButton(self.ui("delete_chat"))
        delete_chat_button.clicked.connect(self.delete_current_chat)
        history_hint = QLabel(self.ui("conversation_history_hint"))
        history_hint.setObjectName("MutedText")
        history_hint.setWordWrap(True)
        self.history_list = QListWidget()
        self.history_list.setObjectName("ConversationList")
        self.history_list.currentItemChanged.connect(self.handle_history_selection)

        history_header.addWidget(history_title)
        history_header.addStretch(1)
        history_header.addWidget(delete_chat_button)
        history_header.addWidget(new_chat_button)
        history_layout.addLayout(history_header)
        history_layout.addWidget(history_hint)
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
        add_button.clicked.connect(self._add_resource_files)

        resources_layout.addWidget(resources_title)
        resources_layout.addWidget(resources_hint)
        resources_layout.addWidget(self.resource_list)
        resources_layout.addWidget(add_button)

        layout.addWidget(workspace_card)
        layout.addWidget(history_card, 1)
        layout.addWidget(resources_card, 1)
        self._refresh_conversation_list()
        return frame

    def _build_center_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("CenterFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)

        layout.addWidget(self._build_chat_tab(), 1)
        return frame

    def _build_chat_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        chat_card = QFrame()
        chat_card.setObjectName("PanelCard")
        chat_layout = QVBoxLayout(chat_card)
        chat_layout.setContentsMargins(16, 16, 16, 16)
        chat_layout.setSpacing(10)

        chat_title = QLabel(self.ui("tab_agent_chat"))
        chat_title.setObjectName("SectionTitle")

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(4, 4, 4, 4)
        self.chat_layout.setSpacing(0)
        self.chat_layout.addStretch(1)
        scroll_area.setWidget(self.chat_container)

        chat_layout.addWidget(chat_title)
        chat_layout.addWidget(scroll_area, 1)
        layout.addWidget(chat_card, 1)

        composer_card = QFrame()
        composer_card.setObjectName("PanelCard")
        composer_layout = QVBoxLayout(composer_card)
        composer_layout.setContentsMargins(16, 16, 16, 16)
        composer_layout.setSpacing(10)

        composer_title = QLabel(self.ui("send_task"))
        composer_title.setObjectName("SectionTitle")
        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText(self._message_placeholder_for_mode())
        self.message_input.setFixedHeight(110)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self.mode_button = QPushButton()
        self.mode_button.setObjectName("ModeDropdownButton")
        self.mode_button.clicked.connect(self._open_mode_menu)
        self.mode_menu = QMenu(self)
        self.mode_menu.setObjectName("ModeDropdownMenu")
        self.mode_actions = {}
        for mode, label_key in (
            ("agent_chat", "mode_agent_chat"),
            ("scheduler", "mode_scheduler"),
            ("encyclopedia", "mode_encyclopedia"),
        ):
            action = self.mode_menu.addAction(self.ui(label_key))
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, value=mode: self._set_selected_mode(value))
            self.mode_actions[mode] = action

        send_button = QPushButton(self.ui("send"))
        send_button.setObjectName("PrimaryButton")
        send_button.clicked.connect(self.handle_send_message)
        clear_button = QPushButton(self.ui("clear_draft"))
        clear_button.clicked.connect(self.message_input.clear)
        button_row.addWidget(self.mode_button)
        button_row.addStretch(1)
        button_row.addWidget(clear_button)
        button_row.addWidget(send_button)
        self._refresh_mode_selector()

        composer_layout.addWidget(composer_title)
        composer_layout.addWidget(self.message_input)
        composer_layout.addLayout(button_row)

        layout.addWidget(composer_card)
        return tab

    def _build_trace_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("TraceFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel(self.ui("thought_trace"))
        title.setObjectName("TitleLabel")
        title.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        subtitle = QLabel(self.ui("thought_trace_subtitle"))
        subtitle.setObjectName("SubtitleLabel")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.trace_container = QWidget()
        self.trace_layout = QVBoxLayout(self.trace_container)
        self.trace_layout.setContentsMargins(0, 0, 0, 0)
        self.trace_layout.setSpacing(10)
        self.trace_layout.addStretch(1)
        scroll_area.setWidget(self.trace_container)

        approval_hint = InfoCard(self.ui("pending_hitl_title"), self.ui("pending_hitl_body"))
        open_dialog_button = QPushButton(self.ui("open_authorization_dialog"))
        open_dialog_button.setObjectName("PrimaryButton")
        open_dialog_button.clicked.connect(self.open_hitl_dialog)

        layout.addWidget(scroll_area, 1)
        layout.addWidget(approval_hint)
        layout.addWidget(open_dialog_button)
        return frame

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
                    list(payload.get("events", [])) if isinstance(payload, dict) else [],
                    list(payload.get("conflicts", [])) if isinstance(payload, dict) else [],
                    UI_TEXTS[self.language],
                )
            elif kind == "encyclopedia":
                payload = message.get("payload", {})
                widget = EncyclopediaResultWidget(
                    self._sender_label(sender),
                    self.ui("chat_encyclopedia_card_title"),
                    str(message.get("text", "")),
                    str(payload.get("query", "")) if isinstance(payload, dict) else "",
                    str(payload.get("answer_markdown", "")) if isinstance(payload, dict) else "",
                    [str(item) for item in payload.get("citations", [])] if isinstance(payload, dict) else [],
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
        self._refresh_conversation_list()

    def _load_trace_events(self, events: list[dict[str, str]]) -> None:
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
        self._sync_active_conversation()

    def _refresh_profile_views(self) -> None:
        self.header_user_label.setText(self.ui("signed_in_as", name=self.current_user["name"]))
        self.backend_mode_label.setText(self.backend_status_text())
        if hasattr(self, "workspace_name_label"):
            self.workspace_name_label.setText(self.current_user["name"])
        if hasattr(self, "workspace_hint_label"):
            self.workspace_hint_label.setText(self.ui("workspace_hint"))
        if hasattr(self, "workspace_conversation_chip"):
            self.workspace_conversation_chip.setText(
                self.ui("workspace_conversations", count=len(self.conversations))
            )
        if hasattr(self, "workspace_material_chip"):
            self.workspace_material_chip.setText(
                self.ui("workspace_materials", count=len(self.resource_files))
            )
        if hasattr(self, "workspace_trace_chip"):
            self.workspace_trace_chip.setText(
                self.ui("workspace_trace", count=len(self.trace_events))
            )

    def open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self, UI_TEXTS[self.language], self.cas_settings, self.api_settings)
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
        if not (self.api_client.enabled and self.api_client.authenticated and self.current_username):
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
        display_name = str(user_profile.get("display_name") or self.current_username or self.local(PROFILE["name"]))
        major = str(user_profile.get("major") or self.local(PROFILE["major"]))
        self.current_user_id_value = str(user_profile.get("user_id") or self.current_user_id())
        self.remote_profile = {
            "name": display_name,
            "major": major,
        }
        self.current_user = {
            "name": display_name,
            "major": major,
            "focus": self.ui("authenticated_focus"),
        }

        chat_history = payload.get("chat_history", [])
        if isinstance(chat_history, list):
            self.chat_messages = [
                {
                    "kind": "text",
                    "sender": "user" if str(item.get("role", "")).lower() == "user" else "agent",
                    "text": str(item.get("content", "")),
                }
                for item in chat_history
            ]
            self.trace_events = []
            self.pending_hitl_request = None
            self._sync_active_conversation()
            self._load_chat_messages(self.chat_messages)
            self._load_trace_events(self.trace_events)

        materials = payload.get("materials", [])
        if isinstance(materials, list):
            self.material_records = [item for item in materials if isinstance(item, dict)]
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
                self.schedule_events = self._normalize_schedule_events(events)
            if isinstance(conflicts, list):
                self.conflicts = self._normalize_conflicts(conflicts)

        self._sync_remote_sessions()
        self._refresh_profile_views()

    def _apply_agent_response(self, response: dict[str, Any], auto_open_hitl: bool = True) -> None:
        assistant_message = response.get("assistant_message", {})
        assistant_text = str(assistant_message.get("content", "")).strip()
        trace_items: list[dict[str, str]] = []
        trace = response.get("trace", [])
        if isinstance(trace, list) and trace:
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
        pending_hitl_request = self._normalize_hitl_request(hitl_request) if isinstance(hitl_request, dict) else None
        extra_messages = self._build_response_cards(response)
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
        worker.finished.connect(lambda _: self._active_workers.remove(worker) if worker in self._active_workers else None)
        worker.errored.connect(lambda _: self._active_workers.remove(worker) if worker in self._active_workers else None)
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
        if not (self.api_client.enabled and self.api_client.authenticated and self.current_username):
            return False

        user_id = self.current_user_id()
        session_id = self.session_id
        _attachments = attachments or []
        _auto_open_hitl = auto_open_hitl

        def _call():
            return self.api_client.run_agent(
                user_id=user_id,
                session_id=session_id,
                message=message,
                attachments=_attachments,
                hitl_reply=hitl_reply,
            )

        def _on_done(response):
            self._apply_agent_response(response, auto_open_hitl=_auto_open_hitl)

        def _on_error(err):
            self._append_trace(
                self.local({"en": "Observation", "zh": "观察"}),
                self.ui("trace_backend_unavailable_title"),
                self.ui("trace_backend_unavailable_detail", error=err),
                "pending",
            )

        self._start_worker(_call, _on_done, _on_error)
        return True

    def handle_password_login(self) -> None:
        username = self.login_username_input.text().strip()
        password = self.login_password_input.text()
        if not username or not password:
            QMessageBox.warning(self, self.ui("login_failed"), self.ui("enter_both_username_password"))
            return

        if self.api_client.enabled:
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
                QMessageBox.warning(self, self.ui("login_failed"), err)

            self._start_worker(_call, _on_done, _on_error)
            return

        record = self.registered_users.get(username)
        if record is None or record["password"] != password:
            QMessageBox.warning(self, self.ui("login_failed"), self.ui("invalid_credentials"))
            return

        self._complete_login(username)

    def handle_register(self) -> None:
        username = self.register_username_input.text().strip()
        display_name = self.register_display_name_input.text().strip()
        major = self.register_major_input.text().strip()
        password = self.register_password_input.text()
        confirm = self.register_confirm_input.text()

        if not username:
            QMessageBox.warning(self, self.ui("register_failed"), self.ui("choose_username"))
            return
        if not display_name:
            QMessageBox.warning(self, self.ui("register_failed"), self.ui("choose_display_name"))
            return
        if not major:
            QMessageBox.warning(self, self.ui("register_failed"), self.ui("choose_major"))
            return
        if not password or not confirm:
            QMessageBox.warning(self, self.ui("register_failed"), self.ui("enter_confirm_password"))
            return
        if password != confirm:
            QMessageBox.warning(self, self.ui("register_failed"), self.ui("passwords_do_not_match"))
            return

        if self.api_client.enabled:
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
                QMessageBox.warning(self, self.ui("register_failed"), err)

            self._start_worker(_call, _on_done, _on_error)
            return

        if username in self.registered_users:
            QMessageBox.warning(self, self.ui("register_failed"), self.ui("username_exists"))
            return

        self.registered_users[username] = {
            "password": password,
            "display_name": display_name,
            "major": major,
        }

        QMessageBox.information(self, self.ui("registration_complete"), self.ui("registration_success"))
        self.login_username_input.setText(username)
        self.register_username_input.clear()
        self.register_display_name_input.clear()
        self.register_major_input.clear()
        self.register_password_input.clear()
        self.register_confirm_input.clear()
        self._show_auth(0)

    def start_new_chat(self) -> None:
        self._flush_response_stream(open_dialog=False)
        conversation = self._active_conversation()
        if conversation is not None:
            has_user_messages = any(item["sender"] == "user" for item in conversation["messages"])
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
        if conversation is None:
            return

        result = QMessageBox.question(
            self,
            self.ui("delete_chat_confirm_title"),
            self.ui("delete_chat_confirm_body"),
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        session_id = str(conversation["session_id"])
        should_delete_remote = any(item.get("sender") == "user" for item in conversation.get("messages", []))
        should_delete_remote = should_delete_remote or bool(str(conversation.get("remote_updated_at", "")).strip())
        should_delete_remote = should_delete_remote or bool(str(conversation.get("title", "")).strip())

        if self.api_client.enabled and self.api_client.authenticated and should_delete_remote:
            try:
                self.api_client.delete_session(session_id)
            except BackendApiError as exc:
                QMessageBox.warning(self, self.ui("delete_chat_failed_title"), str(exc))
                return

        self.conversations = [item for item in self.conversations if item["session_id"] != session_id]
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
        self.resource_files = list(RESOURCE_FILES)
        self.session_id = self._new_session_id()
        self._reset_dynamic_state()
        self._build_root()
        self._show_home()

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
            return

        self._apply_agent_response(self._generate_mock_response(text))
        self.message_input.clear()

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
        request_payload = self.pending_hitl_request or self._build_localized_hitl_request()
        dialog = HitlDialog(self, UI_TEXTS[self.language], request_payload)
        accepted = dialog.exec()

        request_id = str(request_payload.get("request_id", "")).strip() if isinstance(request_payload, dict) else ""
        if request_id and self._run_remote_agent(
            message="",
            hitl_reply={"request_id": request_id, "approved": bool(accepted)},
            auto_open_hitl=False,
        ):
            return

        detail = self.ui("trace_hitl_approved") if accepted else self.ui("trace_hitl_pending")
        self._append_trace(
            self.local({"en": "Tool Use", "zh": "工具调用"}),
            self.ui("trace_hitl_update_title"),
            detail,
            "done" if accepted else "pending",
        )

    def refresh_mock_content(self) -> None:
        self._flush_response_stream(open_dialog=False)
        if self.current_username and self.api_client.authenticated:
            self.sync_bootstrap_data(record_trace=True)
            return

        self.pending_hitl_request = None
        self._reset_dynamic_state()
        self._build_root()
        self.stack.setCurrentWidget(self.dashboard_page if self.current_username else self.home_page)

    def refresh_schedule_data(self) -> None:
        self._flush_response_stream(open_dialog=False)
        if not (self.api_client.enabled and self.api_client.authenticated and self.current_username):
            self.refresh_mock_content()
            return

        def _on_done(payload):
            events = payload.get("events", [])
            conflicts = payload.get("conflicts", [])
            if isinstance(events, list):
                self.schedule_events = self._normalize_schedule_events(events)
            if isinstance(conflicts, list):
                self.conflicts = self._normalize_conflicts(conflicts)
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
            QMessageBox.warning(self, self.ui("refresh_schedule_failed_title"), err)
            self._append_trace(
                self.local({"en": "Observation", "zh": "观察"}),
                self.ui("refresh_schedule_failed_title"),
                err,
                "error",
            )

        self._start_worker(self.api_client.refresh_schedule, _on_done, _on_error)

    def _add_resource_files(self) -> None:
        selected_files, _selected_filter = QFileDialog.getOpenFileNames(
            self,
            self.ui("resource_dialog_title"),
            "",
            self.ui("resource_dialog_filter"),
        )
        if not selected_files:
            return

        existing_names = {self._resource_display_name(resource).lower() for resource in self.resource_files}
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
                    str(item.get("file_name") or item.get("name") or item.get("file_id") or "resource")
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
                    self.ui("trace_loaded_materials_detail", count=len(all_added), files=preview),
                    "done",
                )
                QMessageBox.information(
                    self,
                    self.ui("resource_added_title"),
                    self.ui("resource_added_body", count=len(all_added), skipped=_skipped_count),
                )
            if errors:
                QMessageBox.warning(
                    self,
                    self.ui("resource_upload_failed_title"),
                    self.ui("resource_upload_failed_body", details="\n".join(errors[:4])),
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
