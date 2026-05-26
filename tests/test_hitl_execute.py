"""Tests for deterministic HITL-approved OS operations."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.core import AgentDeps
from backend.agent.hitl import HITLPendingState
from backend.agent.tools.os_automation import execute_approved_hitl_operation
from backend.database.postgres import User
from tests.conftest import TestSessionLocal


async def _make_real_user(username: str = "hitl_test_user") -> User:
    """Insert a real User row into the test DB and return the ORM object."""
    async with TestSessionLocal() as db:
        user = User(
            user_id=uuid.uuid4(),
            username=username,
            password_hash="fake_hash",
            display_name="HITL Tester",
            major="CS",
            working_dir=None,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


@pytest.mark.asyncio
async def test_execute_file_update_writes_exact_content(tmp_path) -> None:
    username = "hitl_test_user"
    workspace = tmp_path / username
    workspace.mkdir()
    target = workspace / "报告.txt"
    target.write_text("old", encoding="utf-8")

    from backend.config import settings

    original_ws = settings.WORKSPACE_DIR
    settings.WORKSPACE_DIR = str(tmp_path)
    try:
        user = await _make_real_user(username)
        async with TestSessionLocal() as db:
            deps = AgentDeps(
                db=db,
                user=user,
                session_id="sess-1",
                llm_api_key="test-key",
                cas_account=None,
                cas_password=None,
            )

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
    finally:
        settings.WORKSPACE_DIR = original_ws
