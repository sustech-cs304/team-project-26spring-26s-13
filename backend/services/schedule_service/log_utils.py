import contextvars
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import socket
import uuid as _uuid

import httpx

logger = logging.getLogger(__name__)

_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "bb_trace_id", default=""
)
_sync_job_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "bb_sync_job_id", default=""
)
_diag_mode_var: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "bb_diag_mode",
    default=False,
)

_HOSTNAME: str = ""
try:
    _HOSTNAME = socket.gethostname()
except Exception:
    _HOSTNAME = "unknown"


def gen_trace_id() -> str:
    tid = _uuid.uuid4().hex[:12]
    _trace_id_var.set(tid)
    return tid


def get_trace_id() -> str:
    return _trace_id_var.get() or gen_trace_id()


def set_sync_job_id(job_id: str) -> None:
    _sync_job_id_var.set(job_id)


def get_sync_job_id() -> str:
    return _sync_job_id_var.get() or "-"


def set_diag_mode(on: bool) -> None:
    _diag_mode_var.set(on)


def is_diag_mode() -> bool:
    return _diag_mode_var.get()


def _structured_prefix() -> str:
    tid = get_trace_id()
    jid = get_sync_job_id()
    return f"host={_HOSTNAME} trace={tid} job={jid}"


class _TraceInjectFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        tid = _trace_id_var.get()
        if tid:
            record.trace_id = tid
        else:
            record.trace_id = "-"
        jid = _sync_job_id_var.get()
        record.sync_job_id = jid or "-"
        if not getattr(record, "hostname", ""):
            record.hostname = _HOSTNAME
        return True


_trace_filter = _TraceInjectFilter()

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
            "%(asctime)s %(levelname)s [%(name)s] %(funcName)s:%(lineno)d | trace=%(trace_id)s job=%(sync_job_id)s | %(message)s",
        )
    )
    handler.addFilter(_trace_filter)

    for lg_name in [
        "backend.services.schedule_service.log_utils",
        "backend.services.material_service",
    ]:
        lg = logging.getLogger(lg_name)
        lg.handlers.clear()
        lg.addHandler(handler)
        lg.setLevel(logging.DEBUG)
        lg.propagate = False

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


_FAILURE_DIR: Path | None = None


def _get_failure_dir() -> Path:
    global _FAILURE_DIR
    if _FAILURE_DIR is None:
        root = Path(__file__).resolve().parents[3]
        _FAILURE_DIR = root / "temp" / "failures"
    _FAILURE_DIR.mkdir(parents=True, exist_ok=True)
    return _FAILURE_DIR


def _dump_failure_snapshot(
    label: str,
    url: str,
    status_code: int | None,
    response_headers: dict[str, str] | None,
    response_body: str | bytes | None,
    elapsed_seconds: float | None = None,
    extra: dict | None = None,
) -> str | None:
    try:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
        filename = f"{ts}_{safe_label}.json"
        filepath = _get_failure_dir() / filename

        hex_head = ""
        body_snippet = ""
        if response_body is not None:
            try:
                if isinstance(response_body, bytes):
                    body_snippet = response_body[:4000].decode(
                        "utf-8", errors="replace"
                    )
                    hex_head = response_body[:32].hex()
                else:
                    body_snippet = str(response_body)[:4000]
                    hex_head = body_snippet.encode("utf-8")[:32].hex()
            except Exception:
                body_snippet = ""
                hex_head = ""

        safe_headers: dict[str, str] = {}
        if response_headers:
            for k, v in response_headers.items():
                kl = k.lower()
                if any(s in kl for s in ("cookie", "set-cookie", "authorization")):
                    safe_headers[k] = "***REDACTED***"
                else:
                    safe_headers[k] = v

        snapshot = {
            "label": label,
            "url": url,
            "status_code": status_code,
            "response_headers": safe_headers,
            "body_snippet": body_snippet,
            "hex_head": hex_head,
            "elapsed_seconds": round(elapsed_seconds, 4) if elapsed_seconds else None,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "trace_id": get_trace_id(),
            "host": _HOSTNAME,
            "sync_job_id": get_sync_job_id(),
            "extra": extra or {},
        }
        filepath.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.warning(
            "bb.snapshot: saved label=%s url=%s file=%s", label, url, filepath.name
        )
        return str(filepath)
    except Exception:
        logger.exception("bb.snapshot: failed to write snapshot")
        return None
