from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CalendarPdfRef:
    url: str
    title: str | None = None
    media_type: str | None = None


@dataclass(frozen=True)
class CalendarOverrides:
    cancel_days: set[date]
    move_rules: list[tuple[date, date]]
    week1_monday: date | None = None
    source_url: str | None = None
    source_pdf_url: str | None = None
    source_pdf_path: str | None = None
    extracted_pages: int | None = None
