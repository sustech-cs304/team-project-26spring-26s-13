"""
tests/test_materials.py
Tests for /api/materials/* endpoints: list, upload, delete.
Upload tests mock the heavy vectorization service to avoid real file I/O
and ChromaDB calls during unit testing.
"""

import io
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from tests.conftest import SAMPLE_USER

# ── Helper ────────────────────────────────────────────────────────────────────


def _fake_material_info(file_name: str = "test.pdf") -> dict:
    """Return a MaterialInfo-like dict for patching material_service."""
    import uuid
    from datetime import datetime, timezone

    return {
        "file_id": str(uuid.uuid4()),
        "file_name": file_name,
        "file_type": "application/pdf",
        "subject_type": "cs",
        "vectorized": False,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }


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


async def test_upload_material_success(async_client: AsyncClient, auth_headers: dict):
    """Upload a PDF → 201 with MaterialInfo. Vectorization is mocked."""
    fake_info = _fake_material_info("lecture.pdf")
    with patch(
        "backend.services.material_service.upload_and_vectorize",
        new_callable=AsyncMock,
        return_value=fake_info,
    ):
        resp = await async_client.post(
            "/api/materials/upload",
            headers=auth_headers,
            files={
                "file": (
                    "lecture.pdf",
                    io.BytesIO(b"%PDF fake content"),
                    "application/pdf",
                )
            },
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["file_name"] == "lecture.pdf"
    assert data["vectorized"] is False


async def test_upload_material_unsupported_type(
    async_client: AsyncClient, auth_headers: dict
):
    """Upload an unsupported file type → 400 Bad Request."""
    with patch(
        "backend.services.material_service.upload_and_vectorize",
        new_callable=AsyncMock,
        side_effect=ValueError("Unsupported file type"),
    ):
        resp = await async_client.post(
            "/api/materials/upload",
            headers=auth_headers,
            files={
                "file": (
                    "notes.exe",
                    io.BytesIO(b"MZ binary"),
                    "application/octet-stream",
                )
            },
        )
    assert resp.status_code == 400


async def test_upload_material_unauthenticated(async_client: AsyncClient):
    """Upload without token → 401/403."""
    resp = await async_client.post(
        "/api/materials/upload",
        files={"file": ("x.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
    )
    assert resp.status_code in (401, 403)


# ── DELETE /api/materials/{file_id} ──────────────────────────────────────────


async def test_delete_material_not_found(async_client: AsyncClient, auth_headers: dict):
    """DELETE a non-existent file_id → 404."""
    import uuid

    fake_id = str(uuid.uuid4())
    with patch(
        "backend.services.material_service.delete_material",
        new_callable=AsyncMock,
        side_effect=FileNotFoundError,
    ):
        resp = await async_client.delete(
            f"/api/materials/{fake_id}", headers=auth_headers
        )
    assert resp.status_code == 404


async def test_delete_material_forbidden(async_client: AsyncClient, auth_headers: dict):
    """DELETE a file belonging to another user → 403."""
    import uuid

    fake_id = str(uuid.uuid4())
    with patch(
        "backend.services.material_service.delete_material",
        new_callable=AsyncMock,
        side_effect=PermissionError,
    ):
        resp = await async_client.delete(
            f"/api/materials/{fake_id}", headers=auth_headers
        )
    assert resp.status_code == 403


async def test_delete_material_success(async_client: AsyncClient, auth_headers: dict):
    """DELETE an existing material → 204 No Content."""
    import uuid

    fake_id = str(uuid.uuid4())
    with patch(
        "backend.services.material_service.delete_material",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await async_client.delete(
            f"/api/materials/{fake_id}", headers=auth_headers
        )
    assert resp.status_code == 204
