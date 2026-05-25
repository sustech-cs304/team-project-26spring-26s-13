"""
tests/test_materials.py
Tests for /api/materials/* endpoints: list, upload, delete.
Auth-guard and permission tests use real DB operations.
"""

import io
import uuid

from httpx import AsyncClient

from tests.conftest import TestSessionLocal

# ── GET /api/materials ────────────────────────────────────────────────────────


async def test_list_materials_empty(async_client: AsyncClient, auth_headers: dict):
    """Fresh user should have an empty materials list."""
    resp = await async_client.get("/api/materials", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_materials_unauthenticated(async_client: AsyncClient):
    """GET /api/materials without token → 401/403."""
    resp = await async_client.get("/api/materials")
    assert resp.status_code in (401, 403)


# ── POST /api/materials/upload ────────────────────────────────────────────────


async def test_upload_material_unauthenticated(async_client: AsyncClient):
    """Upload without token → 401/403."""
    resp = await async_client.post(
        "/api/materials/upload",
        files={"file": ("x.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
    )
    assert resp.status_code in (401, 403)


# ── DELETE /api/materials/{file_id} ──────────────────────────────────────────


async def test_delete_material_unauthenticated(async_client: AsyncClient):
    """DELETE without token → 401/403."""
    resp = await async_client.delete(f"/api/materials/{uuid.uuid4()}")
    assert resp.status_code in (401, 403)


async def test_delete_material_not_found(async_client: AsyncClient, auth_headers: dict):
    """DELETE a non-existent file_id → 404."""
    resp = await async_client.delete(
        f"/api/materials/{uuid.uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404


# ── POST /api/materials/sync-blackboard ───────────────────────────────────────


async def test_sync_blackboard_materials_unauthenticated(async_client: AsyncClient):
    """POST /api/materials/sync-blackboard without token → 401/403."""
    resp = await async_client.post("/api/materials/sync-blackboard")
    assert resp.status_code in (401, 403)
