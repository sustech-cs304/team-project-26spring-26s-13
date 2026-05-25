"""Tests for deterministic HITL-approved OS operations."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from backend.agent.hitl import HITLPendingState
from backend.agent.tools.os_automation import execute_approved_hitl_operation


@pytest.mark.asyncio
async def test_execute_file_update_writes_exact_content(tmp_path, monkeypatch) -> None:
    user_id = "test-user-hitl"
    workspace = tmp_path / user_id
    workspace.mkdir()
    target = workspace / "报告.txt"
    target.write_text("old", encoding="utf-8")

    monkeypatch.setattr(
        "backend.agent.tools.os_automation.settings.WORKSPACE_DIR",
        str(tmp_path),
    )

    deps = MagicMock()
    deps.user.user_id = user_id
    deps.session_id = "sess-1"
    deps.db = AsyncMock()

    state = HITLPendingState(
        request_id="hitl_test",
        session_id="sess-1",
        action="Overwrite",
        risk="medium",
        tool_name="file_update",
        tool_args={"path": "报告.txt", "content": "456789"},
    )

    result = await execute_approved_hitl_operation(deps, state)
    assert "456789" in result
    assert target.read_text(encoding="utf-8") == "456789"
