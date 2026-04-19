"""
Frontend Relevant/main.py
PyQt6 应用入口。
启动顺序：健康检查后端 → 显示 HomePage → 跳转 AuthPage → 跳转 DashboardPage
"""

import sys
import time

import requests
from PyQt6.QtWidgets import QApplication, QMessageBox

from frontend.config import API_BASE_URL


from frontend.app import MainWindow, APP_STYLE


def wait_for_backend(timeout: int = 15) -> bool:
    """
    轮询后端 /health 接口，等待 FastAPI 服务就绪。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{API_BASE_URL}/health", timeout=1)
            if r.ok:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)

    if not wait_for_backend():
        QMessageBox.critical(
            None,
            "Backend Unreachable",
            f"Cannot connect to backend at {API_BASE_URL}.\n\nPlease ensure the FastAPI server is running."
        )
        sys.exit(1)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
