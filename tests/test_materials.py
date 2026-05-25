"""
tests/test_materials.py
Tests for /api/materials/* endpoints: list, upload, delete.
Upload tests mock the heavy vectorization service to avoid real file I/O
and ChromaDB calls during unit testing.
"""

import io
from types import SimpleNamespace
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


# ── POST /api/materials/sync-blackboard ───────────────────────────────────────


async def test_sync_blackboard_materials_success(
    async_client: AsyncClient, auth_headers: dict
):
    fake_info = _fake_material_info("lecture3.pdf")
    with patch(
        "backend.services.material_service.sync_blackboard_materials",
        new_callable=AsyncMock,
        return_value=[fake_info],
    ) as mocked:
        resp = await async_client.post(
            "/api/materials/sync-blackboard?course_keyword=软件工程&keyword=lecture3&limit=20",
            headers=auth_headers,
        )
    assert resp.status_code == 201
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["file_name"] == "lecture3.pdf"
    mocked.assert_awaited_once()
    _args, kwargs = mocked.await_args
    assert kwargs["course_keyword"] == "软件工程"
    assert kwargs["keyword"] == "lecture3"
    assert kwargs["limit"] == 20


async def test_sync_blackboard_materials_permission_error(
    async_client: AsyncClient, auth_headers: dict
):
    with patch(
        "backend.services.material_service.sync_blackboard_materials",
        new_callable=AsyncMock,
        side_effect=PermissionError("CAS credentials not configured"),
    ):
        resp = await async_client.post(
            "/api/materials/sync-blackboard", headers=auth_headers
        )
    assert resp.status_code == 424


async def test_sync_blackboard_materials_value_error(
    async_client: AsyncClient, auth_headers: dict
):
    with patch(
        "backend.services.material_service.sync_blackboard_materials",
        new_callable=AsyncMock,
        side_effect=ValueError("bad request"),
    ):
        resp = await async_client.post(
            "/api/materials/sync-blackboard", headers=auth_headers
        )
    assert resp.status_code == 400


async def test_sync_blackboard_materials_unauthenticated(async_client: AsyncClient):
    resp = await async_client.post("/api/materials/sync-blackboard")
    assert resp.status_code in (401, 403)


# ── Service: sync_blackboard_materials filtering ──────────────────────────────


async def test_service_sync_blackboard_materials_filters_course_and_keyword():
    import uuid

    from backend.services import material_service
    from backend.schemas.material import MaterialInfo
    from backend.services.schedule_service.fetch_bb import BlackboardMaterial

    class _FakeScalars:
        def __init__(self, items):
            self._items = list(items)

        def __iter__(self):
            return iter(self._items)

    class _FakeDb:
        async def scalars(self, _stmt):
            return _FakeScalars([])

    user = SimpleNamespace(
        user_id=uuid.uuid4(),
        cas_account="dummy",
        cas_password_encrypted="encrypted",
        llm_api_key_encrypted=None,
    )

    bb_items = [
        BlackboardMaterial(
            title="Lecture 3 - Requirements",
            course_id="CS304",
            course_name="软件工程",
            content_id="c1",
            file_name="lecture3-requirements.pdf",
            file_type="application/pdf",
            source_url="https://bb.example/x",
            download_url="https://bb.example/d",
            file_bytes=b"%PDF-1.4 ...",
        ),
        BlackboardMaterial(
            title="Lecture 2 - Process",
            course_id="CS304",
            course_name="软件工程",
            content_id="c2",
            file_name="lecture2-process.pdf",
            file_type="application/pdf",
            source_url="https://bb.example/x2",
            download_url="https://bb.example/d2",
            file_bytes=b"%PDF-1.4 ...",
        ),
        BlackboardMaterial(
            title="Lecture 3 - Something Else",
            course_id="CS305",
            course_name="其他课程",
            content_id="c3",
            file_name="lecture3-other.pdf",
            file_type="application/pdf",
            source_url="https://bb.example/y",
            download_url="https://bb.example/d3",
            file_bytes=b"%PDF-1.4 ...",
        ),
    ]

    fake_info = MaterialInfo.model_validate(
        _fake_material_info("lecture3-requirements.pdf")
    )
    with patch(
        "backend.services.material_service.decrypt",
        return_value="pw",
    ), patch(
        "backend.services.material_service.fetch_blackboard_course_materials",
        new_callable=AsyncMock,
        return_value=(bb_items, []),
    ), patch(
        "backend.services.material_service._create_material_from_bytes",
        new_callable=AsyncMock,
        return_value=fake_info,
    ) as created:
        synced = await material_service.sync_blackboard_materials(
            _FakeDb(),
            user,
            course_keyword="软件工程",
            keyword="lecture3",
            limit=None,
        )
    assert len(synced) == 1
    assert synced[0].file_name == "lecture3-requirements.pdf"
    created.assert_awaited_once()
