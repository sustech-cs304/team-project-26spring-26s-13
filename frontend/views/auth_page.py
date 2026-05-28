"""
Frontend Relevant/views/auth_page.py
登录/注册页面。
认证成功后 emit authenticated signal，MainWindow 切换到 DashboardPage。
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from frontend.api.client import APIError, api_client


class AuthPage(QWidget):
    """
    包含 Login 和 Register 两个 Tab。
    认证成功后 emit authenticated(user_id, display_name)。
    """

    authenticated = pyqtSignal(str, str)  # (user_id, display_name)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """
        布局：
          QTabWidget
          ├── Tab "Login":    username, password, Login button
          └── Tab "Register": username, password, display_name, major, Register button
        """
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("Student Productivity Agent")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        tabs = QTabWidget(self)

        login_tab = QWidget()
        login_layout = QVBoxLayout(login_tab)
        self._login_username = QLineEdit(login_tab)
        self._login_username.setPlaceholderText("Username")
        self._login_password = QLineEdit(login_tab)
        self._login_password.setPlaceholderText("Password")
        self._login_password.setEchoMode(QLineEdit.EchoMode.Password)
        login_button = QPushButton("Login", login_tab)
        login_button.clicked.connect(self._on_login)
        login_layout.addWidget(self._login_username)
        login_layout.addWidget(self._login_password)
        login_layout.addWidget(login_button)
        login_layout.addStretch(1)

        register_tab = QWidget()
        register_layout = QVBoxLayout(register_tab)
        self._register_username = QLineEdit(register_tab)
        self._register_username.setPlaceholderText("Username")
        self._register_display_name = QLineEdit(register_tab)
        self._register_display_name.setPlaceholderText("Display name")
        self._register_major = QLineEdit(register_tab)
        self._register_major.setPlaceholderText("Major")
        self._register_password = QLineEdit(register_tab)
        self._register_password.setPlaceholderText("Password")
        self._register_password.setEchoMode(QLineEdit.EchoMode.Password)
        register_button = QPushButton("Register", register_tab)
        register_button.clicked.connect(self._on_register)
        register_layout.addWidget(self._register_username)
        register_layout.addWidget(self._register_display_name)
        register_layout.addWidget(self._register_major)
        register_layout.addWidget(self._register_password)
        register_layout.addWidget(register_button)
        register_layout.addStretch(1)

        tabs.addTab(login_tab, "Login")
        tabs.addTab(register_tab, "Register")
        layout.addWidget(tabs, 1)

    def _on_login(self) -> None:
        """
        点击 Login 按钮：
        1. 调用 api_client.login(username, password)
        2. 成功 → emit authenticated(user_id, display_name)
        3. 失败 → 显示 QMessageBox 错误提示
        """
        username = self._login_username.text().strip()
        password = self._login_password.text()
        if not username or not password:
            QMessageBox.warning(
                self, "Login failed", "Username and password are required."
            )
            return
        try:
            payload = api_client.login(username, password)
        except APIError as exc:
            QMessageBox.warning(self, "Login failed", exc.detail)
            return
        self.authenticated.emit(
            str(payload.get("user_id") or username),
            str(payload.get("display_name") or username),
        )

    def _on_register(self) -> None:
        """
        点击 Register 按钮：
        1. 调用 api_client.register(...)
        2. 成功 → 自动调用 api_client.login() 获取 token，emit authenticated
        3. 失败 → 显示错误提示
        """
        username = self._register_username.text().strip()
        password = self._register_password.text()
        display_name = self._register_display_name.text().strip() or username
        major = self._register_major.text().strip()
        if not username or not password:
            QMessageBox.warning(
                self, "Registration failed", "Username and password are required."
            )
            return
        try:
            payload = api_client.register(username, password, display_name, major)
        except APIError as exc:
            QMessageBox.warning(self, "Registration failed", exc.detail)
            return
        self.authenticated.emit(
            str(payload.get("user_id") or username),
            str(payload.get("display_name") or display_name),
        )
