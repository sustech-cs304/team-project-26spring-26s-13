from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

import httpx

from backend.services.schedule_service.constants import logger


def _cache_dir() -> Path:
    root = Path(__file__).resolve().parents[3]
    return root / "temp" / "calendar_cache"


def _safe_basename_from_url(url: str) -> str:
    p = urlparse(url)
    name = Path(p.path).name or "calendar.pdf"
    return name


def _cache_path_for_pdf(url: str) -> Path:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    base = _safe_basename_from_url(url)
    return _cache_dir() / f"{h}-{base}"


async def download_calendar_pdf(
    pdf_url: str,
    *,
    client: httpx.AsyncClient | None = None,
    force: bool = False,
) -> Path:
    if not pdf_url:
        raise ValueError("pdf_url is required")

    out = _cache_path_for_pdf(pdf_url)
    out.parent.mkdir(parents=True, exist_ok=True)

    if out.exists() and not force and out.stat().st_size > 0:
        logger.info("calendar.fetch: cache_hit path=%s url=%s", out, pdf_url)
        return out

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(30.0), trust_env=False)

    try:
        assert client is not None
        r = await client.get(pdf_url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-CN,zh;q=0.9"})
        r.raise_for_status()
        out.write_bytes(r.content)
    finally:
        if own_client and client is not None:
            await client.aclose()

    logger.info("calendar.fetch: downloaded bytes=%d path=%s url=%s", out.stat().st_size, out, pdf_url)
    return out


async def download_calendar_asset(
    asset_url: str,
    *,
    client: httpx.AsyncClient | None = None,
    force: bool = False,
) -> Path:
    return await download_calendar_pdf(asset_url, client=client, force=force)
