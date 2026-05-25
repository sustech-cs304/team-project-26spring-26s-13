"""
backend/agent/tools/__init__.py
导入所有工具模块，确保 @agent.tool 装饰器在 loop.py 初始化 agent 后执行注册。
loop.py 中 import backend.agent.tools 时此文件自动执行。
"""

from backend.agent.tools import scheduler  # noqa: F401
from backend.agent.tools import rag  # noqa: F401
from backend.agent.tools import os_automation  # noqa: F401
from backend.agent.tools import study_copilot  # noqa: F401
from backend.agent.tools import personal_tasks  # noqa: F401
from backend.agent.tools import library_room  # noqa: F401
from backend.agent.tools import time_utils  # noqa: F401
