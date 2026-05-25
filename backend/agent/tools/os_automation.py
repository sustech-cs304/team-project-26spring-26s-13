"""
backend/agent/tools/os_automation.py
OS 文件系统自动化工具。

安全约束：
  1. 所有操作严格限制在用户 workspace 内（settings.WORKSPACE_DIR / {user_id}/）
  2. UPDATE / DELETE / 批量 RENAME 触发 HITL（不可绕过）
  3. 所有写操作完成后写入 audit_logs 表
  4. 工具只用 pathlib / shutil API，不允许执行任意 shell 命令

HITL 复跑机制（关键）：
  - 首次调用：tool 检查 ctx.deps.hitl_approved 为 False → 抛 HITLInterrupt
              → loop.py 捕获 → 返回 HITL 请求给前端
  - 用户在前端批准后：loop.py 重新跑 agent，构造 deps 时把 hitl_approved 置为 True
  - LLM 收到 build_hitl_continuation_prompt 后会再次调用同一工具
  - 工具看到 ctx.deps.hitl_approved == True，跳过中断，直接执行实际操作
"""

import re
import shutil
from pathlib import Path

from pydantic_ai import RunContext

from backend.agent.core import AgentDeps, agent
from backend.agent.hitl import HITLPendingState, wait_for_user_interrupt
from backend.config import settings
from backend.services import audit_service

# ── Workspace 与路径安全 ───────────────────────────────────────────────────────


def _workspace_for_user(username: str) -> Path:
    root = Path(settings.WORKSPACE_DIR) / username
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _get_workspace(ctx: RunContext[AgentDeps]) -> Path:
    """返回当前用户的 workspace 绝对路径（以 username 命名），不存在则创建。"""
    return _workspace_for_user(ctx.deps.user.username)


def _safe_path(workspace: Path, target: str) -> Path:
    """
    把用户 / LLM 给的相对/绝对路径安全解析到 workspace 内。
    防止 ".." 路径穿越、绝对路径越权。

    Returns:
        解析后的绝对 Path，保证在 workspace 内
    Raises:
        PermissionError: 路径在 workspace 之外，或者为空字符串
    """
    target = (target or "").strip().replace("\\", "/").lstrip("/")
    if not target:
        raise PermissionError("Empty path is not allowed.")
    resolved = (workspace / target).resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError as e:
        raise PermissionError(f"Path '{target}' is outside the workspace.") from e
    return resolved


def _rel(workspace: Path, path: Path) -> str:
    """返回相对于 workspace 的展示用路径（POSIX 风格）。"""
    try:
        return path.relative_to(workspace).as_posix()
    except ValueError:
        return path.as_posix()


# ── 工具：列目录 ──────────────────────────────────────────────────────────────


@agent.tool
async def file_list(ctx: RunContext[AgentDeps], directory: str = ".") -> str:
    """
    列出 workspace 内某个目录的直接子项（文件 + 子目录）。
    只读操作，不触发 HITL。

    Args:
        directory: 相对于 workspace 的目录路径，"." 表示 workspace 根目录

    Returns:
        多行字符串，每行 "[DIR] name/" 或 "[FILE] name (sizeKB)"
        失败返回 "ERROR:DIR_NOT_FOUND" / "ERROR:OUT_OF_WORKSPACE"
    """
    workspace = _get_workspace(ctx)
    try:
        target = (
            _safe_path(workspace, directory or ".")
            if directory not in ("", ".")
            else workspace
        )
    except PermissionError:
        return "ERROR:OUT_OF_WORKSPACE"
    if not target.exists() or not target.is_dir():
        return "ERROR:DIR_NOT_FOUND"

    lines: list[str] = [
        f"[Workspace] {workspace}",
        f"[CWD] {_rel(workspace, target) or '.'}",
    ]
    entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    if not entries:
        lines.append("(empty)")
    for p in entries:
        if p.is_dir():
            lines.append(f"[DIR]  {p.name}/")
        else:
            kb = p.stat().st_size / 1024
            lines.append(f"[FILE] {p.name} ({kb:.1f} KB)")
    return "\n".join(lines)


# ── 工具：读文件 ──────────────────────────────────────────────────────────────


@agent.tool
async def file_read(ctx: RunContext[AgentDeps], path: str) -> str:
    """
    读取 workspace 内指定文本文件的内容。只读操作，不触发 HITL。

    Args:
        path: 相对于 workspace 的文件路径

    Returns:
        文件文本（截断至 settings.OS_READ_MAX_CHARS）；
        失败返回 "ERROR:FILE_NOT_FOUND" / "ERROR:NOT_A_FILE" /
        "ERROR:OUT_OF_WORKSPACE" / "ERROR:BINARY_FILE"
    """
    workspace = _get_workspace(ctx)
    try:
        safe = _safe_path(workspace, path)
    except PermissionError:
        return "ERROR:OUT_OF_WORKSPACE"
    if not safe.exists():
        return "ERROR:FILE_NOT_FOUND"
    if not safe.is_file():
        return "ERROR:NOT_A_FILE"
    try:
        text = safe.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "ERROR:BINARY_FILE"

    await audit_service.log(
        db=ctx.deps.db,
        user_id=ctx.deps.user.user_id,
        session_id=ctx.deps.session_id,
        action_type="read",
        target_path=str(safe),
        description=f"Read file '{_rel(workspace, safe)}'",
        hitl_required=False,
    )

    limit = settings.OS_READ_MAX_CHARS
    if len(text) > limit:
        return text[:limit] + f"\n\n[...truncated, total {len(text)} chars...]"
    return text


# ── 工具：创建文件 ────────────────────────────────────────────────────────────


@agent.tool
async def file_create(
    ctx: RunContext[AgentDeps],
    path: str,
    content: str = "",
) -> str:
    """
    在 workspace 内创建新文件（已存在则报错，**不覆盖**）。新增操作不触发 HITL。
    自动创建中间目录。

    Args:
        path:    相对于 workspace 的文件路径
        content: 文件文本内容（默认空字符串）

    Returns:
        "OK:FILE_CREATED:{relpath}" 成功
        "ERROR:FILE_EXISTS" 文件已存在
        "ERROR:OUT_OF_WORKSPACE" 路径越权
    """
    workspace = _get_workspace(ctx)
    try:
        safe = _safe_path(workspace, path)
    except PermissionError:
        return "ERROR:OUT_OF_WORKSPACE"
    if safe.exists():
        return "ERROR:FILE_EXISTS"
    safe.parent.mkdir(parents=True, exist_ok=True)
    safe.write_text(content, encoding="utf-8")

    rel = _rel(workspace, safe)
    await audit_service.log(
        db=ctx.deps.db,
        user_id=ctx.deps.user.user_id,
        session_id=ctx.deps.session_id,
        action_type="create",
        target_path=str(safe),
        description=f"Create file '{rel}' ({len(content)} chars)",
        hitl_required=False,
    )
    return f"OK:FILE_CREATED:{rel}"


# ── 工具：覆盖文件 — HITL medium ──────────────────────────────────────────────


@agent.tool
async def file_update(
    ctx: RunContext[AgentDeps],
    path: str,
    content: str,
) -> str:
    """
    覆盖 workspace 内已有文件的全部内容。**不可逆**，仅当文件存在时触发 HITL（risk=medium）。

    调用前：若不确定文件是否存在，先 `file_list(".")`；
    path 必须与用户指定的文件名一致。

    Args:
        path:    相对于 workspace 的文件路径（必须已存在）
        content: 新的完整文件内容（用户要求的原文，不要擅自替换）

    Returns:
        批准并执行成功："OK:FILE_UPDATED:{relpath}"
        文件不存在："ERROR:FILE_NOT_FOUND"（不会弹 HITL，应列出目录并询问用户）
        其他错误："ERROR:OUT_OF_WORKSPACE"
    """
    workspace = _get_workspace(ctx)
    try:
        safe = _safe_path(workspace, path)
    except PermissionError:
        return "ERROR:OUT_OF_WORKSPACE"
    if not safe.exists() or not safe.is_file():
        entries = sorted(p.name for p in workspace.iterdir()) if workspace.exists() else []
        listing = ", ".join(entries) if entries else "(empty)"
        return f"ERROR:FILE_NOT_FOUND. Current workspace contents: [{listing}]. Do NOT call file_list again — report this to the user immediately."

    rel = _rel(workspace, safe)
    if not ctx.deps.hitl_approved:
        preview = content if len(content) <= 120 else content[:120] + "..."
        wait_for_user_interrupt(
            session_id=ctx.deps.session_id,
            action=f"Overwrite file '{rel}'",
            risk="medium",
            payload=[
                f"Overwrite '{rel}' with {len(content)} chars",
                f"New content preview: {preview!r}",
            ],
            reason="文件覆盖是不可逆操作，需要您的确认。",
            tool_name="file_update",
            tool_args={"path": path, "content": content},
        )

    # 只有 HITL 批准后才会到达这里
    safe.write_text(content, encoding="utf-8")
    await audit_service.log(
        db=ctx.deps.db,
        user_id=ctx.deps.user.user_id,
        session_id=ctx.deps.session_id,
        action_type="update",
        target_path=str(safe),
        description=f"Overwrite file '{rel}' ({len(content)} chars)",
        hitl_required=True,
        hitl_approved=True,
    )
    return f"OK:FILE_UPDATED:{rel}"


# ── 工具：删除文件/目录 — HITL high ───────────────────────────────────────────


@agent.tool
async def file_delete(ctx: RunContext[AgentDeps], path: str) -> str:
    """
    删除 workspace 内的文件或目录（**目录会递归删除**）。
    **不可逆**，仅当目标存在时触发 HITL（risk=high）。

    调用前：若用户给出的文件名不确定，先 `file_list(".")` 确认存在；
    必须使用用户指定的路径，不要换成其他文件名。

    Args:
        path: 相对于 workspace 的目标路径（须与用户要求一致）

    Returns:
        批准并执行成功："OK:FILE_DELETED:{relpath}"
        目标不存在："ERROR:FILE_NOT_FOUND"（不会弹 HITL，应列出目录并询问用户）
        其他错误："ERROR:OUT_OF_WORKSPACE"
    """
    workspace = _get_workspace(ctx)
    try:
        safe = _safe_path(workspace, path)
    except PermissionError:
        return "ERROR:OUT_OF_WORKSPACE"
    if not safe.exists():
        # Return current listing so LLM can reply in one shot without extra file_list calls
        entries = sorted(p.name for p in workspace.iterdir()) if workspace.exists() else []
        listing = ", ".join(entries) if entries else "(empty)"
        return f"ERROR:FILE_NOT_FOUND. Current workspace contents: [{listing}]. Do NOT call file_list again — report this to the user immediately."

    rel = _rel(workspace, safe)
    kind = "directory" if safe.is_dir() else "file"

    if not ctx.deps.hitl_approved:
        wait_for_user_interrupt(
            session_id=ctx.deps.session_id,
            action=f"Delete {kind} '{rel}'",
            risk="high",
            payload=[
                f"Delete {kind} '{rel}'"
                + (" and ALL its contents" if kind == "directory" else "")
            ],
            reason=f"删除{kind}不可恢复，需要您的确认。",
            tool_name="file_delete",
            tool_args={"path": path},
        )

    if safe.is_dir():
        shutil.rmtree(safe)
    else:
        safe.unlink()

    await audit_service.log(
        db=ctx.deps.db,
        user_id=ctx.deps.user.user_id,
        session_id=ctx.deps.session_id,
        action_type="delete",
        target_path=str(safe),
        description=f"Delete {kind} '{rel}'",
        hitl_required=True,
        hitl_approved=True,
    )
    return f"OK:FILE_DELETED:{rel}"


# ── 工具：批量重命名 — Dry-run + HITL high ────────────────────────────────────


@agent.tool
async def batch_rename(
    ctx: RunContext[AgentDeps],
    directory: str,
    pattern: str,
    replacement: str,
) -> str:
    """
    批量重命名 workspace 内某目录下文件名匹配 pattern 的文件（正则）。

    工作模式：
      - 首次调用：触发 HITL，附带 dry-run 预览
      - 用户批准后再次调用相同参数：实际执行重命名

    Args:
        directory:   相对于 workspace 的目录路径
        pattern:     正则表达式（针对文件名）
        replacement: 替换字符串，支持 \\1 \\2 反向引用

    Returns:
        JSON 字符串：
          首次（无匹配）：{"dry_run": true, "preview": [], "count": 0, "note": "..."}
          执行后：{"dry_run": false, "renamed": [...], "skipped": [...], "count": N}
        失败：
          "ERROR:DIR_NOT_FOUND" / "ERROR:OUT_OF_WORKSPACE" / "ERROR:BAD_REGEX:{msg}"
    """
    import json as _json

    workspace = _get_workspace(ctx)
    try:
        target_dir = _safe_path(workspace, directory)
    except PermissionError:
        return "ERROR:OUT_OF_WORKSPACE"
    if not target_dir.exists() or not target_dir.is_dir():
        return "ERROR:DIR_NOT_FOUND"

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"ERROR:BAD_REGEX:{e}"

    # 扫出 dry-run preview
    preview: list[dict] = []
    for p in sorted(target_dir.iterdir()):
        if not p.is_file():
            continue
        if not regex.search(p.name):
            continue
        new_name = regex.sub(replacement, p.name)
        if new_name == p.name:
            continue
        preview.append({"original": p.name, "renamed": new_name})

    rel_dir = _rel(workspace, target_dir) or "."

    if not preview:
        return _json.dumps(
            {"dry_run": True, "preview": [], "count": 0, "note": "No files matched."},
            ensure_ascii=False,
        )

    # 首次调用：抛 HITL，并把 preview 通过 payload 透出
    if not ctx.deps.hitl_approved:
        wait_for_user_interrupt(
            session_id=ctx.deps.session_id,
            action=f"Batch rename {len(preview)} files in '{rel_dir}'",
            risk="high",
            payload=[f"{item['original']}  ->  {item['renamed']}" for item in preview],
            reason=f"批量重命名将影响 {len(preview)} 个文件，需要您的确认。",
            tool_name="batch_rename",
            tool_args={
                "directory": directory,
                "pattern": pattern,
                "replacement": replacement,
                "preview": preview,
            },
        )

    # 批准后真正执行
    renamed: list[dict] = []
    skipped: list[dict] = []
    for item in preview:
        src = target_dir / item["original"]
        dst = target_dir / item["renamed"]
        if dst.exists():
            skipped.append({**item, "reason": "TARGET_EXISTS"})
            continue
        try:
            src.rename(dst)
            renamed.append(item)
        except OSError as e:
            skipped.append({**item, "reason": str(e)})

    await audit_service.log(
        db=ctx.deps.db,
        user_id=ctx.deps.user.user_id,
        session_id=ctx.deps.session_id,
        action_type="rename",
        target_path=str(target_dir),
        description=(
            f"Batch rename in '{rel_dir}': pattern={pattern!r} -> {replacement!r}, "
            f"renamed={len(renamed)}, skipped={len(skipped)}"
        ),
        hitl_required=True,
        hitl_approved=True,
    )

    return _json.dumps(
        {
            "dry_run": False,
            "renamed": renamed,
            "skipped": skipped,
            "count": len(renamed),
        },
        ensure_ascii=False,
    )


async def execute_approved_hitl_operation(
    deps: AgentDeps, state: HITLPendingState
) -> str:
    """
    用户 HITL 批准后确定性执行已登记的工具参数，避免 LLM 二次改写 content。
    """
    workspace = _workspace_for_user(deps.user.username)
    name = state.tool_name
    args = state.tool_args or {}

    if name == "file_update":
        path = str(args.get("path", ""))
        content = str(args.get("content", ""))
        safe = _safe_path(workspace, path)
        if not safe.exists() or not safe.is_file():
            return f"ERROR:FILE_NOT_FOUND ({path})"
        rel = _rel(workspace, safe)
        safe.write_text(content, encoding="utf-8")
        await audit_service.log(
            db=deps.db,
            user_id=deps.user.user_id,
            session_id=deps.session_id,
            action_type="update",
            target_path=str(safe),
            description=f"Overwrite file '{rel}' ({len(content)} chars, HITL approved)",
            hitl_required=True,
            hitl_approved=True,
        )
        preview = content if len(content) <= 80 else content[:80] + "..."
        return (
            f"已覆盖 workspace 文件 `{rel}`（{len(content)} 字符）。"
            f"内容预览：{preview!r}"
        )

    if name == "file_delete":
        path = str(args.get("path", ""))
        safe = _safe_path(workspace, path)
        if not safe.exists():
            return f"ERROR:FILE_NOT_FOUND ({path})"
        rel = _rel(workspace, safe)
        kind = "directory" if safe.is_dir() else "file"
        if safe.is_dir():
            shutil.rmtree(safe)
        else:
            safe.unlink()
        await audit_service.log(
            db=deps.db,
            user_id=deps.user.user_id,
            session_id=deps.session_id,
            action_type="delete",
            target_path=str(safe),
            description=f"Delete {kind} '{rel}' (HITL approved)",
            hitl_required=True,
            hitl_approved=True,
        )
        return f"已删除 workspace 中的 {kind} `{rel}`。"

    if name == "batch_rename":
        import json as _json

        directory = str(args.get("directory", "."))
        preview = list(args.get("preview") or [])
        target_dir = _safe_path(workspace, directory)
        if not target_dir.exists() or not target_dir.is_dir():
            return f"ERROR:DIR_NOT_FOUND ({directory})"
        renamed: list[dict] = []
        skipped: list[dict] = []
        for item in preview:
            src = target_dir / item["original"]
            dst = target_dir / item["renamed"]
            if dst.exists():
                skipped.append({**item, "reason": "TARGET_EXISTS"})
                continue
            try:
                src.rename(dst)
                renamed.append(item)
            except OSError as e:
                skipped.append({**item, "reason": str(e)})
        rel_dir = _rel(workspace, target_dir) or "."
        await audit_service.log(
            db=deps.db,
            user_id=deps.user.user_id,
            session_id=deps.session_id,
            action_type="rename",
            target_path=str(target_dir),
            description=f"Batch rename in '{rel_dir}', renamed={len(renamed)}",
            hitl_required=True,
            hitl_approved=True,
        )
        return _json.dumps(
            {
                "dry_run": False,
                "renamed": renamed,
                "skipped": skipped,
                "count": len(renamed),
            },
            ensure_ascii=False,
        )

    return f"ERROR:UNSUPPORTED_HITL_TOOL ({name})"
