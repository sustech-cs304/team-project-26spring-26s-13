"""
tests/test_conflicts.py
Pure unit tests for backend/services/schedule_service/conflicts.py.
No database or network calls – all functions are deterministic transforms.
"""

from datetime import datetime, timedelta

import pytest

from backend.services.schedule_service.conflicts import (
    detect_conflicts,
    detect_overlaps_with_personal,
    detect_overlaps_with_personal_payload,
    parse_personal_events,
)
from backend.services.schedule_service.constants import CourseOccurrence, Deadline
from backend.services.schedule_service.personal import FixedPersonalEvent

# ── Helpers ───────────────────────────────────────────────────────────────────

BASE_DATE = datetime(2026, 4, 28)


def _deadline(
    title: str, course_id: str, hour: int = 10, type_: str = "assignment"
) -> Deadline:
    return Deadline(
        title=title,
        course_id=course_id,
        due_at=BASE_DATE.replace(hour=hour),
        type=type_,
    )


def _course(course_id: str, start_h: int = 9, end_h: int = 10) -> CourseOccurrence:
    return CourseOccurrence(
        course_id=course_id,
        start_at=BASE_DATE.replace(hour=start_h),
        end_at=BASE_DATE.replace(hour=end_h),
        location="Room 101",
        kind="lecture",
    )


def _personal(title: str, start_h: int = 9, end_h: int = 10) -> FixedPersonalEvent:
    return FixedPersonalEvent(
        title=title,
        start_at=BASE_DATE.replace(hour=start_h),
        end_at=BASE_DATE.replace(hour=end_h),
    )


# ── detect_conflicts ──────────────────────────────────────────────────────────


def test_detect_conflicts_all_empty():
    result = detect_conflicts([], [])
    assert result.events == []
    assert result.conflicts == []


def test_detect_conflicts_courses_only_no_conflicts():
    """Courses without any deadlines produce events but zero conflicts."""
    result = detect_conflicts([], [_course("CS101")])
    assert len(result.events) == 1
    assert result.conflicts == []


def test_detect_conflicts_deadlines_only_no_conflicts():
    """Deadlines with no overlapping course slots produce no conflicts."""
    result = detect_conflicts([_deadline("HW1", "CS101", hour=8)], [])
    assert len(result.events) == 1
    assert result.conflicts == []


def test_detect_conflicts_deadline_far_from_course():
    """Deadline > 2 h away from any course slot → no conflict."""
    # Deadline at 20:00, course 09:00-10:00 → 10 h apart
    d = _deadline("Night HW", "CS101", hour=20)
    c = _course("CS101", start_h=9, end_h=10)
    result = detect_conflicts([d], [c])
    assert result.conflicts == []


def test_detect_conflicts_deadline_inside_course_window():
    """Deadline at 10:00, course ends at 10:30 → within the 2 h window → conflict."""
    d = Deadline(
        title="Quiz",
        course_id="CS101",
        due_at=BASE_DATE.replace(hour=10),
        type="quiz",
    )
    c = CourseOccurrence(
        course_id="CS101",
        start_at=BASE_DATE.replace(hour=9),
        end_at=BASE_DATE.replace(hour=10, minute=30),
        location="Room A",
        kind="lecture",
    )
    result = detect_conflicts([d], [c])
    assert len(result.conflicts) >= 1
    assert result.conflicts[0].title == "Quiz"


def test_detect_conflicts_events_sorted_chronologically():
    """Events in ScheduleData must be sorted by start time."""
    d_late = _deadline("HW-late", "CS102", hour=18)
    d_early = _deadline("HW-early", "CS101", hour=8)
    c = _course("CS103", start_h=12, end_h=13)
    result = detect_conflicts([d_late, d_early], [c])
    # Extract the time string (ISO point or range; split on "~" to get start)
    times = [ev.time.split("~")[0] for ev in result.events]
    assert times == sorted(times)


def test_detect_conflicts_event_ids_are_unique():
    """Every ScheduleEvent must have a distinct event_id."""
    deadlines = [_deadline(f"HW{i}", f"CS{i}", hour=i + 8) for i in range(3)]
    courses = [_course(f"CS{i + 10}", start_h=i + 9, end_h=i + 10) for i in range(3)]
    result = detect_conflicts(deadlines, courses)
    ids = [ev.event_id for ev in result.events]
    assert len(ids) == len(set(ids))


# ── detect_overlaps_with_personal ─────────────────────────────────────────────


def test_overlaps_all_empty():
    result = detect_overlaps_with_personal([], [], [])
    assert result.events == []
    assert result.conflicts == []


def test_overlaps_personal_no_overlap_with_course():
    """Personal event at 14-15 h, course at 09-10 h → no conflict."""
    result = detect_overlaps_with_personal(
        [],
        [_course("CS101", start_h=9, end_h=10)],
        [_personal("Library", start_h=14, end_h=15)],
    )
    assert result.conflicts == []


def test_overlaps_personal_overlaps_course():
    """Personal event and course share the same time slot → conflict."""
    result = detect_overlaps_with_personal(
        [],
        [_course("CS101", start_h=9, end_h=10)],
        [_personal("Doctor", start_h=9, end_h=10)],
    )
    assert len(result.conflicts) >= 1


def test_overlaps_personal_partial_overlap_with_course():
    """Personal 08:30-09:30 and course 09:00-10:00 → partial overlap → conflict."""
    c = CourseOccurrence(
        course_id="CS101",
        start_at=BASE_DATE.replace(hour=9, minute=0),
        end_at=BASE_DATE.replace(hour=10, minute=0),
        location="R1",
        kind="lecture",
    )
    p = FixedPersonalEvent(
        title="Errand",
        start_at=BASE_DATE.replace(hour=8, minute=30),
        end_at=BASE_DATE.replace(hour=9, minute=30),
    )
    result = detect_overlaps_with_personal([], [c], [p])
    assert len(result.conflicts) >= 1


def test_overlaps_deadline_inside_personal_point_mode():
    """Deadline at 09:30 inside personal event 09:00-10:00 → conflict (point mode)."""
    d = Deadline(
        title="Exam",
        course_id="CS201",
        due_at=BASE_DATE.replace(hour=9, minute=30),
        type="quiz",
    )
    result = detect_overlaps_with_personal(
        [d],
        [],
        [_personal("Morning block", start_h=9, end_h=10)],
        deadline_mode="point",
    )
    assert len(result.conflicts) >= 1


def test_overlaps_deadline_outside_personal_point_mode():
    """Deadline at 11:00 outside personal event 09:00-10:00 → no conflict."""
    d = _deadline("Afternoon HW", "CS201", hour=11)
    result = detect_overlaps_with_personal(
        [d],
        [],
        [_personal("Morning block", start_h=9, end_h=10)],
        deadline_mode="point",
    )
    assert result.conflicts == []


def test_overlaps_invalid_personal_event_skipped():
    """Personal events where end <= start must be silently skipped."""
    bad = FixedPersonalEvent(
        title="Bad",
        start_at=BASE_DATE.replace(hour=10),
        end_at=BASE_DATE.replace(hour=9),  # end before start
    )
    result = detect_overlaps_with_personal([], [], [bad])
    # Bad event is skipped; no crash, no events, no conflicts
    assert result.events == []
    assert result.conflicts == []


# ── parse_personal_events ─────────────────────────────────────────────────────


def test_parse_personal_events_none():
    assert parse_personal_events(None) == []


def test_parse_personal_events_empty_list():
    assert parse_personal_events([]) == []


def test_parse_personal_events_invalid_json_string():
    assert parse_personal_events("not-json") == []


def test_parse_personal_events_valid_dict_list():
    payload = [
        {
            "title": "Study group",
            "start_at": "2026-04-28T09:00:00",
            "end_at": "2026-04-28T10:00:00",
        }
    ]
    events = parse_personal_events(payload)
    assert len(events) == 1
    assert events[0].title == "Study group"


def test_parse_personal_events_skips_end_before_start():
    """Events with end ≤ start must be discarded."""
    payload = [
        {
            "title": "Backwards",
            "start_at": "2026-04-28T10:00:00",
            "end_at": "2026-04-28T09:00:00",
        }
    ]
    assert parse_personal_events(payload) == []


def test_parse_personal_events_alt_field_names():
    """Parser should accept 'start'/'end' as aliases for 'start_at'/'end_at'."""
    payload = [
        {
            "title": "Meeting",
            "start": "2026-04-28T14:00:00",
            "end": "2026-04-28T15:00:00",
        }
    ]
    events = parse_personal_events(payload)
    assert len(events) == 1
    assert events[0].title == "Meeting"


def test_parse_personal_events_missing_title_uses_default():
    """An event dict without a title should default to 'TODO'."""
    payload = [
        {
            "start_at": "2026-04-28T09:00:00",
            "end_at": "2026-04-28T10:00:00",
        }
    ]
    events = parse_personal_events(payload)
    assert len(events) == 1
    assert events[0].title == "TODO"


def test_parse_personal_events_sorted_by_start():
    """Returned events must be sorted by start time."""
    payload = [
        {
            "title": "B",
            "start_at": "2026-04-28T14:00:00",
            "end_at": "2026-04-28T15:00:00",
        },
        {
            "title": "A",
            "start_at": "2026-04-28T09:00:00",
            "end_at": "2026-04-28T10:00:00",
        },
    ]
    events = parse_personal_events(payload)
    assert events[0].title == "A"
    assert events[1].title == "B"


def test_parse_personal_events_json_string_input():
    """A JSON string containing a list should be parsed correctly."""
    import json

    payload = json.dumps(
        [
            {
                "title": "JSON event",
                "start_at": "2026-04-28T08:00:00",
                "end_at": "2026-04-28T09:00:00",
            }
        ]
    )
    events = parse_personal_events(payload)
    assert len(events) == 1
    assert events[0].title == "JSON event"


# ── detect_overlaps_with_personal_payload ─────────────────────────────────────


def test_payload_wrapper_passes_through():
    """detect_overlaps_with_personal_payload must behave like the direct variant."""
    payload = [
        {
            "title": "Errand",
            "start_at": "2026-04-28T09:00:00",
            "end_at": "2026-04-28T10:00:00",
        }
    ]
    result = detect_overlaps_with_personal_payload(
        [],
        [_course("CS101", start_h=9, end_h=10)],
        payload,
    )
    assert len(result.conflicts) >= 1
