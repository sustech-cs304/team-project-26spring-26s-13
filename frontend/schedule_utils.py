"""Helpers for grouping backend schedule events by calendar day."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
import re
from typing import Any


_DATE_PATTERN = re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})")


def parse_schedule_time(raw_time: str) -> tuple[datetime | None, datetime | None]:
    """Parse ScheduleEvent.time into optional start/end datetimes."""
    text = (raw_time or "").strip()
    if not text:
        return None, None

    if "~" in text:
        start_text, end_text = text.split("~", 1)
        return _parse_datetime(start_text), _parse_datetime(end_text)

    parsed = _parse_datetime(text)
    return parsed, None


def event_dates(event: dict[str, Any]) -> list[date]:
    """Return all calendar dates touched by an event."""
    start, end = parse_schedule_time(str(event.get("time", "")))
    if start is None and end is None:
        return []

    start_day = (start or end).date()
    end_day = (end or start).date()
    if end_day < start_day:
        end_day = start_day

    span = (end_day - start_day).days
    if span > 31:
        return [start_day]
    return [start_day + timedelta(days=offset) for offset in range(span + 1)]


def events_by_date(events: list[dict[str, Any]]) -> dict[date, list[dict[str, Any]]]:
    grouped: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        for day in event_dates(event):
            grouped[day].append(event)
    for day, day_events in grouped.items():
        grouped[day] = sorted(day_events, key=event_sort_key)
    return dict(grouped)


def event_sort_key(event: dict[str, Any]) -> tuple[datetime, str]:
    start, _end = parse_schedule_time(str(event.get("time", "")))
    if start is None:
        sort_time = datetime.max
    else:
        sort_time = start.replace(tzinfo=None)
    return sort_time, str(event.get("title", "")).lower()


def next_event_date(events: list[dict[str, Any]], today: date | None = None) -> date | None:
    today = today or date.today()
    all_days = sorted({day for event in events for day in event_dates(event)})
    if not all_days:
        return None
    for day in all_days:
        if day >= today:
            return day
    return all_days[-1]


def format_event_time(event: dict[str, Any], selected_day: date | None = None) -> str:
    raw_time = str(event.get("time", "")).strip()
    start, end = parse_schedule_time(raw_time)
    if start is None:
        return raw_time

    start_day = start.date()
    if end is not None:
        end_day = end.date()
        if selected_day is not None and start_day != end_day:
            return f"{start_day.isoformat()} {start:%H:%M} - {end_day.isoformat()} {end:%H:%M}"
        if start_day == end_day:
            return f"{start:%H:%M} - {end:%H:%M}"
        return f"{start_day.isoformat()} {start:%H:%M} - {end_day.isoformat()} {end:%H:%M}"

    if selected_day == start_day and start.time() != time.min:
        return f"{start:%H:%M}"
    if start.time() == time.min:
        return start_day.isoformat()
    return f"{start_day.isoformat()} {start:%H:%M}"


def _parse_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass

    match = _DATE_PATTERN.search(text)
    if not match:
        return None

    year, month, day = (int(part) for part in match.groups())
    try:
        return datetime(year, month, day)
    except ValueError:
        return None
