# backend/agent/tools/base.py
from functools import wraps
from typing import Any, Callable

def safe_tool(func: Callable) -> Callable:
    """
    装饰器：捕获工具执行中的任何非 HITL 异常。
    将异常转化为以 'ERROR:' 开头的字符串，供 Agent 进行 Observation。
    """
    @wraps(func)
    async def wrapper(*args, **kwargs) -> str | Any:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            # 不要捕获 HITLInterrupt，让它抛给 loop.py
            if "HITLInterrupt" in type(e).__name__:
                raise e
            return f"ERROR: 执行工具时发生错误: {str(e)}"
    return wrapper