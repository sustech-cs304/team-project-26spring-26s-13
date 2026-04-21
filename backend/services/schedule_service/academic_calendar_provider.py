from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

from backend.services.schedule_service.academic_calendar_extract import extract_calendar_text_from_pdf
from backend.services.schedule_service.academic_calendar_fetch import download_calendar_asset
from backend.services.schedule_service.academic_calendar_models import CalendarOverrides, CalendarPdfRef
from backend.services.schedule_service.academic_calendar_parse import parse_calendar_overrides
from backend.services.schedule_service.academic_calendar_source import discover_calendar_pdfs, is_calendar_asset_url
from backend.services.schedule_service.log_utils import logger


def _cache_dir() -> Path:
    root = Path(__file__).resolve().parents[3]
    return root / "temp" / "calendar_cache"


def _overrides_cache_path() -> Path:
    return _cache_dir() / "calendar_overrides.json"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _read_cached_overrides(path: Path, *, max_age: timedelta) -> CalendarOverrides | None:
    if not path.exists() or path.stat().st_size <= 0:
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    if _now_utc() - mtime > max_age:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cancel_days = {_parse_iso_date(x) for x in data.get("cancel_days", [])}
        cancel_days = {d for d in cancel_days if d is not None}
        move_rules = []
        for a, b in data.get("move_rules", []):
            da = _parse_iso_date(a)
            db = _parse_iso_date(b)
            if da and db:
                move_rules.append((da, db))
        return CalendarOverrides(
            cancel_days=set(cancel_days),
            move_rules=move_rules,
            week1_monday=_parse_iso_date(data.get("week1_monday") or ""),
            source_url=data.get("source_url"),
            source_pdf_url=data.get("source_pdf_url"),
            source_pdf_path=data.get("source_pdf_path"),
            extracted_pages=data.get("extracted_pages"),
        )
    except Exception:
        logger.exception("calendar.provider: failed to read cache path=%s", path)
        return None


def _write_cached_overrides(path: Path, overrides: CalendarOverrides) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(overrides)
    payload["cancel_days"] = sorted([d.isoformat() for d in overrides.cancel_days])
    payload["move_rules"] = [[a.isoformat(), b.isoformat()] for a, b in overrides.move_rules]
    payload["week1_monday"] = overrides.week1_monday.isoformat() if overrides.week1_monday else None
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_iso_date(s: str) -> date | None:
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None


def _pick_best_pdf(pdfs: list[CalendarPdfRef]) -> CalendarPdfRef:
    if not pdfs:
        raise ValueError("no calendar pdfs discovered")

    preferred = os.getenv("SUSTECH_CALENDAR_PDF_URL", "").strip()
    if preferred:
        return CalendarPdfRef(url=preferred, title="env")

    def score(p: CalendarPdfRef) -> tuple[int, int]:
        t = (p.title or "").lower()
        u = p.url.lower()
        s = 0
        if "校历" in t or "calendar" in t:
            s += 3
        if "academic-calendar" in u or "calendar" in u:
            s += 2
        if "pdf" in u:
            s += 1
        return (s, len(u))

    return sorted(pdfs, key=score, reverse=True)[0]


async def get_calendar_overrides(
    *,
    page_url: str | None = None,
    max_cache_age: timedelta = timedelta(days=7),
    force_refresh: bool = False,
) -> CalendarOverrides:
    cache_path = _overrides_cache_path()
    if not force_refresh:
        cached = _read_cached_overrides(cache_path, max_age=max_cache_age)
        if cached is not None:
            logger.info("calendar.provider: overrides_cache_hit path=%s", cache_path)
            return cached

    page_url = (page_url or os.getenv("SUSTECH_CALENDAR_PAGE_URL") or "https://sustech.edu.cn/zh/academic-calendar.html").strip()
    if not page_url:
        raise ValueError("page_url is required")

    if httpx is None:
        if is_calendar_asset_url(page_url):
            pdf_ref = CalendarPdfRef(url=page_url, title="direct")
        else:
            pdfs = await discover_calendar_pdfs(page_url=page_url, client=None)
            pdf_ref = _pick_best_pdf(pdfs)

        pdf_path = await download_calendar_asset(pdf_ref.url, client=None, force=force_refresh)
        extracted = await extract_calendar_text_from_pdf(pdf_path)
        overrides = parse_calendar_overrides(
            extracted.text,
            source_url=page_url,
            source_pdf_url=pdf_ref.url,
            source_pdf_path=str(pdf_path),
            extracted_pages=extracted.page_count,
        )
    else:
        async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(30.0), trust_env=False) as client:  # type: ignore[union-attr]
            if is_calendar_asset_url(page_url):
                pdf_ref = CalendarPdfRef(url=page_url, title="direct")
            else:
                pdfs = await discover_calendar_pdfs(page_url=page_url, client=client)
                pdf_ref = _pick_best_pdf(pdfs)

            pdf_path = await download_calendar_asset(pdf_ref.url, client=client, force=force_refresh)
            extracted = await extract_calendar_text_from_pdf(pdf_path)
            overrides = parse_calendar_overrides(
                extracted.text,
                source_url=page_url,
                source_pdf_url=pdf_ref.url,
                source_pdf_path=str(pdf_path),
                extracted_pages=extracted.page_count,
            )

    _write_cached_overrides(cache_path, overrides)
    logger.info("calendar.provider: overrides_cached path=%s", cache_path)
    return overrides
