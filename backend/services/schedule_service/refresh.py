import asyncio

from cryptography.fernet import InvalidToken

from backend.schemas.agent import ScheduleData

from .conflicts import detect_conflicts
from .fetch_bb import fetch_blackboard
from .fetch_tis import fetch_course_schedule
from .log_utils import _ensure_file_logging


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
    except (InvalidToken, TypeError, ValueError) as exc:
        raise PermissionError(f"CAS credentials invalid: {type(exc).__name__}") from exc

    deadlines, slots = await asyncio.gather(
        fetch_blackboard(cas_account, cas_password),
        fetch_course_schedule(cas_account, cas_password, force_refresh=True),
    )
    return detect_conflicts(deadlines, slots)
