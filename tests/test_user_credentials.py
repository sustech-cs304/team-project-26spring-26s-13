"""
tests/test_user_credentials.py
Tests for PUT /api/user/credentials.
Credentials (CAS password, LLM API key) are Fernet-encrypted on write;
we only verify the HTTP contract, not the decrypted values.
"""

from httpx import AsyncClient


# ── PUT /api/user/credentials ─────────────────────────────────────────────────

async def test_update_credentials_unauthenticated(async_client: AsyncClient):
    """PUT /api/user/credentials without a token → 401/403."""
    resp = await async_client.put("/api/user/credentials", json={})
    assert resp.status_code in (401, 403)


async def test_update_credentials_invalid_token(async_client: AsyncClient):
    """Bogus Bearer token → 401."""
    resp = await async_client.put(
        "/api/user/credentials",
        headers={"Authorization": "Bearer totally.invalid.token"},
        json={"cas_account": "student"},
    )
    assert resp.status_code == 401


async def test_update_credentials_empty_body(async_client: AsyncClient, auth_headers: dict):
    """Empty JSON body (all fields None) should be a no-op → 204."""
    resp = await async_client.put("/api/user/credentials", headers=auth_headers, json={})
    assert resp.status_code == 204


async def test_update_credentials_cas_account_only(async_client: AsyncClient, auth_headers: dict):
    """Update cas_account only → 204 No Content."""
    resp = await async_client.put(
        "/api/user/credentials",
        headers=auth_headers,
        json={"cas_account": "12345678@mail.sustech.edu.cn"},
    )
    assert resp.status_code == 204


async def test_update_credentials_cas_password(async_client: AsyncClient, auth_headers: dict):
    """Update CAS account + password → 204; password is stored encrypted."""
    resp = await async_client.put(
        "/api/user/credentials",
        headers=auth_headers,
        json={
            "cas_account": "teststu",
            "cas_password": "myCasSecretP@ss",
        },
    )
    assert resp.status_code == 204


async def test_update_credentials_llm_api_key(async_client: AsyncClient, auth_headers: dict):
    """Update LLM API key only → 204."""
    resp = await async_client.put(
        "/api/user/credentials",
        headers=auth_headers,
        json={"llm_api_key": "sk-deepseek-test-key-abc123"},
    )
    assert resp.status_code == 204


async def test_update_credentials_all_fields(async_client: AsyncClient, auth_headers: dict):
    """Update all credential fields at once → 204."""
    resp = await async_client.put(
        "/api/user/credentials",
        headers=auth_headers,
        json={
            "cas_account": "stuXXXX",
            "cas_password": "correct_horse_battery",
            "llm_api_key": "sk-deepseek-prod-key",
        },
    )
    assert resp.status_code == 204


async def test_update_credentials_then_profile_unchanged(
    async_client: AsyncClient, auth_headers: dict
):
    """Updating credentials must not alter display_name or major."""
    await async_client.put(
        "/api/user/credentials",
        headers=auth_headers,
        json={"cas_account": "newaccount", "cas_password": "newpass"},
    )
    profile_resp = await async_client.get("/api/user/profile", headers=auth_headers)
    assert profile_resp.status_code == 200
    profile = profile_resp.json()
    assert profile["display_name"] == "Test User"
    assert profile["major"] == "Computer Science"
