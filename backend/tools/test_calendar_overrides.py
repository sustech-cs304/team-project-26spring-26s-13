from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date
from pathlib import Path
import sys


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


sys.path.insert(0, str(_repo_root()))

from backend.services.schedule_service.academic_calendar_fetch import download_calendar_asset
from backend.services.schedule_service.academic_calendar_models import CalendarPdfRef
from backend.services.schedule_service.academic_calendar_source import discover_calendar_pdfs, is_calendar_asset_url
from backend.services.schedule_service.academic_calendar_provider import get_calendar_overrides


def _json_default(obj):
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(f"not json serializable: {type(obj)}")


def _pick_best_asset(pdfs: list[CalendarPdfRef]) -> CalendarPdfRef:
    if not pdfs:
        raise ValueError("no calendar assets discovered")

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



async def _run(page_url: str, *, force: bool) -> dict[str, object]:
    overrides = await get_calendar_overrides(page_url=page_url, force_refresh=force)
    payload = {
        "source_url": overrides.source_url,
        "source_pdf_path": overrides.source_pdf_path,
        "extracted_pages": overrides.extracted_pages,
        "week1_monday": overrides.week1_monday,
        "cancel_days_count": len(overrides.cancel_days),
        "cancel_days_head": sorted(list(overrides.cancel_days))[:20],
        "move_rules_count": len(overrides.move_rules),
        "move_rules": overrides.move_rules,
    }
    return payload


async def _fetch_only(url: str, *, force: bool) -> dict[str, object]:
    if is_calendar_asset_url(url):
        picked = CalendarPdfRef(url=url, title="direct", media_type=None)
        discovered = [picked]
    else:
        discovered = await discover_calendar_pdfs(page_url=url, client=None)
        picked = _pick_best_asset(discovered)

    path = await download_calendar_asset(picked.url, client=None, force=force)
    return {
        "input_url": url,
        "discovered_count": len(discovered),
        "discovered": [{"url": p.url, "title": p.title, "media_type": p.media_type} for p in discovered[:20]],
        "picked_url": picked.url,
        "download_path": str(path),
        "download_bytes": path.stat().st_size if path.exists() else 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--url",
        default="https://sustech.edu.cn/zh/academic-calendar.html",
        help="校历页面 URL 或校历资源直链（pdf/jpg/png/webp）",
    )
    ap.add_argument("--fetch-only", action="store_true", help="仅测试发现/下载链路，不做 OCR/解析")
    ap.add_argument("--force", action="store_true", help="跳过缓存强制刷新下载/解析")
    ap.add_argument("--out", default=str(_repo_root() / "temp" / "calendar_cache" / "manual_test_overrides.json"))
    args = ap.parse_args()

    if args.fetch_only:
        payload = asyncio.run(_fetch_only(args.url, force=bool(args.force)))
    else:
        payload = asyncio.run(_run(args.url, force=bool(args.force)))
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
    print(f"saved={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
