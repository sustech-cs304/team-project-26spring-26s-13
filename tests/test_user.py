"""
tests/test_user.py
Tests for /api/user/* endpoints: get profile, update profile.
All endpoints require JWT authentication.
"""

from httpx import AsyncClient

from tests.conftest import SAMPLE_USER


# ── GET /api/user/profile ─────────────────────────────────────────────────────

async def test_get_profile_success(async_client: AsyncClient, auth_headers: dict):
    """Authenticated GET /api/user/profile → 200 with correct user data."""
    resp = await async_client.get("/api/user/profile", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == SAMPLE_USER["display_name"]
    assert data["major"] == SAMPLE_USER["major"]
    assert "user_id" in data
    # Sensitive fields must NOT be present
    assert "password_hash" not in data
    assert "cas_password_encrypted" not in data


async def test_get_profile_unauthenticated(async_client: AsyncClient):
    """GET /api/user/profile without a token → 401/403."""
    resp = await async_client.get("/api/user/profile")
    assert resp.status_code in (401, 403)


async def test_get_profile_invalid_token(async_client: AsyncClient):
    """GET /api/user/profile with a bogus token → 401 Unauthorized."""
    resp = await async_client.get(
        "/api/user/profile",
        headers={"Authorization": "Bearer totally.invalid.token"},
    )
    assert resp.status_code == 401


# ── PUT /api/user/profile ─────────────────────────────────────────────────────

async def test_update_profile_display_name(async_client: AsyncClient, auth_headers: dict):
    """PUT /api/user/profile updating display_name → 200 with new name."""
    resp = await async_client.put(
        "/api/user/profile",
        headers=auth_headers,
        json={"display_name": "Updated Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Updated Name"


async def test_update_profile_major(async_client: AsyncClient, auth_headers: dict):
    """PUT /api/user/profile updating major → 200 with new major."""
    resp = await async_client.put(
        "/api/user/profile",
        headers=auth_headers,
        json={"major": "Data Science"},
    )
    assert resp.status_code == 200
    assert resp.json()["major"] == "Data Science"


async def test_update_profile_persists(async_client: AsyncClient, auth_headers: dict):
    """Profile changes should persist: GET after PUT returns updated values."""
    await async_client.put(
        "/api/user/profile",
        headers=auth_headers,
        json={"display_name": "Persistent Name", "major": "Physics"},
    )
    get_resp = await async_client.get("/api/user/profile", headers=auth_headers)
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["display_name"] == "Persistent Name"
    assert data["major"] == "Physics"


async def test_update_profile_unauthenticated(async_client: AsyncClient):
    """PUT /api/user/profile without token → 401/403."""
    resp = await async_client.put("/api/user/profile", json={"display_name": "X"})
    assert resp.status_code in (401, 403)
