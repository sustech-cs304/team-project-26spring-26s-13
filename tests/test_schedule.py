"""
tests/test_schedule.py
Tests for /api/schedule/refresh endpoint.
The CAS scraper and Blackboard crawler are mocked to avoid real network calls.
"""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

# ── POST /api/schedule/refresh ────────────────────────────────────────────────


async def test_refresh_schedule_unauthenticated(async_client: AsyncClient):
    """POST /api/schedule/refresh without token → 401/403."""
    resp = await async_client.post("/api/schedule/refresh")
    assert resp.status_code in (401, 403)


async def test_refresh_schedule_success(async_client: AsyncClient, auth_headers: dict):
    """POST /api/schedule/refresh with mocked service → 200 with ScheduleData."""
    fake_schedule = {
        "events": [],
        "conflicts": [],
    }
    with patch(
        "backend.services.schedule_service.refresh",
        new_callable=AsyncMock,
        return_value=fake_schedule,
    ):
        resp = await async_client.post("/api/schedule/refresh", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert "conflicts" in data


async def test_refresh_schedule_cas_fail(async_client: AsyncClient, auth_headers: dict):
    """POST /api/schedule/refresh when CAS login fails → 424."""
    with patch(
        "backend.services.schedule_service.refresh",
        new_callable=AsyncMock,
        side_effect=PermissionError("CAS login failed"),
    ):
        resp = await async_client.post("/api/schedule/refresh", headers=auth_headers)
    assert resp.status_code == 424


async def test_refresh_schedule_service_unavailable(
    async_client: AsyncClient, auth_headers: dict
):
    """POST /api/schedule/refresh when upstream service is down → 503."""
    with patch(
        "backend.services.schedule_service.refresh",
        new_callable=AsyncMock,
        side_effect=ConnectionError("Blackboard unreachable"),
    ):
        resp = await async_client.post("/api/schedule/refresh", headers=auth_headers)
    assert resp.status_code == 503
