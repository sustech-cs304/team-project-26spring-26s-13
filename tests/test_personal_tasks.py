"""
Tests for personal_tasks date parsing utility.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from backend.agent.tools.personal_tasks import _parse_dt


class TestParseDt:
    def test_iso_with_timezone(self):
        result = _parse_dt("2026-04-15T14:00:00+08:00")
        assert result.hour == 14
        assert result.tzinfo is not None

    def test_iso_without_timezone(self):
        result = _parse_dt("2026-04-15T14:00:00")
        assert result.hour == 14
        assert result.tzinfo == ZoneInfo("Asia/Shanghai")

    def test_date_only(self):
        result = _parse_dt("2026-04-15")
        assert result.year == 2026
        assert result.month == 4
        assert result.day == 15
        assert result.hour == 0

    def test_invalid_raises(self):
        import pytest

        with pytest.raises(ValueError, match="无法解析"):
            _parse_dt("not-a-date")
