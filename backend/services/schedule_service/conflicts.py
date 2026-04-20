import json
import re
from datetime import datetime, timedelta, timezone

from backend.schemas.agent import ScheduleConflict, ScheduleData, ScheduleEvent

from .constants import CourseOccurrence, Deadline
from .personal import FixedPersonalEvent


def _safe_id(prefix: str, raw: str) -> str:
    s = (raw or "").strip()
    s = re.sub(r"\s+", "_", s)
    if len(s) > 200:
        s = s[:200]
    return f"{prefix}:{s}" if s else prefix


def _normalize_dt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_iso_dt(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _normalize_dt(value)

    s = str(value).strip()
    if not s:
        return None

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    try:
        return _normalize_dt(datetime.fromisoformat(s))
    except ValueError:
        return None


def parse_personal_events(payload: object) -> list[FixedPersonalEvent]:
    if payload is None:
        return []

    obj = payload
    if isinstance(payload, str):
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            return []

    if isinstance(obj, dict):
        for k in ("personal_events", "events", "todos", "items", "data"):
            if k in obj:
                obj = obj.get(k)
                break

    if not isinstance(obj, list):
        return []

    events: list[FixedPersonalEvent] = []

    for item in obj:
        if isinstance(item, FixedPersonalEvent):
            start_at = _normalize_dt(item.start_at)
            end_at = _normalize_dt(item.end_at)
            if end_at <= start_at:
                continue
            events.append(
                FixedPersonalEvent(
                    title=str(item.title or "").strip() or "TODO",
                    start_at=start_at,
                    end_at=end_at,
                    location=item.location,
                )
            )
            continue

        if not isinstance(item, dict):
            continue

        title = str(item.get("title") or item.get("name") or item.get("summary") or "").strip() or "TODO"

        start_raw = (
            item.get("start_at")
            or item.get("start")
            or item.get("begin")
            or (item.get("time") or {}).get("start")
            or (item.get("time") or {}).get("start_at")
        )
        end_raw = (
            item.get("end_at")
            or item.get("end")
            or item.get("finish")
            or (item.get("time") or {}).get("end")
            or (item.get("time") or {}).get("end_at")
        )

        start_at = _parse_iso_dt(start_raw)
        end_at = _parse_iso_dt(end_raw)
        if not start_at or not end_at or end_at <= start_at:
            continue

        location = item.get("location")
        if location is not None:
            location = str(location).strip() or None

        events.append(FixedPersonalEvent(title=title, start_at=start_at, end_at=end_at, location=location))

    events.sort(key=lambda e: (e.start_at, e.end_at, e.title))
    return events


def detect_conflicts(
    deadlines: list[Deadline],
    course_slots: list[CourseOccurrence],
) -> ScheduleData:

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


def detect_overlaps_with_personal(
    deadlines: list[Deadline],
    course_slots: list[CourseOccurrence],
    personal_events: list[FixedPersonalEvent],
    *,
    deadline_mode: str = "point",
    deadline_window: timedelta = timedelta(hours=2),
) -> ScheduleData:
    events_with_time: list[tuple[datetime, ScheduleEvent]] = []
    conflicts: list[ScheduleConflict] = []

    normalized_courses: list[CourseOccurrence] = []
    for o in course_slots or []:
        start = _normalize_dt(o.start_at)
        end = _normalize_dt(o.end_at)
        if end <= start:
            continue
        normalized_courses.append(
            CourseOccurrence(
                course_id=o.course_id,
                start_at=start,
                end_at=end,
                location=o.location,
                kind=o.kind,
                instructor=o.instructor,
                notes=o.notes,
            )
        )

    normalized_deadlines: list[Deadline] = []
    for d in deadlines or []:
        due = _normalize_dt(d.due_at)
        normalized_deadlines.append(
            Deadline(
                title=d.title,
                course_id=d.course_id,
                due_at=due,
                type=d.type,
                estimated_minutes=d.estimated_minutes,
                priority=d.priority,
                url=d.url,
            )
        )

    normalized_personal: list[FixedPersonalEvent] = []
    for p in personal_events or []:
        start = _normalize_dt(p.start_at)
        end = _normalize_dt(p.end_at)
        if end <= start:
            continue
        normalized_personal.append(
            FixedPersonalEvent(
                title=str(p.title or "").strip() or "TODO",
                start_at=start,
                end_at=end,
                location=p.location,
            )
        )

    for o in normalized_courses:
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

        events_with_time.append(
            (
                start,
                ScheduleEvent(
                    event_id=_safe_id("tis", f"{o.course_id}:{start.isoformat()}"),
                    title=title,
                    time=time_s,
                    source="教务系统",
                    detail=detail,
                ),
            )
        )

    for d in normalized_deadlines:
        title = (d.title or "").strip() or "Deadline"
        due = d.due_at
        time_s = due.isoformat()

        detail_parts: list[str] = [f"course_id={d.course_id}", f"type={d.type}"]
        if d.url:
            detail_parts.append(f"url={d.url}")
        detail = " ".join(detail_parts)

        raw_id = f"{d.course_id}:{due.isoformat()}:{d.url or title}"
        events_with_time.append(
            (
                due,
                ScheduleEvent(
                    event_id=_safe_id("bb", raw_id),
                    title=title,
                    time=time_s,
                    source="Blackboard",
                    detail=detail,
                ),
            )
        )

    for p in normalized_personal:
        start = p.start_at
        end = p.end_at
        time_s = f"{start.isoformat()}~{end.isoformat()}"
        detail = ""
        if p.location:
            detail = f"location={p.location}"
        events_with_time.append(
            (
                start,
                ScheduleEvent(
                    event_id=_safe_id("todo", f"{p.title}:{start.isoformat()}"),
                    title=p.title,
                    time=time_s,
                    source="Local TODO",
                    detail=detail,
                ),
            )
        )

    courses_sorted = sorted(normalized_courses, key=lambda o: (o.start_at, o.end_at, o.course_id))
    personal_sorted = sorted(normalized_personal, key=lambda p: (p.start_at, p.end_at, p.title))

    i = 0
    for p in personal_sorted:
        while i < len(courses_sorted) and courses_sorted[i].end_at <= p.start_at:
            i += 1
        j = i
        while j < len(courses_sorted) and courses_sorted[j].start_at < p.end_at:
            o = courses_sorted[j]
            if o.end_at > p.start_at:
                course_title = (o.notes or o.course_id or "").strip() or o.course_id
                todo_time = f"{p.start_at.isoformat()}~{p.end_at.isoformat()}"
                course_time = f"{o.start_at.isoformat()}~{o.end_at.isoformat()}"
                parts = [
                    "type=todo_course_overlap",
                    f"todo={p.title}",
                    f"todo_time={todo_time}",
                    f"course={course_title}",
                    f"course_time={course_time}",
                ]
                if o.location:
                    parts.append(f"course_location={o.location}")
                if p.location:
                    parts.append(f"todo_location={p.location}")
                conflicts.append(ScheduleConflict(title=p.title, detail=" ".join(parts)))
            j += 1

    if deadline_mode not in {"point", "window"}:
        deadline_mode = "point"

    deadlines_sorted = sorted(normalized_deadlines, key=lambda d: (d.due_at, d.course_id, d.title))
    di = 0
    for p in personal_sorted:
        if deadline_mode == "window":
            window_start = p.start_at - deadline_window
            while di < len(deadlines_sorted) and deadlines_sorted[di].due_at <= window_start:
                di += 1
        else:
            while di < len(deadlines_sorted) and deadlines_sorted[di].due_at < p.start_at:
                di += 1

        dj = di
        while dj < len(deadlines_sorted) and deadlines_sorted[dj].due_at < p.end_at:
            d = deadlines_sorted[dj]
            due = d.due_at

            if deadline_mode == "point":
                hit = p.start_at <= due < p.end_at
            else:
                ddl_start = due - deadline_window
                hit = max(p.start_at, ddl_start) < min(p.end_at, due)

            if hit:
                todo_time = f"{p.start_at.isoformat()}~{p.end_at.isoformat()}"
                parts = [
                    "type=todo_deadline_overlap",
                    f"mode={deadline_mode}",
                    f"todo={p.title}",
                    f"todo_time={todo_time}",
                    f"deadline={str(d.title or '').strip() or 'Deadline'}",
                    f"deadline_at={due.isoformat()}",
                    f"course_id={d.course_id}",
                ]
                if d.url:
                    parts.append(f"url={d.url}")
                conflicts.append(ScheduleConflict(title=p.title, detail=" ".join(parts)))
            dj += 1

    events_with_time.sort(key=lambda x: x[0])
    events = [e for _t, e in events_with_time]
    return ScheduleData(events=events, conflicts=conflicts)


def detect_overlaps_with_personal_payload(
    deadlines: list[Deadline],
    course_slots: list[CourseOccurrence],
    personal_payload: object,
    *,
    deadline_mode: str = "point",
    deadline_window: timedelta = timedelta(hours=2),
) -> ScheduleData:
    personal_events = parse_personal_events(personal_payload)
    return detect_overlaps_with_personal(
        deadlines,
        course_slots,
        personal_events,
        deadline_mode=deadline_mode,
        deadline_window=deadline_window,
    )
