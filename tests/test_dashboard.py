"""
tests/test_dashboard.py
Tests for GET /api/dashboard/bootstrap.
"""

from httpx import AsyncClient

from tests.conftest import SAMPLE_USER


# ── GET /api/dashboard/bootstrap ─────────────────────────────────────────────

async def test_bootstrap_unauthenticated(async_client: AsyncClient):
    """GET /api/dashboard/bootstrap without token → 401/403."""
    resp = await async_client.get("/api/dashboard/bootstrap")
    assert resp.status_code in (401, 403)


async def test_bootstrap_success(async_client: AsyncClient, auth_headers: dict):
    """Authenticated GET /api/dashboard/bootstrap → 200 with all required fields."""
    resp = await async_client.get("/api/dashboard/bootstrap", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "user_profile" in data
    assert "chat_history" in data
    assert "materials" in data
    assert "local_schedule" in data


async def test_bootstrap_fresh_user_has_empty_collections(
    async_client: AsyncClient, auth_headers: dict
):
    """Brand-new user should have empty chat history, materials, and schedule."""
    resp = await async_client.get("/api/dashboard/bootstrap", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["chat_history"] == []
    assert data["materials"] == []
    assert data["local_schedule"]["events"] == []
    assert data["local_schedule"]["conflicts"] == []


async def test_bootstrap_user_profile_matches_registration(
    async_client: AsyncClient, auth_headers: dict, registered_user: dict
):
    """Profile returned in bootstrap must match the registered user's display_name and major."""
    resp = await async_client.get("/api/dashboard/bootstrap", headers=auth_headers)
    assert resp.status_code == 200
    profile = resp.json()["user_profile"]
    assert profile["display_name"] == SAMPLE_USER["display_name"]
    assert profile["major"] == SAMPLE_USER["major"]
    assert "user_id" in profile
    # Sensitive fields must be absent
    assert "password_hash" not in profile
    assert "cas_password_encrypted" not in profile


async def test_bootstrap_active_session_id_none_for_new_user(
    async_client: AsyncClient, auth_headers: dict
):
    """Brand-new user with no sessions should have active_session_id as null."""
    resp = await async_client.get("/api/dashboard/bootstrap", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["active_session_id"] is None


async def test_bootstrap_invalid_token(async_client: AsyncClient):
    """Bogus Bearer token → 401."""
    resp = await async_client.get(
        "/api/dashboard/bootstrap",
        headers={"Authorization": "Bearer totally.invalid.token"},
    )
    assert resp.status_code == 401
