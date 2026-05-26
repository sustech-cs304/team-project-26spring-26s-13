"""
tests/test_schedule.py
Tests for /api/schedule/refresh endpoint (auth guard).
"""

from httpx import AsyncClient


async def test_refresh_schedule_unauthenticated(async_client: AsyncClient):
    """POST /api/schedule/refresh without token → 401/403."""
    resp = await async_client.post("/api/schedule/refresh")
    assert resp.status_code in (401, 403)
