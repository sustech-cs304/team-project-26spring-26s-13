import asyncio
from datetime import date, datetime
import unittest
from unittest.mock import AsyncMock, patch

from backend.services.schedule_service.academic_calendar_models import CalendarOverrides
from backend.services.schedule_service.constants import CourseOccurrence
from backend.services.schedule_service.fetch_tis import (
    TisScheduleContext,
    fetch_course_schedule_context,
    invalidate_tis_schedule_cache,
)


def _make_context(course_id: str, day: int) -> TisScheduleContext:
    occurrence = CourseOccurrence(
        course_id=course_id,
        start_at=datetime(2026, 3, day, 8, 0),
        end_at=datetime(2026, 3, day, 9, 50),
        location="Room 101",
        kind="lecture",
        instructor="Teacher",
        notes=f"Course {course_id}",
    )
    overrides = CalendarOverrides(
        cancel_days=set(),
        move_rules=[],
        week1_monday=date(2026, 2, 23),
    )
    return TisScheduleContext(
        raw_occurrences=[occurrence],
        effective_occurrences=[occurrence],
        overrides=overrides,
    )


class TestFetchTisCache(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        invalidate_tis_schedule_cache()

    def tearDown(self) -> None:
        invalidate_tis_schedule_cache()

    async def test_fetch_course_schedule_context_uses_cache_for_same_account(self) -> None:
        context = _make_context("CS101", 3)

        with patch(
            "backend.services.schedule_service.fetch_tis._fetch_course_schedule_context_uncached",
            new=AsyncMock(return_value=context),
        ) as fetch_mock:
            first = await fetch_course_schedule_context("student_a", "secret")
            second = await fetch_course_schedule_context("student_a", "secret")

        self.assertIs(first, context)
        self.assertIs(second, context)
        self.assertEqual(fetch_mock.await_count, 1)

    async def test_fetch_course_schedule_context_force_refresh_replaces_cache(self) -> None:
        first_context = _make_context("CS101", 3)
        refreshed_context = _make_context("CS102", 4)

        with patch(
            "backend.services.schedule_service.fetch_tis._fetch_course_schedule_context_uncached",
            new=AsyncMock(side_effect=[first_context, refreshed_context]),
        ) as fetch_mock:
            cached = await fetch_course_schedule_context("student_b", "secret")
            refreshed = await fetch_course_schedule_context("student_b", "secret", force_refresh=True)
            after_refresh = await fetch_course_schedule_context("student_b", "secret")

        self.assertIs(cached, first_context)
        self.assertIs(refreshed, refreshed_context)
        self.assertIs(after_refresh, refreshed_context)
        self.assertEqual(fetch_mock.await_count, 2)

    async def test_invalidate_tis_schedule_cache_removes_existing_entry(self) -> None:
        first_context = _make_context("CS101", 3)
        second_context = _make_context("CS101", 5)

        with patch(
            "backend.services.schedule_service.fetch_tis._fetch_course_schedule_context_uncached",
            new=AsyncMock(side_effect=[first_context, second_context]),
        ) as fetch_mock:
            initial = await fetch_course_schedule_context("student_c", "secret")
            invalidate_tis_schedule_cache("student_c")
            after_invalidate = await fetch_course_schedule_context("student_c", "secret")

        self.assertIs(initial, first_context)
        self.assertIs(after_invalidate, second_context)
        self.assertEqual(fetch_mock.await_count, 2)

    async def test_concurrent_requests_share_single_uncached_fetch(self) -> None:
        context = _make_context("CS201", 6)

        async def delayed_fetch(*_args, **_kwargs) -> TisScheduleContext:
            await asyncio.sleep(0.01)
            return context

        with patch(
            "backend.services.schedule_service.fetch_tis._fetch_course_schedule_context_uncached",
            new=AsyncMock(side_effect=delayed_fetch),
        ) as fetch_mock:
            first, second = await asyncio.gather(
                fetch_course_schedule_context("student_d", "secret"),
                fetch_course_schedule_context("student_d", "secret"),
            )

        self.assertIs(first, context)
        self.assertIs(second, context)
        self.assertEqual(fetch_mock.await_count, 1)


if __name__ == "__main__":
    unittest.main()
