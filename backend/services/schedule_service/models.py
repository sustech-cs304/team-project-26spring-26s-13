from dataclasses import dataclass
from datetime import datetime

from .enums import CourseOccurrenceKind, DeadlineType, TaskPeriod


@dataclass
class Deadline:
    title: str
    course_id: str
    due_at: datetime
    type: DeadlineType
    course_name: str | None = None
    estimated_minutes: int | None = None
    priority: int | None = None
    url: str | None = None

    def __post_init__(self) -> None:
        self.type = DeadlineType.coerce(self.type)


@dataclass
class Course:
    course_id: str
    course_name: str
    credits: int | None = None
    experiment_credits: int | None = None


@dataclass
class CourseOccurrence:
    course_id: str
    start_at: datetime
    end_at: datetime
    location: str
    kind: CourseOccurrenceKind
    instructor: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        self.kind = CourseOccurrenceKind.coerce(self.kind)


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
    period: TaskPeriod
    earliest_start: datetime | None = None
    deadline: datetime | None = None
    time_windows: list[TimeWindow] | None = None
    location: str | None = None
    importance: int | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        self.period = TaskPeriod.coerce(self.period)
