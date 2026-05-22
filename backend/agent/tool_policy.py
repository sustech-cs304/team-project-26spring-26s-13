"""
backend/agent/tool_policy.py
Agent 工具暴露策略。

目标：
1. 将“哪些工具应该暴露给模型”与业务执行解耦。
2. 对占位中的文件系统工具增加显式意图门禁，避免普通聊天被误路由到文件操作。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import ToolDefinition

from backend.schemas.agent import RouteType

FILE_TOOL_NAMES = {
    "file_read",
    "file_create",
    "file_update",
    "file_delete",
    "batch_rename",
}

# 预约类工具名称：这些工具涉及资源锁定，需要 HITL 审批
BOOKING_TOOL_NAMES = {
    "book_library_room",
}

_FILE_ACTION_TERMS = {
    "read",
    "open",
    "create",
    "write",
    "save",
    "update",
    "overwrite",
    "delete",
    "remove",
    "rename",
    "move",
    "copy",
    "load",
    "读取",
    "打开",
    "创建",
    "新建",
    "写入",
    "保存",
    "更新",
    "覆盖",
    "删除",
    "移除",
    "重命名",
    "移动",
    "复制",
    "载入",
}

_FILE_TARGET_TERMS = {
    "file",
    "folder",
    "directory",
    "workspace",
    "path",
    "local",
    ".txt",
    ".md",
    ".pdf",
    ".ppt",
    ".pptx",
    ".doc",
    ".docx",
    ".csv",
    ".json",
    ".py",
    "文件",
    "文档",
    "目录",
    "文件夹",
    "路径",
    "本地",
    "工作区",
}

_LIBRARY_TERMS = {
    "图书馆",
    "讨论间",
    "讨论室",
    "研修间",
    "自习室",
    "空间预约",
    "预约系统",
    "空房间",
    "study room",
    "discussion room",
    "library",
    "room availability",
}

_NON_FILE_MEMORY_TERMS = {
    "remember",
    "memory",
    "memorize",
    "记住",
    "记忆",
    "记下来",
    "帮我记",
    "请为我记忆",
    "请记住",
}


def _prompt_to_text(prompt: str | Sequence[Any] | None) -> str:
    if prompt is None:
        return ""
    if isinstance(prompt, str):
        return prompt

    parts: list[str] = []
    for item in prompt:
        text = getattr(item, "content", None)
        if isinstance(text, str):
            parts.append(text)
        else:
            parts.append(str(item))
    return "\n".join(parts)


def has_explicit_file_operation_intent(prompt: str | Sequence[Any] | None) -> bool:
    """
    仅当用户明确表达“本地文件/目录/workspace 操作”时，才允许暴露文件工具。

    例如：
    - “在 workspace 里创建 todo.md”
    - “读取本地 notes.txt”
    - “把这个目录下的文件批量重命名”

    不应判定为文件操作的例子：
    - “请为我记忆：我 5 月 15 日去考 TOEFL”
    - “记住我下周要答辩”
    """
    text = _prompt_to_text(prompt).strip()
    if not text:
        return False

    lowered = text.lower()

    has_action = any(term in lowered for term in _FILE_ACTION_TERMS)
    has_target = any(term in lowered for term in _FILE_TARGET_TERMS)

    if has_action and has_target:
        return True

    # “记忆/记住/remember” 很容易被模型误解成“写文件保存”，这里显式排除。
    if any(term in lowered for term in _NON_FILE_MEMORY_TERMS):
        return False

    return False


async def prepare_tools_for_prompt(
    ctx: RunContext[Any],
    tool_defs: list[ToolDefinition],
) -> list[ToolDefinition]:
    """
    动态裁剪本轮可见工具。

    当前策略：
    - 仅在用户显式请求本地文件操作时，暴露 file_* / batch_rename 工具。
    - 其它请求保留这些占位工具为“不可见”，从而避免误触发 NotImplementedError。
    """
    if has_explicit_file_operation_intent(ctx.prompt):
        return tool_defs

    return [tool_def for tool_def in tool_defs if tool_def.name not in FILE_TOOL_NAMES]


def normalize_route_for_prompt(user_prompt: str, route: RouteType) -> RouteType:
    """
    若没有显式文件操作意图，则不允许把普通聊天误标为 os_automation。
    """
    if route == "os_automation" and not has_explicit_file_operation_intent(user_prompt):
        return "chat"
    return route


def has_library_intent(prompt: str | Sequence[Any] | None) -> bool:
    """判断用户消息是否涉及图书馆讨论间查询。"""
    text = _prompt_to_text(prompt).strip().lower()
    if not text:
        return False
    return any(term in text for term in _LIBRARY_TERMS)
