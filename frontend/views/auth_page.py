"""
God Xun-Frontend/views/auth_page.py
登录/注册页面。
认证成功后 emit authenticated signal，MainWindow 切换到 DashboardPage。
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QLabel, QLineEdit, QPushButton, QTabWidget,
    QVBoxLayout, QWidget,
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
        # TODO: self._setup_ui()

    def _setup_ui(self) -> None:
        """
        布局：
          QTabWidget
          ├── Tab "Login":    username, password, Login button
          └── Tab "Register": username, password, display_name, major, Register button
        """
        # TODO
        raise NotImplementedError

    def _on_login(self) -> None:
        """
        点击 Login 按钮：
        1. 调用 api_client.login(username, password)
        2. 成功 → emit authenticated(user_id, display_name)
        3. 失败 → 显示 QMessageBox 错误提示
        """
        # TODO
        raise NotImplementedError

    def _on_register(self) -> None:
        """
        点击 Register 按钮：
        1. 调用 api_client.register(...)
        2. 成功 → 自动调用 api_client.login() 获取 token，emit authenticated
        3. 失败 → 显示错误提示
        """
        # TODO
        raise NotImplementedError
