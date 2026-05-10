import asyncio
import uuid
from datetime import timedelta

from cryptography.fernet import InvalidToken

from backend.schemas.agent import ScheduleData

from .conflicts import detect_overlaps_with_personal_payload
from .fetch_bb import fetch_blackboard
from .fetch_tis import fetch_course_schedule
from .log_utils import _ensure_file_logging


async def refresh(db, user) -> ScheduleData:
    _ensure_file_logging()

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

    from backend.services import task_service

    user_id = getattr(user, "user_id", None)
    personal_tasks = []
    if user_id:
        try:
            tasks = await task_service.list_tasks(db, uuid.UUID(str(user_id)))
            for t in tasks:
                if not t.start_time:
                    continue
                end_at = t.end_time or (t.start_time + timedelta(hours=1))
                personal_tasks.append({
                    "title": t.title,
                    "start_at": t.start_time.isoformat(),
                    "end_at": end_at.isoformat(),
                    "location": t.location,
                })
        except Exception:
            pass

    return detect_overlaps_with_personal_payload(deadlines, slots, personal_tasks)
