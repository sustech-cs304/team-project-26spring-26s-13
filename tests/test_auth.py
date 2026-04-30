"""
tests/test_auth.py
Tests for /api/auth/* endpoints: register, login, logout.
"""

from httpx import AsyncClient

from tests.conftest import SAMPLE_USER


# ── Register ──────────────────────────────────────────────────────────────────

async def test_register_success(async_client: AsyncClient):
    """POST /api/auth/register with valid data → 201 + token."""
    resp = await async_client.post("/api/auth/register", json=SAMPLE_USER)
    assert resp.status_code == 201
    data = resp.json()
    assert "token" in data
    assert data["display_name"] == SAMPLE_USER["display_name"]
    assert data["major"] == SAMPLE_USER["major"]
    # user_id must be returned and non-empty
    assert data.get("user_id")


async def test_register_missing_field(async_client: AsyncClient):
    """POST /api/auth/register without required field → 422 Unprocessable Entity."""
    resp = await async_client.post(
        "/api/auth/register",
        json={"username": "nopassword", "display_name": "X", "major": "CS"},
    )
    assert resp.status_code == 422


async def test_register_short_password(async_client: AsyncClient):
    """POST /api/auth/register with a too-short password → 422."""
    resp = await async_client.post(
        "/api/auth/register",
        json={**SAMPLE_USER, "password": "123"},
    )
    assert resp.status_code == 422


async def test_register_short_username(async_client: AsyncClient):
    """POST /api/auth/register with a too-short username (< 3 chars) → 422."""
    resp = await async_client.post(
        "/api/auth/register",
        json={**SAMPLE_USER, "username": "ab"},
    )
    assert resp.status_code == 422


async def test_register_duplicate_username(async_client: AsyncClient):
    """Registering the same username twice → 400 Bad Request."""
    await async_client.post("/api/auth/register", json=SAMPLE_USER)
    resp = await async_client.post("/api/auth/register", json=SAMPLE_USER)
    assert resp.status_code == 400
    assert "already" in resp.json()["detail"].lower()


# ── Login ─────────────────────────────────────────────────────────────────────

async def test_login_success(async_client: AsyncClient, registered_user: dict):
    """POST /api/auth/login with correct credentials → 200 + token."""
    resp = await async_client.post(
        "/api/auth/login",
        json={"username": SAMPLE_USER["username"], "password": SAMPLE_USER["password"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["display_name"] == SAMPLE_USER["display_name"]


async def test_login_wrong_password(async_client: AsyncClient, registered_user: dict):
    """POST /api/auth/login with wrong password → 401 Unauthorized."""
    resp = await async_client.post(
        "/api/auth/login",
        json={"username": SAMPLE_USER["username"], "password": "wrongpassword"},
    )
    assert resp.status_code == 401


async def test_login_nonexistent_user(async_client: AsyncClient):
    """POST /api/auth/login for a user that doesn't exist → 401 Unauthorized."""
    resp = await async_client.post(
        "/api/auth/login",
        json={"username": "ghost", "password": "ghostpass"},
    )
    assert resp.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────

async def test_logout(async_client: AsyncClient, auth_headers: dict):
    """POST /api/auth/logout → 204 No Content (stateless JWT)."""
    resp = await async_client.post("/api/auth/logout", headers=auth_headers)
    assert resp.status_code == 204
