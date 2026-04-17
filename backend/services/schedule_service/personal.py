from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class FixedPersonalEvent:
    title: str
    start_at: datetime
    end_at: datetime
    location: str | None = None


@dataclass
class TimeWindow:
    weekdays: set[int]
    start_time: str
    end_time: str


@dataclass
class PersonalTask:
    title: str
    duration_minutes: int
    target_occurrences: int
    period: Literal["day", "week", "month", "year"]
    earliest_start: datetime | None = None
    deadline: datetime | None = None
    time_windows: list[TimeWindow] | None = None
    location: str | None = None
    importance: int | None = None
    notes: str | None = None
