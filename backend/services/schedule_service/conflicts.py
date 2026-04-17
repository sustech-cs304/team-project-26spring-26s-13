import re
from datetime import datetime, timedelta

from backend.schemas.agent import ScheduleConflict, ScheduleData, ScheduleEvent

from .constants import CourseOccurrence, Deadline


def detect_conflicts(
    deadlines: list[Deadline],
    course_slots: list[CourseOccurrence],
) -> ScheduleData:
    def _safe_id(prefix: str, raw: str) -> str:
        s = (raw or "").strip()
        s = re.sub(r"\s+", "_", s)
        if len(s) > 200:
            s = s[:200]
        return f"{prefix}:{s}" if s else prefix

    events_with_time: list[tuple[datetime, ScheduleEvent]] = []
    conflicts: list[ScheduleConflict] = []

    for o in course_slots or []:
        title = (o.notes or o.course_id or "").strip() or "Course"
        start = o.start_at
        end = o.end_at
        time_s = f"{start.isoformat()}~{end.isoformat()}"

        detail_parts: list[str] = [f"course_id={o.course_id}"]
        if o.location:
            detail_parts.append(f"location={o.location}")
        if o.instructor:
            detail_parts.append(f"instructor={o.instructor}")
        detail = " ".join(detail_parts)

        event = ScheduleEvent(
            event_id=_safe_id("tis", f"{o.course_id}:{start.isoformat()}"),
            title=title,
            time=time_s,
            source="教务系统",
            detail=detail,
        )
        events_with_time.append((start, event))

    window = timedelta(hours=2)

    for d in deadlines or []:
        title = (d.title or "").strip() or "Deadline"
        due = d.due_at
        time_s = due.isoformat()

        detail_parts: list[str] = [f"course_id={d.course_id}", f"type={d.type}"]
        if d.url:
            detail_parts.append(f"url={d.url}")
        detail = " ".join(detail_parts)

        raw_id = f"{d.course_id}:{due.isoformat()}:{d.url or title}"
        event = ScheduleEvent(
            event_id=_safe_id("bb", raw_id),
            title=title,
            time=time_s,
            source="Blackboard",
            detail=detail,
        )
        events_with_time.append((due, event))

        start_window = due - window
        for o in course_slots or []:
            if not (o.start_at < due and o.end_at > start_window):
                continue
            course_title = (o.notes or o.course_id or "").strip() or o.course_id
            slot_time = f"{o.start_at.isoformat()}~{o.end_at.isoformat()}"
            parts = [
                f"deadline_at={due.isoformat()}",
                f"course={course_title}",
                f"course_time={slot_time}",
            ]
            if o.location:
                parts.append(f"location={o.location}")
            conflicts.append(
                ScheduleConflict(
                    title=title,
                    detail=" ".join(parts),
                )
            )

    events_with_time.sort(key=lambda x: x[0])
    events = [e for _t, e in events_with_time]
    return ScheduleData(events=events, conflicts=conflicts)
