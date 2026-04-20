"""Package exports for schedule-related services."""

from .conflicts import (
    detect_conflicts,
    detect_overlaps_with_personal,
    detect_overlaps_with_personal_payload,
    parse_personal_events,
)
from .constants import Course, CourseOccurrence, Deadline
from .effective_schedule import (
    EffectiveScheduleConflict,
    EffectiveScheduleDay,
    TeachingDayResolution,
    query_effective_schedule_conflicts,
    query_effective_schedule_for_date,
    resolve_teaching_day,
)
from .fetch_bb import fetch_blackboard
from .fetch_tis import TisScheduleContext, fetch_course_schedule, fetch_course_schedule_context
from .personal import FixedPersonalEvent, PersonalTask, TimeWindow
from .refresh import refresh

__all__ = [
    "Course",
    "CourseOccurrence",
    "Deadline",
    "FixedPersonalEvent",
    "TimeWindow",
    "PersonalTask",
    "EffectiveScheduleConflict",
    "EffectiveScheduleDay",
    "TeachingDayResolution",
    "TisScheduleContext",
    "fetch_blackboard",
    "fetch_course_schedule",
    "fetch_course_schedule_context",
    "detect_conflicts",
    "detect_overlaps_with_personal",
    "detect_overlaps_with_personal_payload",
    "parse_personal_events",
    "query_effective_schedule_conflicts",
    "query_effective_schedule_for_date",
    "resolve_teaching_day",
    "refresh",
]
