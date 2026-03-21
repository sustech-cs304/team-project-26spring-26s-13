"""PyQt6 desktop frontend prototype for the Student Productivity Agent project."""

from __future__ import annotations

import sys
from typing import Any
from uuid import uuid4

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
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
        DASHBOARD_METRICS,
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
        DASHBOARD_METRICS,
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


def localized(value, language: str):
    """Resolve bilingual values into a concrete string/list for the current language."""
    if isinstance(value, dict) and "en" in value and "zh" in value:
        return value[language]
    return value


class MetricCard(QFrame):
    def __init__(self, title: str, value: str, detail: str) -> None:
        super().__init__()
        self.setObjectName("MetricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        value_label = QLabel(value)
        value_label.setObjectName("CardValue")
        detail_label = QLabel(detail)
        detail_label.setObjectName("MutedText")
        detail_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(detail_label)


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
    def __init__(self, sender: str, sender_label: str, text: str) -> None:
        super().__init__()
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 10)

        bubble = QFrame()
        bubble.setObjectName("UserBubble" if sender == "user" else "AgentBubble")
        bubble.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(14, 12, 14, 12)
        bubble_layout.setSpacing(6)

        sender_title = QLabel(sender_label)
        sender_title.setObjectName("CardTitle")
        text_label = QLabel(text)
        text_label.setObjectName("BodyText")
        text_label.setWordWrap(True)
        text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        bubble_layout.addWidget(sender_title)
        bubble_layout.addWidget(text_label)

        if sender == "user":
            outer.addStretch(1)
            outer.addWidget(bubble, 0)
        else:
            outer.addWidget(bubble, 0)
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
        self.api_base_url_input = QLineEdit(str(api_state.get("base_url", "")))
        self.api_key_input = QLineEdit(str(api_state.get("api_key", "")))
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_form.addRow(texts["settings_api_base_url"], self.api_base_url_input)
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
            "api_base_url": self.api_base_url_input.text().strip(),
            "api_key": self.api_key_input.text().strip(),
        }


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.api_client = BackendApiClient.from_env()
        self.language = "en"
        self.current_username: str | None = None
        self.pending_hitl_request: dict[str, Any] | None = None
        self.registered_users = {
            account["username"]: {
                "password": account["password"],
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
            "base_url": "",
            "api_key": "",
            "saved": False,
        }
        self.resource_files = list(RESOURCE_FILES)
        self.conversations: list[dict[str, Any]] = []
        self.active_conversation_id: str | None = None
        self.session_id = self._new_session_id()
        self.chat_messages: list[dict[str, str]] = []
        self.trace_events: list[dict[str, str]] = []
        self.schedule_events: list[dict[str, str]] = []
        self.conflicts: list[dict[str, str]] = []

        self._reset_dynamic_state()
        self._build_root()
        self._show_home()

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

    def connection_settings_payload(self) -> dict[str, Any] | None:
        payload: dict[str, Any] = {}
        if self.cas_settings.get("saved"):
            payload["cas"] = {
                "username": self.cas_settings.get("username", ""),
                "password": self.cas_settings.get("password", ""),
            }
        if self.api_settings.get("saved"):
            payload["api"] = {
                "base_url": self.api_settings.get("base_url", ""),
                "api_key": self.api_settings.get("api_key", ""),
            }
        return payload or None

    def current_user_id(self) -> str:
        return self.current_username or "local_student"

    def active_tab_key(self) -> str:
        return "chat"

    def selected_feature_key(self, prompt: str = "") -> str:
        lowered = prompt.lower()
        if any(keyword in lowered for keyword in ("schedule", "deadline", "日程", "冲突", "截止")):
            return "scheduler"
        if any(keyword in lowered for keyword in ("credit", "dorm", "handbook", "学分", "宿舍", "手册")):
            return "encyclopedia"
        if any(keyword in lowered for keyword in ("delete", "overwrite", "modify", "删除", "覆盖", "修改")):
            return "os_automation"
        return {
            "chat": "agent_chat",
            "schedule": "scheduler",
            "encyclopedia": "encyclopedia",
        }.get(self.active_tab_key(), "agent_chat")

    def _default_user_profile(self) -> dict[str, str]:
        return {
            "name": self.local(PROFILE["name"]),
            "major": self.local(PROFILE["major"]),
            "focus": self.local(PROFILE["focus"]),
        }

    def _build_localized_chat_messages(self) -> list[dict[str, str]]:
        return [
            {
                "sender": item["sender"],
                "text": self.local(item["text"]),
            }
            for item in CHAT_MESSAGES
        ]

    def _build_new_chat_messages(self) -> list[dict[str, str]]:
        for item in CHAT_MESSAGES:
            if item["sender"] == "agent":
                return [{"sender": "agent", "text": self.local(item["text"])}]
        return []

    def _create_conversation(
        self,
        *,
        session_id: str | None = None,
        messages: list[dict[str, str]] | None = None,
        trace: list[dict[str, str]] | None = None,
        pending_hitl_request: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "session_id": session_id or self._new_session_id(),
            "messages": list(messages or self._build_new_chat_messages()),
            "trace": list(trace or []),
            "pending_hitl_request": pending_hitl_request,
        }

    def _derive_conversation_title(self, conversation: dict[str, Any]) -> str:
        for item in conversation["messages"]:
            if item["sender"] == "user" and item["text"].strip():
                title = item["text"].strip().replace("\n", " ")
                return title[:32] + ("..." if len(title) > 32 else "")
        return self.ui("new_chat")

    def _conversation_meta(self, conversation: dict[str, Any]) -> str:
        return self.ui(
            "conversation_meta",
            messages=len(conversation["messages"]),
            trace=len(conversation["trace"]),
        )

    def _resource_meta(self, resource_name: str) -> str:
        suffix = resource_name.rsplit(".", 1)[-1].upper() if "." in resource_name else "FILE"
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
            if status not in {"done", "running", "pending"}:
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
        self._load_schedule_content()
        self._load_encyclopedia_result("default")
        self._load_resource_files()
        self._refresh_profile_views()

    def _reset_dynamic_state(self) -> None:
        self._initialize_default_conversations()
        self.schedule_events = self._build_localized_schedule_events()
        self.conflicts = self._build_localized_conflicts()

        if self.current_username:
            record = self.registered_users.get(self.current_username)
            major = self.local(record["major"]) if record else self.local(PROFILE["major"])
            self.current_user = {
                "name": self.current_username,
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
            item = QListWidgetItem(f"{resource}\n{self._resource_meta(resource)}", self.resource_list)
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

        session_id = current.data(Qt.ItemDataRole.UserRole)
        if not session_id or session_id == self.active_conversation_id:
            return
        self._activate_conversation(str(session_id))

    def toggle_language(self) -> None:
        current_page = self.stack.currentWidget().objectName() if hasattr(self, "stack") else "HomePage"
        auth_tab_index = self.auth_tabs.currentIndex() if hasattr(self, "auth_tabs") else 0
        login_username = self.login_username_input.text() if hasattr(self, "login_username_input") else ""
        register_username = self.register_username_input.text() if hasattr(self, "register_username_input") else ""

        self.language = "zh" if self.language == "en" else "en"
        if self.current_username:
            record = self.registered_users.get(self.current_username)
            major = self.local(record["major"]) if record else self.local(PROFILE["major"])
            self.current_user = {
                "name": self.current_user["name"],
                "major": major,
                "focus": self.ui("authenticated_focus"),
            }
        else:
            self._reset_dynamic_state()
        self._build_root()

        self.login_username_input.setText(login_username)
        self.register_username_input.setText(register_username)

        if current_page == "DashboardPage":
            self.stack.setCurrentWidget(self.dashboard_page)
            if self.current_username and self.api_client.enabled:
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
        history_hint = QLabel(self.ui("conversation_history_hint"))
        history_hint.setObjectName("MutedText")
        history_hint.setWordWrap(True)
        self.history_list = QListWidget()
        self.history_list.setObjectName("ConversationList")
        self.history_list.currentItemChanged.connect(self.handle_history_selection)

        history_header.addWidget(history_title)
        history_header.addStretch(1)
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
        self._load_resource_files()

        add_button = QPushButton(self.ui("add_resource"))
        add_button.clicked.connect(self._show_placeholder_message)

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
        self.message_input.setPlaceholderText(self.ui("message_placeholder"))
        self.message_input.setFixedHeight(110)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        send_button = QPushButton(self.ui("send"))
        send_button.setObjectName("PrimaryButton")
        send_button.clicked.connect(self.handle_send_message)
        clear_button = QPushButton(self.ui("clear_draft"))
        clear_button.clicked.connect(self.message_input.clear)
        button_row.addStretch(1)
        button_row.addWidget(clear_button)
        button_row.addWidget(send_button)

        composer_layout.addWidget(composer_title)
        composer_layout.addWidget(self.message_input)
        composer_layout.addLayout(button_row)

        layout.addWidget(composer_card)
        return tab

    def _build_schedule_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        summary = InfoCard(self.ui("schedule_title"), self.ui("schedule_body"))
        layout.addWidget(summary)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        events_card = QFrame()
        events_card.setObjectName("PanelCard")
        events_layout = QVBoxLayout(events_card)
        events_layout.setContentsMargins(16, 16, 16, 16)
        events_layout.setSpacing(10)
        events_title = QLabel(self.ui("upcoming_events"))
        events_title.setObjectName("SectionTitle")
        self.events_list = QListWidget()
        events_layout.addWidget(events_title)
        events_layout.addWidget(self.events_list)

        conflicts_card = QFrame()
        conflicts_card.setObjectName("PanelCard")
        conflicts_layout = QVBoxLayout(conflicts_card)
        conflicts_layout.setContentsMargins(16, 16, 16, 16)
        conflicts_layout.setSpacing(10)
        conflicts_title = QLabel(self.ui("conflict_notifications"))
        conflicts_title.setObjectName("SectionTitle")

        self.conflict_container = QWidget()
        self.conflict_layout = QVBoxLayout(self.conflict_container)
        self.conflict_layout.setContentsMargins(0, 0, 0, 0)
        self.conflict_layout.setSpacing(10)
        self.conflict_layout.addStretch(1)

        conflict_scroll = QScrollArea()
        conflict_scroll.setWidgetResizable(True)
        conflict_scroll.setFrameShape(QFrame.Shape.NoFrame)
        conflict_scroll.setWidget(self.conflict_container)

        conflicts_layout.addWidget(conflicts_title)
        conflicts_layout.addWidget(conflict_scroll)

        grid.addWidget(events_card, 0, 0)
        grid.addWidget(conflicts_card, 0, 1)
        layout.addLayout(grid, 1)
        return tab

    def _build_encyclopedia_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        intro = InfoCard(self.ui("encyclopedia_title"), self.ui("encyclopedia_body"))
        layout.addWidget(intro)

        search_card = QFrame()
        search_card.setObjectName("PanelCard")
        search_layout = QVBoxLayout(search_card)
        search_layout.setContentsMargins(16, 16, 16, 16)
        search_layout.setSpacing(10)

        search_title = QLabel(self.ui("search_handbook"))
        search_title.setObjectName("SectionTitle")
        query_row = QHBoxLayout()
        query_row.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.ui("search_placeholder"))
        self.search_input.returnPressed.connect(self.handle_search)
        search_button = QPushButton(self.ui("search"))
        search_button.setObjectName("PrimaryButton")
        search_button.clicked.connect(self.handle_search)
        query_row.addWidget(self.search_input, 1)
        query_row.addWidget(search_button)

        suggestions = QHBoxLayout()
        suggestions.setSpacing(8)
        for key in ("suggestion_credit", "suggestion_dorm", "suggestion_graduation"):
            text = self.ui(key)
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, value=text: self.load_search_query(value))
            suggestions.addWidget(button)

        search_layout.addWidget(search_title)
        search_layout.addLayout(query_row)
        search_layout.addLayout(suggestions)
        layout.addWidget(search_card)

        result_grid = QGridLayout()
        result_grid.setHorizontalSpacing(12)
        result_grid.setVerticalSpacing(12)

        answer_card = QFrame()
        answer_card.setObjectName("PanelCard")
        answer_layout = QVBoxLayout(answer_card)
        answer_layout.setContentsMargins(16, 16, 16, 16)
        answer_layout.setSpacing(10)
        answer_title = QLabel(self.ui("answer_rendering"))
        answer_title.setObjectName("SectionTitle")
        self.answer_browser = QTextBrowser()
        answer_layout.addWidget(answer_title)
        answer_layout.addWidget(self.answer_browser)

        citation_card = QFrame()
        citation_card.setObjectName("PanelCard")
        citation_layout = QVBoxLayout(citation_card)
        citation_layout.setContentsMargins(16, 16, 16, 16)
        citation_layout.setSpacing(10)
        citation_title = QLabel(self.ui("retrieved_citations"))
        citation_title.setObjectName("SectionTitle")
        self.citation_list = QListWidget()
        citation_layout.addWidget(citation_title)
        citation_layout.addWidget(self.citation_list)

        result_grid.addWidget(answer_card, 0, 0)
        result_grid.addWidget(citation_card, 0, 1)
        layout.addLayout(result_grid, 1)
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

    def _load_chat_messages(self, messages: list[dict[str, str]]) -> None:
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for message in messages:
            self.chat_layout.insertWidget(
                self.chat_layout.count() - 1,
                BubbleWidget(message["sender"], self._sender_label(message["sender"]), message["text"]),
            )
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

    def _load_schedule_content(self) -> None:
        if not hasattr(self, "events_list") or not hasattr(self, "conflict_layout"):
            return
        self.events_list.clear()
        for event in self.schedule_events:
            item = QListWidgetItem(f"{event['title']}\n{event['time']}  |  {event['source']}\n{event['detail']}")
            self.events_list.addItem(item)

        while self.conflict_layout.count() > 1:
            item = self.conflict_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for conflict in self.conflicts:
            card = QFrame()
            card.setObjectName("ConflictCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)
            title = QLabel(conflict["title"])
            title.setObjectName("SectionTitle")
            detail = QLabel(conflict["detail"])
            detail.setObjectName("BodyText")
            detail.setWordWrap(True)
            card_layout.addWidget(title)
            card_layout.addWidget(detail)
            self.conflict_layout.insertWidget(self.conflict_layout.count() - 1, card)

    def _load_encyclopedia_result(self, key: str) -> None:
        if not hasattr(self, "answer_browser") or not hasattr(self, "citation_list"):
            return
        payload = ENCYCLOPEDIA_RESULTS.get(key, ENCYCLOPEDIA_RESULTS["default"])
        self.answer_browser.setMarkdown(self.local(payload["answer"]))
        self.citation_list.clear()
        for citation in self.local(payload["citations"]):
            QListWidgetItem(citation, self.citation_list)

    def _load_encyclopedia_payload(self, payload: dict[str, Any]) -> None:
        if not hasattr(self, "answer_browser") or not hasattr(self, "citation_list"):
            return
        answer_markdown = str(payload.get("answer_markdown", ""))
        citations = payload.get("citations", [])
        query = str(payload.get("query", "")).strip()

        self.answer_browser.setMarkdown(answer_markdown or self.local(ENCYCLOPEDIA_RESULTS["default"]["answer"]))
        self.citation_list.clear()
        if isinstance(citations, list):
            for citation in citations:
                QListWidgetItem(str(citation), self.citation_list)
        if query and hasattr(self, "search_input"):
            self.search_input.setText(query)

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
            if not payload["cas_username"] or not payload["cas_password"]:
                QMessageBox.warning(
                    self,
                    self.ui("settings_dialog_title"),
                    self.ui("settings_missing_cas"),
                )
                return

            self.cas_settings = {
                "username": payload["cas_username"],
                "password": payload["cas_password"],
                "saved": True,
            }
            QMessageBox.information(
                self,
                self.ui("settings_saved_title"),
                self.ui("settings_cas_saved"),
            )
            return

        if not payload["api_base_url"]:
            QMessageBox.warning(
                self,
                self.ui("settings_dialog_title"),
                self.ui("settings_missing_api"),
            )
            return

        base_url = payload["api_base_url"].rstrip("/")
        api_key = payload["api_key"]
        self.api_settings = {
            "base_url": base_url,
            "api_key": api_key,
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

    def _complete_login(self, username: str) -> None:
        self.current_username = username
        self._reset_dynamic_state()
        self._build_root()
        self.stack.setCurrentWidget(self.dashboard_page)
        self.sync_bootstrap_data(record_trace=True)

    def sync_bootstrap_data(self, record_trace: bool) -> None:
        if not (self.api_client.enabled and self.current_username):
            return

        try:
            payload = self.api_client.bootstrap_dashboard(self.current_user_id())
        except BackendApiError as exc:
            if record_trace:
                self._append_trace(
                    self.local({"en": "Observation", "zh": "观察"}),
                    self.ui("trace_backend_unavailable_title"),
                    self.ui("trace_backend_unavailable_detail", error=str(exc)),
                    "pending",
                )
            return

        self._apply_bootstrap_payload(payload)
        if record_trace:
            self._append_trace(
                self.local({"en": "Observation", "zh": "观察"}),
                self.ui("trace_bootstrap_loaded_title"),
                self.ui("trace_bootstrap_loaded_detail"),
                "done",
            )

    def _apply_bootstrap_payload(self, payload: dict[str, Any]) -> None:
        user_profile = payload.get("user_profile", {})
        display_name = str(user_profile.get("display_name") or self.current_username or self.local(PROFILE["name"]))
        major = str(user_profile.get("major") or self.local(PROFILE["major"]))
        self.current_user = {
            "name": display_name,
            "major": major,
            "focus": self.ui("authenticated_focus"),
        }

        chat_history = payload.get("chat_history", [])
        if isinstance(chat_history, list) and chat_history:
            self.chat_messages = [
                {
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
        if isinstance(materials, list) and materials:
            self.resource_files = [
                str(item.get("file_name") or item.get("name") or item.get("file_id") or "resource")
                for item in materials
            ]
            self._load_resource_files()

        local_schedule = payload.get("local_schedule", {})
        if isinstance(local_schedule, dict):
            events = local_schedule.get("events", [])
            conflicts = local_schedule.get("conflicts", [])
            if isinstance(events, list) and events:
                self.schedule_events = self._normalize_schedule_events(events)
            if isinstance(conflicts, list) and conflicts:
                self.conflicts = self._normalize_conflicts(conflicts)
            self._load_schedule_content()

        self._refresh_profile_views()

    def _apply_agent_response(self, response: dict[str, Any], auto_open_hitl: bool = True) -> None:
        assistant_message = response.get("assistant_message", {})
        assistant_text = str(assistant_message.get("content", "")).strip()
        if assistant_text:
            self.chat_messages.append({"sender": "agent", "text": assistant_text})
            self._load_chat_messages(self.chat_messages)

        trace = response.get("trace", [])
        if isinstance(trace, list) and trace:
            self.trace_events.extend(self._normalize_backend_trace_events(trace))
            self._load_trace_events(self.trace_events)

        ui_payload = response.get("ui_payload", {})
        if isinstance(ui_payload, dict):
            schedule_payload = ui_payload.get("schedule")
            if isinstance(schedule_payload, dict):
                events = schedule_payload.get("events", [])
                conflicts = schedule_payload.get("conflicts", [])
                if isinstance(events, list) and events:
                    self.schedule_events = self._normalize_schedule_events(events)
                if isinstance(conflicts, list) and conflicts:
                    self.conflicts = self._normalize_conflicts(conflicts)
                self._load_schedule_content()

            encyclopedia_payload = ui_payload.get("encyclopedia")
            if isinstance(encyclopedia_payload, dict):
                self._load_encyclopedia_payload(encyclopedia_payload)

        hitl_request = response.get("hitl_request")
        self.pending_hitl_request = self._normalize_hitl_request(hitl_request) if isinstance(hitl_request, dict) else None
        self._sync_active_conversation()
        if self.pending_hitl_request and auto_open_hitl:
            self.open_hitl_dialog()

    def _run_remote_agent(
        self,
        *,
        message: str,
        selected_feature: str,
        hitl_reply: dict[str, Any] | None = None,
        auto_open_hitl: bool = True,
    ) -> bool:
        if not (self.api_client.enabled and self.current_username):
            return False

        try:
            response = self.api_client.run_agent(
                user_id=self.current_user_id(),
                session_id=self.session_id,
                message=message,
                active_tab=self.active_tab_key(),
                selected_feature=selected_feature,
                hitl_reply=hitl_reply,
                connection_settings=self.connection_settings_payload(),
            )
        except BackendApiError as exc:
            self._append_trace(
                self.local({"en": "Observation", "zh": "观察"}),
                self.ui("trace_backend_unavailable_title"),
                self.ui("trace_backend_unavailable_detail", error=str(exc)),
                "pending",
            )
            return False

        self._apply_agent_response(response, auto_open_hitl=auto_open_hitl)
        return True

    def handle_password_login(self) -> None:
        username = self.login_username_input.text().strip()
        password = self.login_password_input.text()
        if not username or not password:
            QMessageBox.warning(self, self.ui("login_failed"), self.ui("enter_both_username_password"))
            return

        record = self.registered_users.get(username)
        if record is None or record["password"] != password:
            QMessageBox.warning(self, self.ui("login_failed"), self.ui("invalid_credentials"))
            return

        self._complete_login(username)

    def handle_register(self) -> None:
        username = self.register_username_input.text().strip()
        password = self.register_password_input.text()
        confirm = self.register_confirm_input.text()

        if not username:
            QMessageBox.warning(self, self.ui("register_failed"), self.ui("choose_username"))
            return
        if username in self.registered_users:
            QMessageBox.warning(self, self.ui("register_failed"), self.ui("username_exists"))
            return
        if not password or not confirm:
            QMessageBox.warning(self, self.ui("register_failed"), self.ui("enter_confirm_password"))
            return
        if password != confirm:
            QMessageBox.warning(self, self.ui("register_failed"), self.ui("passwords_do_not_match"))
            return

        self.registered_users[username] = {
            "password": password,
            "major": PROFILE["major"],
        }

        QMessageBox.information(self, self.ui("registration_complete"), self.ui("registration_success"))
        self.login_username_input.setText(username)
        self.register_username_input.clear()
        self.register_password_input.clear()
        self.register_confirm_input.clear()
        self._show_auth(0)

    def start_new_chat(self) -> None:
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

    def logout(self) -> None:
        self.current_username = None
        self.pending_hitl_request = None
        self.resource_files = list(RESOURCE_FILES)
        self.session_id = self._new_session_id()
        self._reset_dynamic_state()
        self._build_root()
        self._show_home()

    def load_search_query(self, query: str) -> None:
        if not hasattr(self, "search_input"):
            return
        self.search_input.setText(query)
        self.handle_search()

    def handle_search(self) -> None:
        if not hasattr(self, "search_input"):
            return
        raw_query = self.search_input.text().strip()
        if raw_query and self._run_remote_agent(message=raw_query, selected_feature="encyclopedia"):
            return

        query = raw_query.lower()
        if "credit" in query or "学分" in query:
            key = "credit"
        elif "dorm" in query or "宿舍" in query:
            key = "dorm"
        else:
            key = "default"

        self._load_encyclopedia_result(key)
        display_query = query or self.local(ENCYCLOPEDIA_RESULTS["default"]["query"])
        self._append_trace(
            self.local({"en": "Observation", "zh": "观察"}),
            self.ui("trace_rendered_encyclopedia_title"),
            self.ui("trace_rendered_encyclopedia_detail", query=display_query),
            "running",
        )

    def handle_send_message(self) -> None:
        text = self.message_input.toPlainText().strip()
        if not text:
            return

        self.chat_messages.append({"sender": "user", "text": text})
        self._move_active_conversation_to_top()
        self._load_chat_messages(self.chat_messages)
        if self._run_remote_agent(message=text, selected_feature=self.selected_feature_key(text)):
            self.message_input.clear()
            return

        reply = self._generate_mock_reply(text)
        self.chat_messages.append({"sender": "agent", "text": reply})
        self._load_chat_messages(self.chat_messages)
        self.message_input.clear()

        prompt_preview = text[:72] + ("..." if len(text) > 72 else "")
        self._append_trace(
            self.local({"en": "Reasoning", "zh": "推理"}),
            self.ui("trace_responded_main_chat_title"),
            self.ui("trace_responded_main_chat_detail", prompt=prompt_preview),
            "done",
        )

    def _generate_mock_reply(self, prompt: str) -> str:
        lowered = prompt.lower()
        if any(keyword in lowered for keyword in ("schedule", "deadline", "日程", "冲突", "截止")):
            return self.ui("reply_schedule")
        if any(keyword in lowered for keyword in ("credit", "dorm", "handbook", "学分", "宿舍", "手册")):
            return self.ui("reply_encyclopedia")
        if any(keyword in lowered for keyword in ("delete", "overwrite", "modify", "删除", "覆盖", "修改")):
            self.open_hitl_dialog()
            return self.ui("reply_hitl")
        return self.ui("reply_generic")

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
        request_payload = self.pending_hitl_request or self._build_localized_hitl_request()
        dialog = HitlDialog(self, UI_TEXTS[self.language], request_payload)
        accepted = dialog.exec()

        request_id = str(request_payload.get("request_id", "")).strip() if isinstance(request_payload, dict) else ""
        if request_id and self._run_remote_agent(
            message="",
            selected_feature="os_automation",
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
        if self.current_username and self.api_client.enabled:
            self.sync_bootstrap_data(record_trace=True)
            return

        self.pending_hitl_request = None
        self._reset_dynamic_state()
        self._build_root()
        self.stack.setCurrentWidget(self.dashboard_page if self.current_username else self.home_page)

    def _show_placeholder_message(self) -> None:
        QMessageBox.information(self, self.ui("upload_placeholder_title"), self.ui("upload_placeholder_body"))


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
