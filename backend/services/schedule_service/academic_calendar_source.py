from __future__ import annotations

import re
from pathlib import Path
import urllib.request
from urllib.parse import urljoin, urlparse

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment]

from backend.services.schedule_service.academic_calendar_models import CalendarPdfRef
from backend.services.schedule_service.log_utils import logger


_PDF_RE = re.compile(r"""href\s*=\s*["']([^"']+?\.pdf(?:\?[^"']*)?)["']""", re.I)
_IMAGE_RE = re.compile(r"""href\s*=\s*["']([^"']+?\.(?:jpg|jpeg|png|webp)(?:\?[^"']*)?)["']""", re.I)


def is_calendar_asset_url(url: str) -> bool:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}


def _guess_media_type(url: str) -> str | None:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    return None


async def discover_calendar_pdfs(
    *,
    page_url: str,
    client: "httpx.AsyncClient | None" = None,
) -> list[CalendarPdfRef]:
    if not page_url:
        raise ValueError("page_url is required")

    own_client = client is None
    if own_client:
        if httpx is None:
            client = None
        else:
            client = httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(20.0), trust_env=False)  # type: ignore[union-attr]

    try:
        if client is not None:
            r = await client.get(page_url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-CN,zh;q=0.9"})
            r.raise_for_status()
            html = r.text or ""
        else:
            req = urllib.request.Request(
                page_url,
                headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-CN,zh;q=0.9"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
    finally:
        if own_client and client is not None and hasattr(client, "aclose"):
            await client.aclose()

    pdfs: list[CalendarPdfRef] = []

    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a"):
            href = a.get("href")
            if not href:
                continue
            if ".pdf" not in href.lower() and not any(ext in href.lower() for ext in (".jpg", ".jpeg", ".png", ".webp")):
                continue
            url = urljoin(page_url, href)
            title = (a.get_text(" ", strip=True) or "").strip() or None
            pdfs.append(CalendarPdfRef(url=url, title=title, media_type=_guess_media_type(url)))

    if not pdfs:
        for m in _PDF_RE.finditer(html):
            url = urljoin(page_url, m.group(1))
            pdfs.append(CalendarPdfRef(url=url, title=None, media_type=_guess_media_type(url)))
    if not pdfs:
        for m in _IMAGE_RE.finditer(html):
            url = urljoin(page_url, m.group(1))
            pdfs.append(CalendarPdfRef(url=url, title=None, media_type=_guess_media_type(url)))

    seen: set[str] = set()
    deduped: list[CalendarPdfRef] = []
    for p in pdfs:
        key = p.url.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(p)

    if not deduped:
        logger.warning("calendar.source: no pdf links found page_url=%s", page_url)
    else:
        logger.info("calendar.source: pdfs=%d page_url=%s", len(deduped), page_url)

    return deduped
