from backend.schemas.agent import ScheduleData

from .conflicts import detect_conflicts
from .constants import _ensure_file_logging, logger
from .fetch_bb import fetch_blackboard
from .fetch_tis import fetch_course_schedule


async def refresh(db, user) -> ScheduleData:
    _ensure_file_logging()
    _ = db

    cas_account = (getattr(user, "cas_account", None) or "").strip()
    cas_password_encrypted = getattr(user, "cas_password_encrypted", None)

    if not cas_account or not cas_password_encrypted:
        raise PermissionError("CAS credentials not configured")

    from backend.utils.crypto import decrypt

    try:
        cas_password = decrypt(cas_password_encrypted)
    except Exception as exc:
        raise PermissionError(f"CAS credentials invalid: {type(exc).__name__}") from exc

    slots = await fetch_course_schedule(cas_account, cas_password)

    try:
        deadlines = await fetch_blackboard(cas_account, cas_password)
    except Exception as exc:
        logger.warning(
            "schedule.refresh: blackboard fetch failed, continuing with course schedule only err=%s",
            f"{type(exc).__name__}: {exc}",
        )
        deadlines = []

    return detect_conflicts(deadlines, slots)
