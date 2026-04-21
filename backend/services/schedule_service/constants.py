"""
Backward-compatible exports for schedule service constants and helpers.

Concrete implementations now live in smaller modules:
- `enums.py`
- `models.py`
- `service_config.py`
- `log_utils.py`
- `http_utils.py`
- `cas_auth.py`
"""

from .cas_auth import (
    _apply_cached_cas_cookies,
    _cas_login_for_blackboard,
    _cas_login_for_tis,
    _clear_cas_cookie_cache,
    _store_cas_cookie_cache,
)
from .enums import CourseOccurrenceKind, DeadlineType, TaskPeriod
from .http_utils import _backoff_seconds, _request_with_retry
from .log_utils import _bb_sink_dump, _bb_sink_var, _ensure_file_logging, logger
from .models import Course, CourseOccurrence, Deadline, FixedPersonalEvent, PersonalTask, TimeWindow
from .service_config import (
    ACADEMIC_SYSTEM_BASE,
    BLACKBOARD_BASE,
    SUSTECH_CLASS_PERIODS,
    TIS_WEEK1_MONDAY,
    _SUSTECH_CLASS_PERIODS,
    _TIS_WEEK1_MONDAY,
)

__all__ = [
    "ACADEMIC_SYSTEM_BASE",
    "BLACKBOARD_BASE",
    "Course",
    "CourseOccurrence",
    "CourseOccurrenceKind",
    "Deadline",
    "DeadlineType",
    "FixedPersonalEvent",
    "PersonalTask",
    "SUSTECH_CLASS_PERIODS",
    "TIS_WEEK1_MONDAY",
    "TaskPeriod",
    "TimeWindow",
    "_SUSTECH_CLASS_PERIODS",
    "_TIS_WEEK1_MONDAY",
    "_apply_cached_cas_cookies",
    "_backoff_seconds",
    "_bb_sink_dump",
    "_bb_sink_var",
    "_cas_login_for_blackboard",
    "_cas_login_for_tis",
    "_clear_cas_cookie_cache",
    "_ensure_file_logging",
    "_request_with_retry",
    "_store_cas_cookie_cache",
    "logger",
]
