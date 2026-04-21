from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from .academic_calendar_models import CalendarOverrides
from .models import CourseOccurrence
from .fetch_tis import fetch_course_schedule_context


@dataclass(frozen=True)
class TeachingDayResolution:
    calendar_date: date
    teaching_date: date | None
    adjusted: bool
    reason: str


@dataclass(frozen=True)
class EffectiveScheduleDay:
    resolution: TeachingDayResolution
    courses: list[CourseOccurrence]
    overrides: CalendarOverrides


@dataclass(frozen=True)
class EffectiveScheduleConflict:
    resolution: TeachingDayResolution
    activity_start: datetime
    activity_end: datetime
    day_courses: list[CourseOccurrence]
    conflicting_courses: list[CourseOccurrence]


def resolve_teaching_day(calendar_date: date, overrides: CalendarOverrides) -> TeachingDayResolution:
    move_sources = [src for src, dst in overrides.move_rules if dst == calendar_date]
    if move_sources:
        source_date = sorted(move_sources)[0]
        return TeachingDayResolution(
            calendar_date=calendar_date,
            teaching_date=source_date,
            adjusted=True,
            reason=f"{calendar_date.isoformat()} 补 {source_date.isoformat()} 的课",
        )

    if calendar_date in overrides.cancel_days:
        return TeachingDayResolution(
            calendar_date=calendar_date,
            teaching_date=None,
            adjusted=True,
            reason=f"{calendar_date.isoformat()} 为停课/调休日",
        )

    return TeachingDayResolution(
        calendar_date=calendar_date,
        teaching_date=calendar_date,
        adjusted=False,
        reason=f"{calendar_date.isoformat()} 按自然教学日执行",
    )


def _clone_occurrence_to_date(occ: CourseOccurrence, target_date: date, *, note_prefix: str | None = None) -> CourseOccurrence:
    start_at = datetime.combine(target_date, occ.start_at.timetz().replace(tzinfo=None))
    end_at = datetime.combine(target_date, occ.end_at.timetz().replace(tzinfo=None))
    note = occ.notes or occ.course_id
    if note_prefix:
        note = f"{note_prefix}{note}"
    return CourseOccurrence(
        course_id=occ.course_id,
        start_at=start_at,
        end_at=end_at,
        location=occ.location,
        kind=occ.kind,
        instructor=occ.instructor,
        notes=note,
    )


def _courses_for_calendar_date(
    raw_occurrences: list[CourseOccurrence],
    *,
    calendar_date: date,
    resolution: TeachingDayResolution,
    overrides: CalendarOverrides,
) -> list[CourseOccurrence]:
    if resolution.teaching_date is None:
        return []

    if resolution.adjusted and resolution.teaching_date != calendar_date:
        moved: list[CourseOccurrence] = []
        for occ in raw_occurrences:
            if occ.start_at.date() != resolution.teaching_date:
                continue
            moved.append(
                _clone_occurrence_to_date(
                    occ,
                    calendar_date,
                    note_prefix=f"[补 {resolution.teaching_date.isoformat()}] ",
                )
            )
        moved.sort(key=lambda item: (item.start_at, item.course_id))
        return moved

    override_days = {dst for _, dst in overrides.move_rules}
    if calendar_date in override_days:
        return []

    courses = [occ for occ in raw_occurrences if occ.start_at.date() == calendar_date]
    courses.sort(key=lambda item: (item.start_at, item.course_id))
    return courses


async def query_effective_schedule_for_date(
    cas_account: str,
    cas_password: str,
    target_date: date,
) -> EffectiveScheduleDay:
    context = await fetch_course_schedule_context(cas_account, cas_password)
    resolution = resolve_teaching_day(target_date, context.overrides)
    courses = _courses_for_calendar_date(
        context.raw_occurrences,
        calendar_date=target_date,
        resolution=resolution,
        overrides=context.overrides,
    )
    return EffectiveScheduleDay(
        resolution=resolution,
        courses=courses,
        overrides=context.overrides,
    )


async def query_effective_schedule_conflicts(
    cas_account: str,
    cas_password: str,
    target_date: date,
    activity_start_time: time,
    activity_end_time: time,
) -> EffectiveScheduleConflict:
    effective_day = await query_effective_schedule_for_date(cas_account, cas_password, target_date)
    activity_start = datetime.combine(target_date, activity_start_time)
    activity_end = datetime.combine(target_date, activity_end_time)

    conflicting_courses = [
        course
        for course in effective_day.courses
        if course.start_at < activity_end and course.end_at > activity_start
    ]

    return EffectiveScheduleConflict(
        resolution=effective_day.resolution,
        activity_start=activity_start,
        activity_end=activity_end,
        day_courses=effective_day.courses,
        conflicting_courses=conflicting_courses,
    )
