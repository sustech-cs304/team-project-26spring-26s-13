"""
backend/agent/tools/os_automation.py
OS 文件系统自动化工具。

安全约束（必须强制执行）：
  1. 所有操作限制在用户指定的 WORKSPACE 目录内（防止越权访问）
  2. DELETE / RENAME / UPDATE 操作必须触发 HITL（不得绕过）
  3. 每次操作执行后写入 audit_log 表
  4. 工具不得执行任何 shell 命令（os.system、subprocess 等），只能用 os/shutil API

WORKSPACE 说明：
  当前阶段 workspace = 用户 home 目录下的 "spa_workspace/" 子目录。
  严禁访问 workspace 以外的路径（路径必须经过 _safe_path() 验证）。
"""

import os
import shutil
from pathlib import Path

from pydantic_ai import RunContext

from backend.agent.loop import AgentDeps, agent, HITLInterrupt
from backend.agent.hitl import hitl_manager
from backend.services import audit_service


def _safe_path(workspace: Path, target: str) -> Path:
    """
    验证 target 路径在 workspace 内，防止路径穿越攻击（../../../etc/passwd 等）。

    Args:
        workspace: 用户工作区根目录的绝对 Path
        target:    用户/LLM 提供的目标路径（相对或绝对）

    Returns:
        解析后的绝对 Path（保证在 workspace 内）

    Raises:
        PermissionError: 路径在 workspace 外
    """
    # TODO:
    # resolved = (workspace / target).resolve()
    # if not resolved.is_relative_to(workspace):
    #     raise PermissionError(f"Path '{target}' is outside the workspace.")
    # return resolved
    raise NotImplementedError


@agent.tool
async def file_read(ctx: RunContext[AgentDeps], path: str) -> str:
    """
    读取 workspace 内指定文件的文本内容。
    不触发 HITL（只读操作）。

    Args:
        path: 相对于 workspace 的文件路径

    Returns:
        文件文本内容（截断至前 10000 字符以避免 token 爆炸）
        若文件不存在，返回 "ERROR:FILE_NOT_FOUND"
    """
    # TODO:
    # safe = _safe_path(workspace, path)
    # return safe.read_text(encoding="utf-8")[:10000]
    raise NotImplementedError


@agent.tool
async def file_create(ctx: RunContext[AgentDeps], path: str, content: str) -> str:
    """
    在 workspace 内创建新文件（若已存在则报错，不覆盖）。
    不触发 HITL。写入后记录 audit_log。

    Args:
        path:    相对于 workspace 的目标路径（含文件名）
        content: 文件文本内容

    Returns:
        "OK:FILE_CREATED:{path}" 或 "ERROR:FILE_EXISTS"
    """
    # TODO:
    # safe = _safe_path(workspace, path)
    # if safe.exists(): return "ERROR:FILE_EXISTS"
    # safe.parent.mkdir(parents=True, exist_ok=True)
    # safe.write_text(content, encoding="utf-8")
    # await audit_service.log(db, user_id, "create", str(safe), hitl_required=False)
    # return f"OK:FILE_CREATED:{path}"
    raise NotImplementedError


@agent.tool
async def file_update(ctx: RunContext[AgentDeps], path: str, content: str) -> str:
    """
    覆盖 workspace 内已有文件内容（不可逆操作，触发 HITL）。

    HITL 流程：
    1. 调用 hitl_manager.create() 注册挂起状态
    2. 抛出 HITLInterrupt（由 loop.py 捕获，返回 HITL 响应给前端）
    3. 用户审批后 resume_callback 被调用，执行实际写入

    Args:
        path:    相对于 workspace 的目标路径
        content: 新的文件内容

    Returns:
        "OK:FILE_UPDATED:{path}"（审批通过后执行）
        "CANCELLED:USER_REJECTED"（审批拒绝后返回）
        "ERROR:FILE_NOT_FOUND"
    """
    # TODO:
    # safe = _safe_path(workspace, path)
    # if not safe.exists(): return "ERROR:FILE_NOT_FOUND"
    #
    # request_id = f"hitl_{ctx.deps.session_id}_{int(time.time())}"
    # state = hitl_manager.create(request_id, session_id, action=f"Overwrite {path}", risk="medium")
    # raise HITLInterrupt(state, payload=[f"Overwrite content of '{path}'"], reason="File overwrite is irreversible.")
    raise NotImplementedError


@agent.tool
async def file_delete(ctx: RunContext[AgentDeps], path: str) -> str:
    """
    删除 workspace 内指定文件（不可逆操作，触发 HITL，风险等级 high）。

    Args:
        path: 相对于 workspace 的目标路径

    Returns:
        "OK:FILE_DELETED:{path}"（审批通过后执行）
        "CANCELLED:USER_REJECTED"
        "ERROR:FILE_NOT_FOUND"
    """
    # TODO: 类似 file_update，HITL risk="high"
    raise NotImplementedError


@agent.tool
async def batch_rename(
    ctx: RunContext[AgentDeps],
    directory: str,
    pattern: str,
    replacement: str,
) -> str:
    """
    批量重命名 workspace 内某目录下符合 pattern 的文件（regex 支持）。
    先执行 Dry Run（仅预览，不实际执行），将预览结果返回给 LLM，
    LLM 向用户展示后，再次调用时通过 HITL 确认执行。

    Args:
        directory:   相对于 workspace 的目标目录
        pattern:     正则表达式匹配模式（匹配文件名）
        replacement: 替换字符串（支持 regex 捕获组，如 r'\1_renamed'）

    Returns:
        JSON 字符串，格式：
        {
          "dry_run": true,
          "preview": [{"original": str, "renamed": str}],
          "count": int
        }
        实际执行后返回：{"dry_run": false, "renamed": [...], "count": int}
    """
    # TODO:
    # 1. Dry run：扫描目录，对每个文件名 apply regex，生成 preview 列表
    # 2. 返回 preview（不执行）
    # 3. LLM 展示给用户，用户通过自然语言确认 → 触发 HITL
    # 4. HITL 通过后执行实际重命名
    raise NotImplementedError
