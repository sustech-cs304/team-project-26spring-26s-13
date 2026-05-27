"""Tests for the SUSTech library discussion room parser."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from backend.services.library_room_service.fetch import (
    _extract_free_slots,
    _extract_room_items,
    _filter_room,
    _room_from_payload,
    _scopes_from_room_menu,
)
import backend.services.library_room_service.fetch as fetch_module
from backend.services.library_room_service.models import AvailableRoom, LibraryTimeQuery


def _query() -> LibraryTimeQuery:
    return LibraryTimeQuery(target_date=date(2026, 5, 27))


def test_extract_room_items_accepts_paginated_reserve_payload():
    payload = {
        "total": 1,
        "records": [
            {
                "devId": "room-1",
                "devName": "一丹 101",
                "openTimes": [
                    {
                        "openStartTime": "2026-05-27 08:00:00",
                        "openEndTime": "2026-05-27 10:00:00",
                    }
                ],
            }
        ],
    }

    rooms = _extract_room_items(payload)

    assert len(rooms) == 1
    assert rooms[0]["devId"] == "room-1"


def test_extract_free_slots_treats_string_zero_flags_as_available():
    room = {
        "openTimes": [
            {
                "openStartTime": "2026-05-27 08:00:00",
                "openEndTime": "2026-05-27 10:00:00",
                "isUsed": "0",
                "isBefore": "0",
                "disabled": "false",
                "resvStatus": "false",
            }
        ]
    }

    assert _extract_free_slots(room, query=_query()) == ["08:00-10:00"]


def test_room_from_payload_supports_nested_paginated_item_and_reservation_gap():
    room = {
        "roomId": "space-201",
        "spaceName": "Lynn 2F 201 6人间",
        "areaName": "Lynn Library 2F",
        "openTimeList": [
            {
                "startTime": "08:00",
                "endTime": "12:00",
                "isUsed": 0,
                "resvStatus": 0,
            }
        ],
        "resvInfos": [
            {
                "resvStartTime": "2026-05-27 09:00:00",
                "resvEndTime": "2026-05-27 10:00:00",
            }
        ],
    }

    parsed = _room_from_payload(room, query=_query())

    assert parsed is not None
    assert parsed.room_id == "space-201"
    assert parsed.capacity == 6
    assert parsed.time_slots == ["08:00-09:00", "10:00-12:00"]


def test_filter_room_matches_generic_library_floor_query(monkeypatch):
    monkeypatch.setattr(
        fetch_module,
        "_now_local",
        lambda: datetime(2026, 5, 27, 7, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    room = AvailableRoom(
        room_id="1",
        room_name="A101",
        location="一丹图书馆 1F",
        capacity=6,
        time_slots=["08:00-12:00"],
    )
    query = LibraryTimeQuery(
        target_date=date(2026, 5, 27),
        start_time="09:00",
        end_time="10:00",
    )

    filtered = _filter_room(room, location="图书馆一楼", capacity=4, query=query)

    assert filtered is not None
    assert filtered.time_slots == ["09:00-10:00"]


def test_filter_room_matches_specific_room_number_query(monkeypatch):
    monkeypatch.setattr(
        fetch_module,
        "_now_local",
        lambda: datetime(2026, 5, 27, 7, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    target = AvailableRoom(
        room_id="311",
        room_name="一丹图书馆 311 讨论间",
        location="一丹图书馆 3F",
        capacity=6,
        time_slots=["08:00-12:00"],
    )
    other = AvailableRoom(
        room_id="312",
        room_name="一丹图书馆 312 讨论间",
        location="一丹图书馆 3F",
        capacity=6,
        time_slots=["08:00-12:00"],
    )
    query = LibraryTimeQuery(target_date=date(2026, 5, 27))

    assert _filter_room(target, location="一丹图书馆311讨论间", capacity=0, query=query)
    assert (
        _filter_room(other, location="一丹图书馆311讨论间", capacity=0, query=query)
        is None
    )


def test_scopes_from_room_menu_uses_lab_ids_for_nested_floors():
    scopes = _scopes_from_room_menu(
        [
            {
                "id": 2,
                "name": "一丹讨论间",
                "children": [{"id": 6, "name": "一丹三层"}],
            }
        ]
    )

    assert scopes
    assert scopes[0].key == "labIds"
    assert scopes[0].value == "6"


def test_extract_free_slots_handles_epoch_millisecond_reservations():
    room = {
        "openTimes": [{"openStartTime": "08:00", "openEndTime": "12:00"}],
        "resvInfo": [
            {
                "startTime": 1779843600000,  # 2026-05-27 09:00 Asia/Shanghai
                "endTime": 1779847200000,  # 2026-05-27 10:00 Asia/Shanghai
            }
        ],
    }

    assert _extract_free_slots(room, query=_query()) == [
        "08:00-09:00",
        "10:00-12:00",
    ]


def test_filter_room_removes_past_slots_for_today(monkeypatch):
    monkeypatch.setattr(
        fetch_module,
        "_now_local",
        lambda: datetime(2026, 5, 27, 14, 31, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    room = AvailableRoom(
        room_id="311",
        room_name="311（1-3人）",
        location="一丹三层",
        capacity=3,
        time_slots=["08:00-12:00", "14:00-16:00", "21:00-21:15"],
    )

    filtered = _filter_room(
        room, location="一丹图书馆311讨论间", capacity=0, query=_query()
    )

    assert filtered is not None
    assert filtered.time_slots == ["14:45-16:00", "21:00-21:15"]


def test_filter_room_keeps_future_day_slots(monkeypatch):
    monkeypatch.setattr(
        fetch_module,
        "_now_local",
        lambda: datetime(2026, 5, 27, 14, 31, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    room = AvailableRoom(
        room_id="311",
        room_name="311（1-3人）",
        location="一丹三层",
        capacity=3,
        time_slots=["08:00-12:00"],
    )
    query = LibraryTimeQuery(target_date=date(2026, 5, 28))

    filtered = _filter_room(
        room, location="一丹图书馆311讨论间", capacity=0, query=query
    )

    assert filtered is not None
    assert filtered.time_slots == ["08:00-12:00"]
