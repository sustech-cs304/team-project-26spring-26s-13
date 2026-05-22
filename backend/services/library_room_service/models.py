from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class LibraryTimeQuery:
    target_date: date
    start_time: str | None = None
    end_time: str | None = None
    raw: str = ""


@dataclass(frozen=True)
class AvailableRoom:
    room_id: str
    room_name: str
    location: str
    capacity: int
    time_slots: list[str]
