from enum import Enum


class _ValueEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class DeadlineType(_ValueEnum):
    ASSIGNMENT = "assignment"
    QUIZ = "quiz"
    PROJECT = "project"
    PRESENTATION = "presentation"
    OTHER = "other"

    @classmethod
    def coerce(cls, value: "DeadlineType | str") -> "DeadlineType":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return cls.OTHER


class CourseOccurrenceKind(_ValueEnum):
    LECTURE = "lecture"
    EXPERIMENT = "experiment"
    OTHER = "other"

    @classmethod
    def coerce(cls, value: "CourseOccurrenceKind | str") -> "CourseOccurrenceKind":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return cls.OTHER


class TaskPeriod(_ValueEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"

    @classmethod
    def coerce(cls, value: "TaskPeriod | str") -> "TaskPeriod":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError as exc:
            raise ValueError(f"Unsupported task period: {value}") from exc
