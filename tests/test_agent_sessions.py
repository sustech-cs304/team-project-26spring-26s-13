"""
tests/test_agent_sessions.py
Tests for /api/agent/* endpoints:
  - GET  /api/agent/sessions
  - GET  /api/agent/sessions/{id}
  - DELETE /api/agent/sessions/{id}
  - POST /api/agent/run (HTTP contract only; run_agent is mocked)

Sessions are seeded directly via the test DB to avoid real LLM calls.
If the agent router is not registered (pydantic_ai unavailable), the
endpoints return 404 and the tests fail loudly — install pydantic_ai.
"""

import datetime
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import TestSessionLocal, SAMPLE_USER


# ── Fixture: seed a ChatSession row for the registered user ──────────────────

@pytest_asyncio.fixture
async def sample_session(registered_user: dict) -> str:
    """Insert a ChatSession for the registered user and return the session_id."""
    from backend.database.postgres import ChatSession
    import uuid as _uuid

    session_id = f"sess_test_{uuid.uuid4().hex[:8]}"
    user_id = _uuid.UUID(registered_user["user_id"])  # must be uuid.UUID for SQLite binding

    async with TestSessionLocal() as db:
        sess = ChatSession(
            session_id=session_id,
            user_id=user_id,
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow(),
        )
        db.add(sess)
        await db.commit()

    return session_id


# ── GET /api/agent/sessions ───────────────────────────────────────────────────

async def test_list_sessions_unauthenticated(async_client: AsyncClient):
    """GET /api/agent/sessions without token → 401/403."""
    resp = await async_client.get("/api/agent/sessions")
    assert resp.status_code in (401, 403)


async def test_list_sessions_empty_for_new_user(
    async_client: AsyncClient, auth_headers: dict
):
    """Fresh user has no chat sessions → empty list."""
    resp = await async_client.get("/api/agent/sessions", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_sessions_returns_seeded_session(
    async_client: AsyncClient, auth_headers: dict, sample_session: str
):
    """After seeding a session it must appear in the listing."""
    resp = await async_client.get("/api/agent/sessions", headers=auth_headers)
    assert resp.status_code == 200
    ids = [s["session_id"] for s in resp.json()]
    assert sample_session in ids


# ── GET /api/agent/sessions/{session_id} ─────────────────────────────────────

async def test_get_session_not_found(async_client: AsyncClient, auth_headers: dict):
    """GET a non-existent session → 404."""
    resp = await async_client.get(
        "/api/agent/sessions/nonexistent-session-id", headers=auth_headers
    )
    assert resp.status_code == 404


async def test_get_session_success(
    async_client: AsyncClient, auth_headers: dict, sample_session: str
):
    """GET an existing session → 200 with correct structure."""
    resp = await async_client.get(
        f"/api/agent/sessions/{sample_session}", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sample_session
    assert "messages" in data
    assert "title" in data


async def test_get_session_forbidden_for_other_user(async_client: AsyncClient):
    """Session owned by user A must be inaccessible to user B → 403."""
    from backend.database.postgres import ChatSession
    import uuid as _uuid

    user_a = {
        "username": "usera_sess",
        "password": "passwordA1",
        "display_name": "User A",
        "major": "CS",
    }
    user_b = {
        "username": "userb_sess",
        "password": "passwordB1",
        "display_name": "User B",
        "major": "EE",
    }

    reg_a = await async_client.post("/api/auth/register", json=user_a)
    reg_b = await async_client.post("/api/auth/register", json=user_b)
    assert reg_a.status_code == 201
    assert reg_b.status_code == 201

    session_id = f"sess_usera_{uuid.uuid4().hex[:8]}"
    async with TestSessionLocal() as db:
        sess = ChatSession(
            session_id=session_id,
            user_id=_uuid.UUID(reg_a.json()["user_id"]),
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow(),
        )
        db.add(sess)
        await db.commit()

    token_b = reg_b.json()["token"]
    resp = await async_client.get(
        f"/api/agent/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403


# ── DELETE /api/agent/sessions/{session_id} ───────────────────────────────────

async def test_delete_session_not_found(async_client: AsyncClient, auth_headers: dict):
    """DELETE a non-existent session → 404."""
    resp = await async_client.delete(
        "/api/agent/sessions/nonexistent-delete-id", headers=auth_headers
    )
    assert resp.status_code == 404


async def test_delete_session_success(
    async_client: AsyncClient, auth_headers: dict, sample_session: str
):
    """DELETE an existing session → 204, then GET → 404."""
    del_resp = await async_client.delete(
        f"/api/agent/sessions/{sample_session}", headers=auth_headers
    )
    assert del_resp.status_code == 204

    get_resp = await async_client.get(
        f"/api/agent/sessions/{sample_session}", headers=auth_headers
    )
    assert get_resp.status_code == 404


async def test_delete_session_unauthenticated(async_client: AsyncClient):
    """DELETE without token → 401/403."""
    resp = await async_client.delete("/api/agent/sessions/any-id")
    assert resp.status_code in (401, 403)


async def test_delete_session_forbidden_for_other_user(async_client: AsyncClient):
    """DELETE a session owned by user A when authenticated as user B → 403."""
    from backend.database.postgres import ChatSession
    import uuid as _uuid

    user_a = {
        "username": "usera_del",
        "password": "passwordDel1",
        "display_name": "Del A",
        "major": "CS",
    }
    user_b = {
        "username": "userb_del",
        "password": "passwordDel2",
        "display_name": "Del B",
        "major": "EE",
    }

    reg_a = await async_client.post("/api/auth/register", json=user_a)
    reg_b = await async_client.post("/api/auth/register", json=user_b)
    assert reg_a.status_code == 201
    assert reg_b.status_code == 201

    session_id = f"sess_del_{uuid.uuid4().hex[:8]}"
    async with TestSessionLocal() as db:
        sess = ChatSession(
            session_id=session_id,
            user_id=_uuid.UUID(reg_a.json()["user_id"]),
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow(),
        )
        db.add(sess)
        await db.commit()

    token_b = reg_b.json()["token"]
    resp = await async_client.delete(
        f"/api/agent/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403


# ── POST /api/agent/run ───────────────────────────────────────────────────────

async def test_agent_run_unauthenticated(async_client: AsyncClient):
    """POST /api/agent/run without a token → 401/403."""
    resp = await async_client.post(
        "/api/agent/run",
        json={
            "user_id": str(uuid.uuid4()),
            "session_id": "sess_test",
            "message": "Hello",
        },
    )
    assert resp.status_code in (401, 403)


async def test_agent_run_user_id_mismatch(
    async_client: AsyncClient, auth_headers: dict, registered_user: dict
):
    """POST /api/agent/run where body.user_id ≠ token's user_id → 403."""
    resp = await async_client.post(
        "/api/agent/run",
        headers=auth_headers,
        json={
            "user_id": str(uuid.uuid4()),  # intentionally wrong
            "session_id": "sess_test",
            "message": "Hello agent",
        },
    )
    assert resp.status_code == 403


async def test_agent_run_success_with_mock(
    async_client: AsyncClient, auth_headers: dict, registered_user: dict
):
    """POST /api/agent/run with mocked run_agent → 200 + AgentResponse structure."""
    from datetime import timezone

    fake_response = {
        "session_id": "sess_mocked_001",
        "assistant_message": {
            "role": "assistant",
            "content": "Mocked reply",
            "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
        },
        "trace": [],
        "route": "chat",
        "ui_payload": {"schedule": None, "encyclopedia": None},
        "hitl_request": None,
        "error": None,
    }

    # AgentResponse is a Pydantic model; patch run_agent to return it
    from backend.schemas.agent import AgentResponse
    fake_agent_response = AgentResponse(**fake_response)

    with patch(
        "backend.api.agent.run_agent",
        new_callable=AsyncMock,
        return_value=fake_agent_response,
    ):
        resp = await async_client.post(
            "/api/agent/run",
            headers=auth_headers,
            json={
                "user_id": registered_user["user_id"],
                "session_id": "sess_mocked_001",
                "message": "Show me my schedule",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert "assistant_message" in data
    assert "trace" in data
    assert "route" in data
