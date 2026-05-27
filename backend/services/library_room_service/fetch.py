from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo

import httpx

from backend.config import settings

from .auth import BOOKING_API_BASE, library_authenticated_session
from .models import AvailableRoom, LibraryTimeQuery

_LOCAL_TZ = ZoneInfo("Asia/Shanghai")
_CACHE_TTL_SECONDS = 5 * 60.0
_CACHE: dict[str, tuple[float, list[AvailableRoom]]] = {}
_CACHE_LOCK = asyncio.Lock()

_PERIODS = {
    "上午": ("08:00", "12:00"),
    "早上": ("08:00", "12:00"),
    "中午": ("11:00", "14:00"),
    "下午": ("12:00", "18:00"),
    "晚上": ("18:00", "22:00"),
    "今晚": ("18:00", "22:00"),
    "夜间": ("18:00", "22:00"),
    "morning": ("08:00", "12:00"),
    "afternoon": ("12:00", "18:00"),
    "evening": ("18:00", "22:00"),
    "night": ("18:00", "22:00"),
}

_WEEKDAY_MAP = {
    "一": 0,
    "1": 0,
    "二": 1,
    "2": 1,
    "三": 2,
    "3": 2,
    "四": 3,
    "4": 3,
    "五": 4,
    "5": 4,
    "六": 5,
    "6": 5,
    "日": 6,
    "天": 6,
    "7": 6,
}


@dataclass(frozen=True)
class _ReserveScope:
    space_list_type: int
    key: str
    value: str
    campus_id: str | None = None


class LibraryRoomQueryError(RuntimeError):
    pass


def _now_local() -> datetime:
    return datetime.now(_LOCAL_TZ)


def normalize_library_time_slot(raw: str) -> LibraryTimeQuery:
    text = (raw or "").strip()
    lowered = text.lower()
    today = _now_local().date()
    target_date = today

    iso_match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", text)
    if iso_match:
        year, month, day = [int(part) for part in iso_match.groups()]
        target_date = date(year, month, day)
    elif "后天" in text:
        target_date = today + timedelta(days=2)
    elif "明天" in text or "tomorrow" in lowered:
        target_date = today + timedelta(days=1)
    elif "今天" in text or "今日" in text or "today" in lowered:
        target_date = today
    else:
        weekday_match = re.search(r"(?:周|星期|礼拜)([一二三四五六日天1-7])", text)
        if weekday_match:
            wanted = _WEEKDAY_MAP[weekday_match.group(1)]
            delta = (wanted - today.weekday()) % 7
            target_date = today + timedelta(days=delta)

    start_time: str | None = None
    end_time: str | None = None
    time_match = re.search(
        r"([01]?\d|2[0-3])(?::?([0-5]\d))?\s*[-~到至]\s*([01]?\d|2[0-3])(?::?([0-5]\d))?",
        text,
    )
    if time_match:
        sh, sm, eh, em = time_match.groups()
        start_time = f"{int(sh):02d}:{int(sm or '00'):02d}"
        end_time = f"{int(eh):02d}:{int(em or '00'):02d}"
    else:
        for key, period in _PERIODS.items():
            if key in lowered or key in text:
                start_time, end_time = period
                break

    return LibraryTimeQuery(
        target_date=target_date,
        start_time=start_time,
        end_time=end_time,
        raw=text,
    )


def _cache_key(
    cas_account: str, query: LibraryTimeQuery, location: str, capacity: int
) -> str:
    now_bucket = ""
    now = _now_local()
    if query.target_date == now.date() and not query.start_time:
        now_bucket = _ceil_to_next_booking_tick(now).strftime("%H:%M")

    return "|".join(
        [
            cas_account.strip().lower(),
            query.target_date.isoformat(),
            query.start_time or "",
            query.end_time or "",
            location.strip().lower(),
            str(max(capacity, 0)),
            now_bucket,
        ]
    )


async def query_available_rooms(
    cas_account: str,
    cas_password: str,
    *,
    location: str = "",
    time_slot: str = "",
    capacity: int = 0,
) -> tuple[LibraryTimeQuery, list[AvailableRoom]]:
    query = normalize_library_time_slot(time_slot)
    _validate_query_date(query)
    key = _cache_key(cas_account, query, location, capacity)

    async with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
            return query, cached[1]

    async def _run_query() -> list[AvailableRoom]:
        async with library_authenticated_session(cas_account, cas_password) as client:
            return await _query_available_rooms_uncached(
                client,
                query=query,
                location=location,
                capacity=capacity,
            )

    rooms = await asyncio.wait_for(
        _run_query(), timeout=float(settings.LIBRARY_QUERY_TIMEOUT_SECONDS)
    )

    async with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), rooms)
    return query, rooms


async def query_available_rooms_window(
    cas_account: str,
    cas_password: str,
    *,
    location: str = "",
    capacity: int = 0,
    days: int = 3,
) -> list[tuple[LibraryTimeQuery, list[AvailableRoom]]]:
    days = max(1, min(days, 3))
    today = _now_local().date()
    queries = [
        LibraryTimeQuery(target_date=today + timedelta(days=offset), raw="")
        for offset in range(days)
    ]

    async def _run_window() -> list[tuple[LibraryTimeQuery, list[AvailableRoom]]]:
        async with library_authenticated_session(cas_account, cas_password) as client:
            results: list[tuple[LibraryTimeQuery, list[AvailableRoom]]] = []
            for query in queries:
                rooms = await _query_available_rooms_uncached(
                    client,
                    query=query,
                    location=location,
                    capacity=capacity,
                )
                results.append((query, rooms))
            return results

    return await asyncio.wait_for(
        _run_window(), timeout=float(settings.LIBRARY_QUERY_TIMEOUT_SECONDS)
    )


def _validate_query_date(query: LibraryTimeQuery) -> None:
    today = _now_local().date()
    if query.target_date < today:
        raise LibraryRoomQueryError("ERROR:LIBRARY_DATE_IN_PAST")
    if query.target_date > today + timedelta(days=2):
        raise LibraryRoomQueryError("ERROR:LIBRARY_DATE_OUT_OF_RANGE")


async def _query_available_rooms_uncached(
    client: httpx.AsyncClient,
    *,
    query: LibraryTimeQuery,
    location: str,
    capacity: int,
) -> list[AvailableRoom]:
    config = await _get_public_config(client)
    space_list_type = int(config.get("spaceListType") or 1)
    scopes = await _discover_scopes(client, space_list_type=space_list_type)
    if not scopes:
        scopes = [
            _ReserveScope(space_list_type=space_list_type, key="kindIds", value="")
        ]

    rooms_by_id: dict[str, AvailableRoom] = {}
    errors: list[Exception] = []
    semaphore = asyncio.Semaphore(max(1, int(settings.LIBRARY_SCOPE_CONCURRENCY)))

    async def _fetch_scope(
        scope: _ReserveScope,
    ) -> tuple[list[dict[str, object]], Exception | None]:
        async with semaphore:
            try:
                return await _fetch_reserve_data(client, query=query, scope=scope), None
            except Exception as exc:  # noqa: BLE001
                return [], exc

    scope_results = await asyncio.gather(*(_fetch_scope(scope) for scope in scopes))
    for payload, error in scope_results:
        if error is not None:
            errors.append(error)
            continue
        for raw_room in payload:
            room = _room_from_payload(raw_room, query=query)
            if room is None:
                continue
            room = _filter_room(room, location=location, capacity=capacity, query=query)
            if room is None:
                continue
            existing = rooms_by_id.get(room.room_id)
            if existing is None:
                rooms_by_id[room.room_id] = room
            else:
                merged_slots = sorted(set(existing.time_slots) | set(room.time_slots))
                rooms_by_id[room.room_id] = AvailableRoom(
                    room_id=existing.room_id,
                    room_name=existing.room_name,
                    location=existing.location,
                    capacity=existing.capacity,
                    time_slots=merged_slots,
                )
    if errors and len(errors) == len(scope_results):
        raise errors[0]
    return sorted(
        rooms_by_id.values(),
        key=lambda r: (r.location, r.capacity or 9999, r.room_name),
    )


async def _api_get(
    client: httpx.AsyncClient,
    path: str,
    *,
    params: dict[str, object] | None = None,
) -> dict:
    response = await client.get(
        f"{BOOKING_API_BASE}/{path.lstrip('/')}",
        params={k: v for k, v in (params or {}).items() if v not in ("", None)},
        timeout=float(settings.LIBRARY_REQUEST_TIMEOUT_SECONDS),
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ConnectionError(f"Unexpected library API response: {path}")
    code = payload.get("code")
    code_text = str(code).strip() if code is not None else ""
    if code_text == "300":
        raise PermissionError(str(payload.get("message") or "Library login required"))
    if code is not None and code_text not in ("", "0"):
        raise LibraryRoomQueryError(str(payload.get("message") or f"ERROR:{code}"))
    return payload


async def _get_public_config(client: httpx.AsyncClient) -> dict[str, object]:
    payload = await _api_get(client, "sysConfig/public")
    data = payload.get("data")
    if not isinstance(data, list):
        return {}
    config: dict[str, object] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        key = str(item.get("sysKey") or "").strip()
        if key:
            config[key] = item.get("sysValue")
    return config


async def _discover_scopes(
    client: httpx.AsyncClient,
    *,
    space_list_type: int,
) -> list[_ReserveScope]:
    scopes: list[_ReserveScope] = []
    menu_payload = await _try_api_get(client, "roomMenu")
    scopes.extend(
        _scopes_from_room_menu(menu_payload.get("data") if menu_payload else None)
    )

    idle_payload = await _try_api_get(client, "home/page/room/idle")
    for item in _walk_dicts(idle_payload.get("data") if idle_payload else None):
        kind_id = _first_str(item, "kindId", "kindIds")
        lab_id = _first_str(item, "labId", "labIds")
        campus_id = _first_str(item, "campusId")
        if space_list_type == 2 and lab_id:
            scopes.append(
                _ReserveScope(
                    space_list_type=space_list_type,
                    key="labIds",
                    value=lab_id,
                    campus_id=campus_id,
                )
            )
        elif kind_id:
            scopes.append(
                _ReserveScope(
                    space_list_type=space_list_type,
                    key="kindIds",
                    value=kind_id,
                    campus_id=campus_id,
                )
            )

    deduped: list[_ReserveScope] = []
    seen: set[tuple[str, str, str | None]] = set()
    for scope in scopes:
        sig = (scope.key, scope.value, scope.campus_id)
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append(scope)
    return deduped[:20]


def _scopes_from_room_menu(value: object) -> list[_ReserveScope]:
    scopes: list[_ReserveScope] = []
    for item in _walk_dicts(value):
        if not isinstance(item, dict):
            continue

        children = item.get("children")
        if isinstance(children, list):
            for child in children:
                if not isinstance(child, dict):
                    continue
                lab_id = _first_str(child, "id", "labId", "labIds")
                campus_id = _first_str(child, "campusId")
                if lab_id:
                    scopes.append(
                        _ReserveScope(
                            space_list_type=2,
                            key="labIds",
                            value=lab_id,
                            campus_id=campus_id,
                        )
                    )

        kind_id = _first_str(item, "kindId", "kindIds")
        campus_id = _first_str(item, "campusId")
        if kind_id:
            scopes.append(
                _ReserveScope(
                    space_list_type=3 if campus_id else 1,
                    key="kindIds",
                    value=kind_id,
                    campus_id=campus_id,
                )
            )
    return scopes


async def _try_api_get(
    client: httpx.AsyncClient,
    path: str,
    *,
    params: dict[str, object] | None = None,
) -> dict | None:
    try:
        return await _api_get(client, path, params=params)
    except Exception:
        return None


async def _fetch_reserve_data(
    client: httpx.AsyncClient,
    *,
    query: LibraryTimeQuery,
    scope: _ReserveScope,
) -> list[dict[str, object]]:
    params: dict[str, object] = {
        "sysKind": 1,
        "resvDates": query.target_date.strftime("%Y%m%d"),
        "page": 1,
        "pageSize": 100,
    }
    if scope.value:
        params[scope.key] = scope.value
    if scope.space_list_type == 3 and scope.campus_id:
        params["campusId"] = scope.campus_id

    payload = await _api_get(client, "reserve", params=params)
    data = payload.get("data")
    return _extract_room_items(data)


def _extract_room_items(value: object) -> list[dict[str, object]]:
    """
    Extract room dictionaries from the booking API response.

    The library system has returned both plain lists and paginated objects over
    time (for example {"records": [...]}, {"rows": [...]}, or nested list data).
    Keeping this tolerant prevents a harmless response shape change from
    collapsing the UI into "no available rooms".
    """
    if isinstance(value, list):
        direct = [item for item in value if _looks_like_room(item)]
        if direct:
            return direct
        nested: list[dict[str, object]] = []
        for item in value:
            nested.extend(_extract_room_items(item))
        return nested

    if isinstance(value, dict):
        if _looks_like_room(value):
            return [value]

        preferred_keys = (
            "records",
            "rows",
            "list",
            "items",
            "data",
            "result",
            "roomList",
            "spaceList",
            "devList",
            "deviceList",
            "resourceList",
        )
        nested: list[dict[str, object]] = []
        for key in preferred_keys:
            if key in value:
                nested.extend(_extract_room_items(value[key]))
        if nested:
            return nested

        for child in value.values():
            nested.extend(_extract_room_items(child))
        return nested

    return []


def _looks_like_room(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    id_keys = ("devId", "devSn", "id", "devNo", "roomId", "spaceId", "resvDevId")
    name_keys = (
        "devName",
        "name",
        "roomName",
        "spaceName",
        "deviceName",
        "resvDevName",
    )
    return bool(_first_str(value, *id_keys) and _first_str(value, *name_keys))


def _room_from_payload(
    item: dict[str, object],
    *,
    query: LibraryTimeQuery,
) -> AvailableRoom | None:
    room_id = _first_str(
        item, "devId", "devSn", "id", "devNo", "roomId", "spaceId", "resvDevId"
    )
    room_name = _split_lang(
        _first_str(
            item,
            "devName",
            "name",
            "roomName",
            "spaceName",
            "deviceName",
            "resvDevName",
        )
    )
    lab_name = _split_lang(
        _first_str(
            item, "labName", "floorName", "areaName", "buildingName", "regionName"
        )
    )
    kind_name = _split_lang(_first_str(item, "kindName", "typeName", "spaceTypeName"))
    if not room_id or not room_name:
        return None

    location = " ".join(part for part in (lab_name, kind_name) if part).strip()
    if not location:
        location = lab_name or kind_name or "图书馆"

    capacity = _extract_capacity(item, room_name)
    slots = _extract_free_slots(item, query=query)
    if not slots:
        return None

    return AvailableRoom(
        room_id=room_id,
        room_name=room_name,
        location=location,
        capacity=capacity,
        time_slots=slots,
    )


def _filter_room(
    room: AvailableRoom,
    *,
    location: str,
    capacity: int,
    query: LibraryTimeQuery,
) -> AvailableRoom | None:
    if location.strip():
        haystack = f"{room.location} {room.room_name}"
        if not _location_matches(location, haystack):
            return None
    if capacity > 0 and room.capacity > 0 and room.capacity < capacity:
        return None

    slots = [_clip_slot(slot, query) for slot in room.time_slots]
    slots = [_clip_past_slot(slot, query) for slot in slots if slot]
    slots = [slot for slot in slots if slot]
    if not slots:
        return None
    return AvailableRoom(
        room_id=room.room_id,
        room_name=room.room_name,
        location=room.location,
        capacity=room.capacity,
        time_slots=sorted(set(slots)),
    )


def _extract_free_slots(
    item: dict[str, object],
    *,
    query: LibraryTimeQuery,
) -> list[str]:
    slots: list[tuple[str, str]] = []
    open_times = _flatten_open_times(
        item.get("openTimes")
        or item.get("openTime")
        or item.get("openTimeList")
        or item.get("timeList")
        or item.get("times")
    )
    for open_item in open_times:
        if _is_unavailable_open_time(open_item):
            continue
        start = _first_str(
            open_item,
            "openStartTime",
            "startTime",
            "beginTime",
            "start",
            "begin",
            "resvBeginTime",
        )
        end = _first_str(
            open_item,
            "openEndTime",
            "endTime",
            "end",
            "finishTime",
            "resvEndTime",
        )
        if start and end:
            slots.append((_hhmm(start), _hhmm(end)))

    if not slots and not open_times:
        open_start = (
            _first_str(item, "openStart", "openStartTime", "startTime") or "08:00"
        )
        open_end = _first_str(item, "openEnd", "openEndTime", "endTime") or "22:00"
        slots = [(_hhmm(open_start), _hhmm(open_end))]

    reservations = []
    for resv in _walk_dicts(item.get("resvInfo") or item.get("resvInfos")):
        start = _first_str(
            resv, "startTime", "resvBeginTime", "resvStartTime", "beginTime"
        )
        end = _first_str(resv, "endTime", "resvEndTime", "resvFinishTime", "finishTime")
        if start and end and _same_day(start, query.target_date):
            reservations.append((_hhmm(start), _hhmm(end)))

    for busy_start, busy_end in reservations:
        slots = _subtract_interval(slots, busy_start, busy_end)

    return [f"{start}-{end}" for start, end in slots if _time_lt(start, end)]


def _flatten_open_times(value: object) -> list[dict[str, object]]:
    if isinstance(value, dict):
        time_keys = {
            "openStartTime",
            "openEndTime",
            "startTime",
            "endTime",
            "beginTime",
            "finishTime",
            "start",
            "end",
        }
        if any(key in value for key in time_keys):
            return [value]
        out: list[dict[str, object]] = []
        for child in value.values():
            out.extend(_flatten_open_times(child))
        return out
    if not isinstance(value, list):
        return []
    out: list[dict[str, object]] = []
    for item in value:
        if isinstance(item, dict):
            out.append(item)
        elif isinstance(item, list):
            out.extend(_flatten_open_times(item))
    return out


def _is_unavailable_open_time(item: dict[str, object]) -> bool:
    if (
        _truthy_flag(item.get("isUsed"))
        or _truthy_flag(item.get("isBefore"))
        or _truthy_flag(item.get("disabled"))
    ):
        return True
    status = _safe_int(item.get("resvStatus") or item.get("status") or 0)
    return bool(status & 4 or status & 16)


def _truthy_flag(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "used", "disabled"}


def _safe_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _subtract_interval(
    slots: list[tuple[str, str]],
    busy_start: str,
    busy_end: str,
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for start, end in slots:
        if _time_lte(busy_end, start) or _time_lte(end, busy_start):
            out.append((start, end))
            continue
        if _time_lt(start, busy_start):
            out.append((start, busy_start))
        if _time_lt(busy_end, end):
            out.append((busy_end, end))
    return out


def _clip_slot(slot: str, query: LibraryTimeQuery) -> str | None:
    match = re.match(r"(\d{2}:\d{2})-(\d{2}:\d{2})", slot)
    if not match:
        return slot
    start, end = match.groups()
    if not query.start_time or not query.end_time:
        return slot

    # For exact ranges, require the requested interval to fit inside one free slot.
    if _time_lte(start, query.start_time) and _time_lte(query.end_time, end):
        return f"{query.start_time}-{query.end_time}"

    clipped_start = max(start, query.start_time)
    clipped_end = min(end, query.end_time)
    if _time_lt(clipped_start, clipped_end):
        return f"{clipped_start}-{clipped_end}"
    return None


def _clip_past_slot(slot: str, query: LibraryTimeQuery) -> str | None:
    now = _now_local()
    if query.target_date != now.date():
        return slot

    match = re.match(r"(\d{2}:\d{2})-(\d{2}:\d{2})", slot or "")
    if not match:
        return slot
    start, end = match.groups()
    earliest_start = _ceil_to_next_booking_tick(now).strftime("%H:%M")
    if _time_lte(end, earliest_start):
        return None
    return f"{max(start, earliest_start)}-{end}"


def _ceil_to_next_booking_tick(value: datetime) -> dt_time:
    minute = ((value.minute + 14) // 15) * 15
    hour = value.hour
    if minute >= 60:
        hour += 1
        minute = 0
    if hour >= 24:
        return dt_time(23, 59)
    return dt_time(hour, minute)


def _extract_capacity(item: dict[str, object], room_name: str) -> int:
    for key in (
        "capacity",
        "devCapacity",
        "maxCapacity",
        "maxUser",
        "maxUsers",
        "personNum",
        "seatNum",
    ):
        raw = item.get(key)
        try:
            value = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    match = re.search(r"(\d+)\s*(?:人|person|people|seat|座)", room_name, re.I)
    return int(match.group(1)) if match else 0


def _location_matches(query: str, haystack: str) -> bool:
    requirements = _location_requirements(query)
    if not requirements:
        return True
    normalized_haystack = _normalize_location_text(haystack)
    return all(
        any(option in normalized_haystack for option in group) for group in requirements
    )


def _location_requirements(text: str) -> list[tuple[str, ...]]:
    normalized = _normalize_location_text(text)
    if not normalized:
        return []

    requirements: list[tuple[str, ...]] = []
    if "一丹" in normalized or "yidan" in normalized:
        requirements.append(("一丹", "yidan"))
    if "琳恩" in normalized or "lynn" in normalized or "linen" in normalized:
        requirements.append(("琳恩", "lynn", "linen"))

    for floor in sorted(set(re.findall(r"([1-9])楼", normalized))):
        requirements.append((f"{floor}楼",))
    for room_number in sorted(set(re.findall(r"\b(\d{3,4})\b", normalized))):
        requirements.append((room_number,))

    if requirements:
        return requirements

    compact = normalized.replace(" ", "")
    return [(compact,)] if compact else []


def _normalize_location_text(text: str) -> str:
    normalized = (text or "").lower()
    for zh, digit in {
        "一": "1",
        "二": "2",
        "三": "3",
        "四": "4",
        "五": "5",
        "六": "6",
        "七": "7",
        "八": "8",
        "九": "9",
    }.items():
        normalized = normalized.replace(f"{zh}楼", f"{digit}楼")
        normalized = normalized.replace(f"{zh}层", f"{digit}楼")
    normalized = re.sub(r"\b([1-9])\s*f\b", r"\1楼", normalized)
    normalized = re.sub(r"\bfloor\s*([1-9])\b", r"\1楼", normalized)
    normalized = re.sub(r"\b([1-9])\s*floor\b", r"\1楼", normalized)
    normalized = re.sub(r"\b([1-9])\s*(?:st|nd|rd|th)\s*floor\b", r"\1楼", normalized)
    for generic in (
        "图书馆",
        "讨论间",
        "讨论室",
        "研修间",
        "自习室",
        "空间预约",
        "预约系统",
        "library",
        "discussion room",
        "study room",
        "room",
    ):
        normalized = normalized.replace(generic, " ")
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _walk_dicts(value: object) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    if isinstance(value, dict):
        out.append(value)
        for child in value.values():
            out.extend(_walk_dicts(child))
    elif isinstance(value, list):
        for item in value:
            out.extend(_walk_dicts(item))
    return out


def _first_str(item: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _split_lang(value: str) -> str:
    return (value or "").split("|", 1)[0].strip()


def _hhmm(value: str) -> str:
    text = str(value).strip()
    epoch_dt = _epoch_ms_datetime(text)
    if epoch_dt is not None:
        return epoch_dt.strftime("%H:%M")
    match = re.search(r"([01]?\d|2[0-3]):([0-5]\d)", text)
    if match:
        return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"
    match = re.search(r"([01]?\d|2[0-3])([0-5]\d)", text)
    if match:
        return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"
    match = re.fullmatch(r"([01]?\d|2[0-3])", text)
    if match:
        return f"{int(match.group(1)):02d}:00"
    return text[:5]


def _same_day(value: str, target: date) -> bool:
    text = str(value)
    epoch_dt = _epoch_ms_datetime(text)
    if epoch_dt is not None:
        return epoch_dt.date() == target
    if not re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", text):
        return True
    normalized = text.replace("/", "-")
    try:
        return datetime.fromisoformat(normalized[:10]).date() == target
    except ValueError:
        return True


def _epoch_ms_datetime(value: str) -> datetime | None:
    text = str(value).strip()
    if not re.fullmatch(r"\d{10,13}", text):
        return None
    raw = int(text)
    if raw > 10_000_000_000:
        raw = raw // 1000
    try:
        return datetime.fromtimestamp(raw, _LOCAL_TZ)
    except (OverflowError, OSError, ValueError):
        return None


def _minutes(value: str) -> int:
    parsed = dt_time.fromisoformat(_hhmm(value))
    return parsed.hour * 60 + parsed.minute


def _time_lt(left: str, right: str) -> bool:
    return _minutes(left) < _minutes(right)


def _time_lte(left: str, right: str) -> bool:
    return _minutes(left) <= _minutes(right)
