"""
God Xun-Frontend/main.py
PyQt6 应用入口。
启动顺序：健康检查后端 → 显示 HomePage → 跳转 AuthPage → 跳转 DashboardPage
"""

import sys
import time

import requests
from PyQt6.QtWidgets import QApplication, QMessageBox

from frontend.config import API_BASE_URL
from frontend.views.home_page import HomePage


def wait_for_backend(timeout: int = 10) -> bool:
    """
    轮询后端 /health 接口，等待 FastAPI 服务就绪。

    Args:
        timeout: 最大等待秒数

    Returns:
        True 表示后端已就绪，False 表示超时
    """
    # TODO:
    # deadline = time.time() + timeout
    # while time.time() < deadline:
    #     try:
    #         r = requests.get(f"{API_BASE_URL}/health", timeout=1)
    #         if r.ok: return True
    #     except Exception:
    #         pass
    #     time.sleep(0.5)
    # return False
    raise NotImplementedError


def main() -> None:
    app = QApplication(sys.argv)

    # TODO:
    # if not wait_for_backend():
    #     QMessageBox.critical(None, "Error", "Cannot connect to backend. Please start the server first.")
    #     sys.exit(1)

    # home = HomePage()
    # home.show()
    # sys.exit(app.exec())
    raise NotImplementedError


if __name__ == "__main__":
    main()
