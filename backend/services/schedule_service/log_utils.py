import contextvars
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_bb_sink_var: contextvars.ContextVar[list[tuple[str, str, int, int, str]] | None] = (
    contextvars.ContextVar(
        "bb_sink",
        default=None,
    )
)


def _log_file_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    return root / "temp" / "log.txt"


def _ensure_file_logging() -> None:
    if getattr(logger, "_bb_file_logging_ready", False):
        return

    log_path = _log_file_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_path,
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(funcName)s:%(lineno)d | %(message)s",
        )
    )

    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    setattr(logger, "_bb_file_logging_ready", True)


def _bb_sink_add(label: str, response: httpx.Response) -> None:
    sink = _bb_sink_var.get()
    if sink is None:
        return

    try:
        text = response.text or ""
    except Exception:
        text = ""

    sink.append(
        (label, str(response.url), int(response.status_code), len(text), text[:8000])
    )


def _bb_sink_dump(reason: str) -> None:
    sink = _bb_sink_var.get() or []
    logger.error("bb.dump: reason=%s responses=%d", reason, len(sink))
    for label, url, status, body_len, preview in sink[-30:]:
        logger.error(
            "bb.dump: label=%s status=%d url=%s body_len=%d\n%s",
            label,
            status,
            url,
            body_len,
            preview,
        )
