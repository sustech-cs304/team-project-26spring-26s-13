"""
backend/api/debug.py
Debug panel endpoints for Blackboard sync troubleshooting.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.deps import get_current_user
from backend.database.postgres import User

router = APIRouter(prefix="/api/debug", tags=["debug"])


class DebugDownloadRequest(BaseModel):
    url: str
    course_id: str = ""


class DebugDownloadResponse(BaseModel):
    url: str
    status: str
    status_code: int | None
    content_type: str | None
    content_length: int | None
    body_size: int
    hex_head: str
    elapsed_seconds: float | None
    error: str | None


@router.post("/bb/test-download", response_model=DebugDownloadResponse)
async def test_download(
    body: DebugDownloadRequest,
    _current_user: User = Depends(get_current_user),
) -> DebugDownloadResponse:
    import time
    import hashlib
    import httpx
    from backend.services.schedule_service.bb_auth import (
        _blackboard_authenticated_session,
    )

    start = time.monotonic()
    error_msg: str | None = None
    status_code: int | None = None
    ct: str | None = None
    cl: int | None = None
    body_size = 0
    hex_head = ""
    final_status = "ok"

    try:
        async with _blackboard_authenticated_session(
            cas_account=None,
            cas_password=None,
        ) as (client, _session_headers):
            response = await client.get(
                body.url,
                headers=_session_headers,
                timeout=30.0,
                follow_redirects=True,
            )
            status_code = response.status_code
            ct = response.headers.get("Content-Type", "")
            try:
                cl = int(response.headers.get("Content-Length", ""))
            except Exception:
                cl = None
            content = response.content
            body_size = len(content)
            if body_size > 0:
                hex_head = content[:64].hex()
            if status_code >= 400:
                final_status = f"http_{status_code}"
            if body_size > 0 and content[:128].lstrip()[:1] == b"<":
                snippet = content[:256].lower()
                if b"<html" in snippet or b"<!doctype" in snippet:
                    final_status = "html_body_not_file"
    except httpx.TimeoutException:
        error_msg = "timeout"
        final_status = "timeout"
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        final_status = "error"

    elapsed = time.monotonic() - start
    return DebugDownloadResponse(
        url=body.url,
        status=final_status,
        status_code=status_code,
        content_type=ct,
        content_length=cl,
        body_size=body_size,
        hex_head=hex_head,
        elapsed_seconds=round(elapsed, 3),
        error=error_msg,
    )


class DebugDumpRequest(BaseModel):
    course_id: str


@router.post("/bb/dump-collection")
async def dump_collection(
    body: DebugDumpRequest,
    _current_user: User = Depends(get_current_user),
):
    from pathlib import Path
    import httpx
    from backend.services.schedule_service.bb_auth import (
        _blackboard_authenticated_session,
    )
    from backend.services.schedule_service.bb_materials import _extract_course_name

    course_id = body.course_id.strip()
    if not course_id:
        raise HTTPException(status_code=400, detail="course_id required")

    page_url = (
        f"https://bb.sustech.edu.cn/webapps/blackboard/content/"
        f"listContent.jsp?course_id={course_id}&mode=reset"
    )

    async with _blackboard_authenticated_session(
        cas_account=None,
        cas_password=None,
    ) as (client, _session_headers):
        response = await client.get(page_url, headers=_session_headers, timeout=30.0)
        text = response.text

    course_name = _extract_course_name(text) or course_id
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in course_name)
    out_dir = Path(__file__).resolve().parents[2] / "temp" / "bb_dumps"
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{course_id}_{safe_name}.html"
    html_path.write_text(text, encoding="utf-8")

    from backend.services.schedule_service.bb_materials import (
        _extract_content_file_urls,
        _extract_cms_course_file_urls,
        _is_cms_course_path,
    )

    base_url = str(response.url)
    content_files = list(_extract_content_file_urls(text, base_url))
    cms_files = list(_extract_cms_course_file_urls(text, base_url))

    return {
        "course_id": course_id,
        "course_name": course_name,
        "html_path": str(html_path),
        "html_size": len(text),
        "content_file_urls": len(content_files),
        "cms_file_urls": len(cms_files),
        "sample_content": content_files[:5],
        "sample_cms": cms_files[:5],
    }


@router.get("/bb/failures")
async def list_failure_snapshots(
    _current_user: User = Depends(get_current_user),
):
    from pathlib import Path
    from backend.services.schedule_service.log_utils import _get_failure_dir

    snap_dir = _get_failure_dir()
    files = sorted(
        snap_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )[:50]
    result = []
    for fp in files:
        try:
            data = fp.read_text(encoding="utf-8")
            import json

            snap = json.loads(data)
            result.append(
                {
                    "file": fp.name,
                    "label": snap.get("label"),
                    "url": snap.get("url", "")[:120],
                    "status_code": snap.get("status_code"),
                    "timestamp": snap.get("timestamp_utc"),
                }
            )
        except Exception:
            result.append({"file": fp.name, "error": "parse_failed"})
    return {"count": len(result), "snapshots": result}


@router.get("/bb/failures/{filename}")
async def get_failure_snapshot(
    filename: str,
    _current_user: User = Depends(get_current_user),
):
    from pathlib import Path
    from backend.services.schedule_service.log_utils import _get_failure_dir

    filepath = _get_failure_dir() / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="snapshot not found")
    import json

    return json.loads(filepath.read_text(encoding="utf-8"))
