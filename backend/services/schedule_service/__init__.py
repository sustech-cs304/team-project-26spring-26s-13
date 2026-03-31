"""
backend/services/schedule_service/
日程爬取与冲突检测业务逻辑。
网络请求通过 httpx.AsyncClient，HTML 解析通过 BeautifulSoup。
"""

import asyncio
import contextvars
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from urllib.parse import unquote_plus, urljoin

import httpx
from bs4 import BeautifulSoup

from backend.schemas.agent import ScheduleConflict, ScheduleData, ScheduleEvent


@dataclass
class Deadline:
    title: str
    course_id: str
    due_at: datetime
    type: Literal["assignment", "quiz", "project", "presentation", "other"]
    estimated_minutes: int | None = None
    priority: int | None = None
    url: str | None = None


@dataclass
class Course:
    course_id: str
    course_name: str
    credits: int | None = None
    experiment_credits: int | None = None


@dataclass
class CourseOccurrence:
    course_id: str
    start_at: datetime
    end_at: datetime
    location: str
    kind: Literal["lecture", "experiment", "other"]
    instructor: str | None = None
    notes: str | None = None # 事件备注


@dataclass
class FixedPersonalEvent:
    # We assume that this fixed personal event occupied all time 
    # from start_at to end_at, thus no duration needed
    title: str
    start_at: datetime
    end_at: datetime
    location: str | None = None


@dataclass
class TimeWindow:
    weekdays: set[int]
    start_time: str # HH:MM, 24h format
    end_time: str # HH:MM, 24h format


@dataclass
class PersonalTask:
    title: str
    duration_minutes: int
    target_occurrences: int
    period: Literal["day", "week", "month", "year"]
    earliest_start: datetime | None = None
    deadline: datetime | None = None
    time_windows: list[TimeWindow] | None = None
    location: str | None = None
    importance: int | None = None
    notes: str | None = None


# SUSTech 相关 URL
BLACKBOARD_BASE = "https://bb.sustech.edu.cn"
ACADEMIC_SYSTEM_BASE = "https://tis.sustech.edu.cn"

logger = logging.getLogger(__name__)


_bb_sink_var: contextvars.ContextVar[list[tuple[str, str, int, int, str]] | None] = contextvars.ContextVar(
    "bb_sink",
    default=None,
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


def _bb_sink_add(label: str, r: httpx.Response) -> None:
    sink = _bb_sink_var.get()
    if sink is None:
        return

    try:
        text = r.text or ""
    except Exception:
        text = ""

    sink.append((label, str(r.url), int(r.status_code), len(text), text[:8000]))


def _bb_sink_dump(reason: str) -> None:
    sink = _bb_sink_var.get() or []
    logger.error("bb.dump: reason=%s responses=%d", reason, len(sink))
    for label, url, status, body_len, preview in sink[-30:]:
        logger.error("bb.dump: label=%s status=%d url=%s body_len=%d\n%s", label, status, url, body_len, preview)


def _test5_file_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    return root / "test" / "result" / "test5.txt"


def _preview_obj(obj: object, limit: int = 8000) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        s = obj
    else:
        try:
            s = json.dumps(obj, ensure_ascii=False, default=str)
        except Exception:
            s = str(obj)
    if len(s) > limit:
        return s[:limit] + "..."
    return s


def _tis_needs_auth_response(resp: httpx.Response) -> bool:
    if resp.status_code == 401:
        return True

    u = str(resp.url)
    if "/authentication/require" in u:
        return True
    if "cas.sustech.edu.cn" in u or "/cas/login" in u:
        return True

    ct = (resp.headers.get("content-type") or "").lower()

    if "application/json" in ct:
        try:
            txt = resp.text or ""
        except Exception:
            txt = ""
        if "身份认证" in txt or "需要身份认证" in txt or "登录" in txt:
            return True

    if ct.startswith("text/html"):
        try:
            snippet = (resp.text or "").lower()
        except Exception:
            snippet = ""
        if "cas" in snippet and ("login" in snippet or "统一身份认证" in snippet):
            return True

    return False


def _tis_dump_test5(
    *,
    reason: str,
    r_term: httpx.Response | None,
    term_payload: object | None,
    r_kb: httpx.Response | None,
    kb_payload: object | None,
    meetings_count: int,
) -> None:
    try:
        path = _test5_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        lines.append(f"reason={reason}")
        lines.append(f"meetings_count={meetings_count}")

        if r_term is not None:
            lines.append(f"term.status={r_term.status_code}")
            lines.append(f"term.url={str(r_term.url)}")
            lines.append(f"term.content_type={r_term.headers.get('content-type','')}")

        if r_kb is not None:
            lines.append(f"kb.status={r_kb.status_code}")
            lines.append(f"kb.url={str(r_kb.url)}")
            lines.append(f"kb.content_type={r_kb.headers.get('content-type','')}")

        if isinstance(kb_payload, dict):
            lines.append(f"kb_payload.type=dict keys={sorted(list(kb_payload.keys()))[:80]}")
        elif isinstance(kb_payload, list):
            lines.append(f"kb_payload.type=list len={len(kb_payload)}")
        else:
            lines.append(f"kb_payload.type={type(kb_payload).__name__}")

        interesting = 0
        samples: list[dict[str, object]] = []
        for d in _tis_iter_dicts(kb_payload):
            if not isinstance(d, dict):
                continue
            if not any(k in d for k in ("SKSJ", "SKSJ_EN", "KEY", "ZC", "KSJC", "JSJC", "RWH")):
                continue
            interesting += 1
            if len(samples) < 8:
                samples.append(
                    {
                        k: d.get(k)
                        for k in ("RWH", "KEY", "XB", "KSJC", "JSJC", "ZC", "SKSJ", "SKSJ_EN")
                        if k in d
                    }
                )

        lines.append(f"kb.interesting_dicts={interesting}")
        for i, s in enumerate(samples):
            lines.append(f"kb.sample[{i}]={_preview_obj(s, 2000)}")

        if term_payload is not None:
            lines.append("term.payload.preview=" + _preview_obj(term_payload, 2500))
        if kb_payload is not None:
            lines.append("kb.payload.preview=" + _preview_obj(kb_payload, 2500))

        path.write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        logger.exception("tis.dump_test5 failed")


def _is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code <= 599


def _backoff_seconds(attempt: int) -> float:
    return 0.5 * (2 ** (attempt - 1))


def _request_error_summary(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    content: str | bytes | None = None,
    data: dict | None = None,
    label: str = "",
) -> httpx.Response:
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            r = await client.request(method, url, headers=headers, content=content, data=data)
        except httpx.HTTPError as exc:
            logger.exception(
                "bb.http: error attempt=%d/%d method=%s url=%s label=%s err=%s",
                attempt,
                max_attempts,
                method,
                url,
                label,
                _request_error_summary(exc),
            )
            if attempt >= max_attempts:
                raise
            await asyncio.sleep(_backoff_seconds(attempt))
            continue

        if label:
            _bb_sink_add(label, r)

        if _is_retryable_status(r.status_code):
            logger.warning(
                "bb.http: retry attempt=%d/%d status=%d method=%s url=%s label=%s",
                attempt,
                max_attempts,
                r.status_code,
                method,
                url,
                label,
            )
            if attempt >= max_attempts:
                return r
            await asyncio.sleep(_backoff_seconds(attempt))
            continue

        return r

    raise RuntimeError("unreachable")



def _parse_due_at_zh_cn(text: str) -> datetime | None:
    raw = (text or "").strip()
    if not raw:
        return None

    m = re.search(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日.*?(上午|下午)\s*(\d{1,2}):(\d{2})",
        raw,
    )
    if m:
        y, mo, d, ampm, hh, mm = m.groups()
        hour = int(hh)
        minute = int(mm)
        if ampm == "下午" and hour != 12:
            hour += 12
        if ampm == "上午" and hour == 12:
            hour = 0
        return datetime(int(y), int(mo), int(d), hour, minute)

    m = re.search(
        r"\b(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T])(\d{1,2}):(\d{2})(?::(\d{2}))?\b",
        raw,
    )
    if m:
        y, mo, d, hh, mm, _ss = m.groups()
        return datetime(int(y), int(mo), int(d), int(hh), int(mm))

    month_map = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }

    m = re.search(
        r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s*(\d{4})\s*(?:at\s*)?(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)\b",
        raw,
        re.I,
    )
    if m:
        mon_s, d, y, hh, mm, _ss, ampm = m.groups()
        mo = month_map.get(mon_s.strip().lower())
        if mo is None:
            return None
        hour = int(hh)
        minute = int(mm)
        ap = ampm.upper()
        if ap == "PM" and hour != 12:
            hour += 12
        if ap == "AM" and hour == 12:
            hour = 0
        return datetime(int(y), int(mo), int(d), hour, minute)

    m = re.search(
        r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\s*(AM|PM))?\b",
        raw,
        re.I,
    )
    if m:
        d, mon_s, y, hh, mm, _ss, ampm = m.groups()
        mo = month_map.get(mon_s.strip().lower())
        if mo is None:
            return None
        hour = int(hh)
        minute = int(mm)
        if ampm:
            ap = ampm.upper()
            if ap == "PM" and hour != 12:
                hour += 12
            if ap == "AM" and hour == 12:
                hour = 0
        return datetime(int(y), int(mo), int(d), hour, minute)

    return None


_COURSE_ID_RE = re.compile(
    r"(?:\bcourse_id=|\"courseId\"\s*:\s*['\"]|\'courseId\'\s*:\s*['\"]|\bcourseId\s*:\s*['\"])(_\d+_\d+)",
    re.I,
)

_COURSE_LAUNCHER_ID_RE = re.compile(
    r"/webapps/blackboard/execute/launcher\?[^'\"\s<>]*\btype=Course\b[^'\"\s<>]*\bid=(_\d+_\d+)",
    re.I,
)

_COURSE_TYPE_ID_RE = re.compile(
    r"\btype\s*[:=]\s*['\"]Course['\"][\s\S]{0,120}?\bid\s*[:=]\s*['\"](_\d+_\d+)['\"]",
    re.I,
)

_DATA_COURSE_ID_RE = re.compile(
    r"\bdata-(?:course-id|courseid|course_id)\s*=\s*['\"](_\d+_\d+)['\"]",
    re.I,
)


def _extract_course_ids(text: str) -> set[str]:
    raw = text or ""
    ids = {m.group(1) for m in _COURSE_ID_RE.finditer(raw)}
    ids |= {m.group(1) for m in _COURSE_LAUNCHER_ID_RE.finditer(raw)}
    ids |= {m.group(1) for m in _COURSE_TYPE_ID_RE.finditer(raw)}
    ids |= {m.group(1) for m in _DATA_COURSE_ID_RE.finditer(raw)}

    try:
        decoded = unquote_plus(raw)
    except Exception:
        decoded = ""

    if decoded and decoded != raw:
        ids |= {m.group(1) for m in _COURSE_ID_RE.finditer(decoded)}
        ids |= {m.group(1) for m in _COURSE_LAUNCHER_ID_RE.finditer(decoded)}
        ids |= {m.group(1) for m in _COURSE_TYPE_ID_RE.finditer(decoded)}
        ids |= {m.group(1) for m in _DATA_COURSE_ID_RE.finditer(decoded)}

    return ids

async def _crawl_course_upload_urls(
    client: httpx.AsyncClient,
    course_id: str,
    referer: str,
) -> set[str]:
    start_url = f"{BLACKBOARD_BASE}/webapps/blackboard/execute/launcher?type=Course&id={course_id}&url="
    to_visit: list[tuple[str, str]] = [(start_url, referer)]
    queued: set[str] = {start_url}
    visited: set[str] = set()
    upload_urls: set[str] = set()

    def enqueue(next_url: str, ref: str) -> None:
        if not next_url:
            return
        if not next_url.startswith(BLACKBOARD_BASE):
            return
        next_url = next_url.split("#", 1)[0]
        if next_url in visited or next_url in queued:
            return
        queued.add(next_url)
        to_visit.append((next_url, ref))

    seed_ref = referer or start_url
    enqueue(f"{BLACKBOARD_BASE}/webapps/blackboard/execute/courseMain?course_id={course_id}&task=true&src=", seed_ref)
    for tool_id in ("_156_1", "_136_1"):
        enqueue(
            f"{BLACKBOARD_BASE}/webapps/blackboard/content/launchLink.jsp?course_id={course_id}&tool_id={tool_id}&tool_type=TOOL&mode=view",
            seed_ref,
        )

    while to_visit and len(visited) < 200 and len(upload_urls) < 1200:
        url, ref = to_visit.pop(0)
        queued.discard(url)
        if url in visited:
            continue
        visited.add(url)

        r = await _request_with_retry(
            client,
            "GET",
            url,
            headers={"Referer": ref} if ref else None,
            label=f"bb.course_crawl:{course_id}",
        )
        if r.status_code >= 400:
            logger.warning("bb.course_crawl: status=%d url=%s course_id=%s", r.status_code, str(r.url), course_id)
            continue

        final_url = str(r.url)
        html = r.text

        for u in _extract_upload_assignment_urls(html, final_url):
            upload_urls.add(u)

        soup = BeautifulSoup(html, "html.parser")
        raw_candidates: set[str] = set()

        for tag in soup.find_all(["a", "area", "frame", "iframe", "link", "script"]):
            for attr in ("href", "data-href", "src"):
                v = (tag.get(attr) or "").strip()
                if not v:
                    continue
                if v.lower().startswith("javascript:"):
                    continue
                raw_candidates.add(v)

            onclick = tag.get("onclick") or ""
            if onclick:
                for m in re.finditer(
                    r"(?:location\.href|window\.location|document\.location)\s*=\s*['\"]([^'\"]+)['\"]",
                    onclick,
                    re.I,
                ):
                    raw_candidates.add(m.group(1).strip())

        for m in re.finditer(
            r"(https?://bb\.sustech\.edu\.cn/[^'\"\s<>]+|/webapps/[^'\"\s<>]+)",
            html,
            re.I,
        ):
            raw_candidates.add(m.group(1).strip())

        for cand in raw_candidates:
            abs_url = urljoin(final_url, cand)
            if not abs_url.startswith(BLACKBOARD_BASE):
                continue
            abs_url = abs_url.split("#", 1)[0]

            if "/webapps/assignment/uploadAssignment" in abs_url:
                if _is_upload_assignment_view_url(abs_url):
                    upload_urls.add(abs_url)
                continue

            if course_id not in abs_url and f"course_id={course_id}" not in abs_url:
                if "/webapps/blackboard/content/listContent.jsp" not in abs_url:
                    if "/webapps/blackboard/content/launchLink.jsp" not in abs_url:
                        if "/webapps/blackboard/execute/courseMain" not in abs_url:
                            continue

            if "/webapps/blackboard/content/listContent.jsp" in abs_url:
                enqueue(abs_url, final_url)
                continue

            if "/webapps/blackboard/content/launchLink.jsp" in abs_url:
                enqueue(abs_url, final_url)
                continue

            if "/webapps/blackboard/execute/courseMain" in abs_url:
                enqueue(abs_url, final_url)
                continue

    return upload_urls


_UPLOAD_ASSIGNMENT_URL_RE = re.compile(
    r"(?:https?://bb\.sustech\.edu\.cn)?/webapps/assignment/uploadAssignment\?[^'\"\s<>]+",
    re.I,
)


def _is_upload_assignment_view_url(url: str) -> bool:
    try:
        u = httpx.URL(url)
    except Exception:
        return False

    if "action" in u.params and (u.params.get("action") or "").lower() == "showhistory":
        return False

    if "outcome_id" in u.params or "outcome_definition_id" in u.params:
        return False

    return bool(u.params.get("content_id"))


def _extract_upload_assignment_urls(text: str, base_url: str) -> list[str]:
    urls: set[str] = set()
    for m in _UPLOAD_ASSIGNMENT_URL_RE.finditer(text or ""):
        raw = m.group(0)
        abs_url = raw if raw.lower().startswith("http") else urljoin(base_url, raw)
        abs_url = abs_url.split("#", 1)[0]
        if not _is_upload_assignment_view_url(abs_url):
            continue
        urls.add(abs_url)
    return sorted(urls)


def _make_dwr_ids() -> tuple[str, str]:
    http_session_id = secrets.token_hex(16).upper()
    suffix = int(time.time() * 1000) % 1000
    script_session_id = f"{secrets.token_hex(16).upper()}{suffix:03d}"
    return http_session_id, script_session_id


def _page_param_from_url(page_url: str) -> str:
    u = httpx.URL(page_url)
    path = u.path
    if u.query:
        path = f"{path}?{u.query.decode('utf-8', errors='ignore')}"
    return path


async def _fetch_upload_urls_via_tool_activity_dwr(
    client: httpx.AsyncClient,
    page_url: str,
) -> list[str]:
    dwr_url = f"{BLACKBOARD_BASE}/webapps/portal/dwr_open/call/plaincall/ToolActivityService.getActivityForAllTools.dwr"
    http_session_id, script_session_id = _make_dwr_ids()
    post_data = (
        "callCount=1\n"
        f"page={_page_param_from_url(page_url)}\n"
        f"httpSessionId={http_session_id}\n"
        f"scriptSessionId={script_session_id}\n"
        "c0-scriptName=ToolActivityService\n"
        "c0-methodName=getActivityForAllTools\n"
        "c0-id=0\n"
        "c0-param0=null:null\n"
        "batchId=0\n"
    )

    r = await _request_with_retry(
        client,
        "POST",
        dwr_url,
        content=post_data,
        headers={
            "Content-Type": "text/plain",
            "Origin": BLACKBOARD_BASE,
            "Referer": page_url,
            "Suppress-Session-Timestamp-Update": "true",
        },
        label="bb.dwr.tool_activity",
    )
    if r.status_code >= 400:
        logger.warning("bb.dwr: status=%d", r.status_code)
        return []

    urls = _extract_upload_assignment_urls(r.text, BLACKBOARD_BASE)
    if urls:
        return urls

    text = r.text
    pairs: set[tuple[str, str]] = set()
    for m in re.finditer(
        r"(?:contentId|content_id)\s*[:=]\s*['\"](?P<content>_\d+_\d+)['\"][\s\S]{0,300}?"
        r"(?:courseId|course_id)\s*[:=]\s*['\"](?P<course>_\d+_\d+)['\"]",
        text,
        re.I,
    ):
        pairs.add((m.group("content"), m.group("course")))

    built: list[str] = []
    for content_id, course_id in pairs:
        built.append(
            f"{BLACKBOARD_BASE}/webapps/assignment/uploadAssignment?content_id={content_id}&course_id={course_id}&group_id=&mode=view"
        )
    return built


async def _crawl_portal_upload_urls(
    client: httpx.AsyncClient,
    start_urls: list[str],
) -> tuple[set[str], set[str]]:
    to_visit: list[tuple[str, str | None]] = [(u, None) for u in start_urls]
    queued: set[str] = set(start_urls)
    visited: set[str] = set()
    upload_urls: set[str] = set()
    seen_course_ids: set[str] = set()

    def enqueue(next_url: str, referer: str | None) -> None:
        if not next_url:
            return
        if not next_url.startswith(BLACKBOARD_BASE):
            return
        next_url = next_url.split("#", 1)[0]
        if next_url in visited or next_url in queued:
            return
        queued.add(next_url)
        to_visit.append((next_url, referer))

    while to_visit and len(visited) < 300 and len(upload_urls) < 1200:
        url, referer = to_visit.pop(0)
        queued.discard(url)
        if url in visited:
            continue
        visited.add(url)

        req_headers: dict[str, str] = {}
        if referer:
            req_headers["Referer"] = referer

        r = await _request_with_retry(
            client,
            "GET",
            url,
            headers=req_headers,
            label="bb.portal_crawl",
        )
        if r.status_code >= 400:
            logger.warning("bb.portal_crawl: status=%d url=%s", r.status_code, str(r.url))
            continue

        final_url = str(r.url)
        html = r.text

        for u in _extract_upload_assignment_urls(html, final_url):
            upload_urls.add(u)

        for course_id in _extract_course_ids(html):
            if course_id in seen_course_ids:
                continue
            seen_course_ids.add(course_id)
            enqueue(f"{BLACKBOARD_BASE}/webapps/blackboard/execute/courseMain?course_id={course_id}", final_url)

        soup = BeautifulSoup(html, "html.parser")
        raw_candidates: set[str] = set()

        for tag in soup.find_all(["a", "area", "frame", "iframe", "link", "script"]):
            for attr in ("href", "data-href", "src"):
                v = (tag.get(attr) or "").strip()
                if not v:
                    continue
                if v.lower().startswith("javascript:"):
                    continue
                raw_candidates.add(v)

            onclick = tag.get("onclick") or ""
            if onclick:
                for m in re.finditer(
                    r"(?:location\.href|window\.location|document\.location)\s*=\s*['\"]([^'\"]+)['\"]",
                    onclick,
                    re.I,
                ):
                    raw_candidates.add(m.group(1).strip())

        for m in re.finditer(
            r"(https?://bb\.sustech\.edu\.cn/[^'\"\s<>]+|/webapps/[^'\"\s<>]+)",
            html,
            re.I,
        ):
            raw_candidates.add(m.group(1).strip())

        for cand in raw_candidates:
            abs_url = urljoin(final_url, cand)
            if not abs_url.startswith(BLACKBOARD_BASE):
                continue
            abs_url = abs_url.split("#", 1)[0]

            if "/webapps/assignment/uploadAssignment" in abs_url:
                if _is_upload_assignment_view_url(abs_url):
                    upload_urls.add(abs_url)
                continue

            if "/webapps/blackboard/content/launchLink.jsp" in abs_url:
                enqueue(abs_url, final_url)
                continue

            if "/webapps/blackboard/content/listContent.jsp" in abs_url:
                enqueue(abs_url, final_url)
                continue

            if "/webapps/blackboard/execute/launcher" in abs_url and "type=Course" in abs_url:
                enqueue(abs_url, final_url)
                continue

            if "/webapps/blackboard/execute/courseMain" in abs_url:
                enqueue(abs_url, final_url)
                continue

            if "/webapps/portal/execute/tabs/tabAction" in abs_url:
                enqueue(abs_url, final_url)
                continue

            if "/webapps/portal/execute/" in abs_url:
                enqueue(abs_url, final_url)
                continue

    return seen_course_ids, upload_urls


_BB_COOKIE_CACHE: dict[str, tuple[float, list[tuple[str, str, str, str]]]] = {}
_BB_COOKIE_TTL_SECONDS = 15 * 60.0


def _export_cookies(cookies: httpx.Cookies) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    for c in cookies.jar:
        out.append((c.name, c.value, c.domain or "", c.path or "/"))
    return out


def _import_cookies(state: list[tuple[str, str, str, str]]) -> httpx.Cookies:
    cookies = httpx.Cookies()
    for name, value, domain, path in state:
        kwargs: dict[str, str] = {}
        if domain:
            kwargs["domain"] = domain
        if path:
            kwargs["path"] = path
        cookies.set(name, value, **kwargs)
    return cookies


def _parse_deadline_from_upload_assignment_html(html: str, page_url: str) -> Deadline | None:
    soup = BeautifulSoup(html, "html.parser")

    title_text = soup.title.get_text(" ", strip=True) if soup.title else ""
    assignment_title = title_text
    m = re.match(r"^上载作业：\s*(.*?)\s*[–-]\s*(.+)$", title_text)
    if m:
        assignment_title = m.group(1).strip()

    course_id = None
    m = re.search(r"\bstrCourseId\s*=\s*['\"]([^'\"]+)['\"]", html)
    if m:
        course_id = m.group(1).strip()
    if not course_id:
        m = re.search(r"\bstrCourseId=([^&'\"\s]+)", html)
        if m:
            course_id = m.group(1).strip()
    if course_id and "-" in course_id:
        course_id = course_id.split("-", 1)[0]

    if not course_id:
        try:
            u = httpx.URL(page_url)
            course_id = u.params.get("strCourseId") or u.params.get("course_id")
        except Exception:
            course_id = None

    due_at: datetime | None = None

    label = None
    for key in ("到期日期", "截止日期", "Due Date", "Due date"):
        label = soup.find("div", class_="metaLabel", string=lambda s, k=key: s and k in s)
        if label:
            break

    if label:
        section = label.find_parent("div", class_="metaSection")
        if section:
            field = section.find("div", class_="metaField")
            if field:
                due_at = _parse_due_at_zh_cn(field.get_text(" ", strip=True))

    if not due_at:
        page_text = soup.get_text(" ", strip=True)
        patterns = [
            r"\d{4}年\d{1,2}月\d{1,2}日.*?(上午|下午)\s*\d{1,2}:\d{2}",
            r"\b\d{4}-\d{1,2}-\d{1,2}(?:[ T])\d{1,2}:\d{2}(?::\d{2})?\b",
            r"\b[A-Za-z]{3,9}\s+\d{1,2},?\s*\d{4}\s*(?:at\s*)?\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)\b",
            r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:AM|PM))?\b",
        ]
        for pat in patterns:
            m = re.search(pat, page_text, re.I)
            if not m:
                continue
            due_at = _parse_due_at_zh_cn(m.group(0))
            if due_at:
                break

    if not due_at or not course_id:
        return None

    return Deadline(
        title=assignment_title,
        course_id=course_id,
        due_at=due_at,
        type="assignment",
        url=page_url,
    )


async def _cas_login(client: httpx.AsyncClient, cas_account: str, cas_password: str, service_url: str) -> None:
    login_url = httpx.URL("https://cas.sustech.edu.cn/cas/login").copy_merge_params({"service": service_url})

    if "tis.sustech.edu.cn" in str(service_url):
        r1 = await _request_with_retry(client, "GET", str(login_url), label="cas.login.get")
        r1.raise_for_status()

        soup = BeautifulSoup(r1.text, "html.parser")
        forms = list(soup.find_all("form"))
        form = None
        for f in forms:
            if f.find("input", attrs={"type": re.compile(r"^password$", re.I)}):
                form = f
                break
        if form is None:
            form = soup.find("form")
        if not form:
            raise ConnectionError("CAS login form not found")

        payload: dict[str, str] = {}
        inputs = list(form.find_all("input"))
        for inp in inputs:
            name = inp.get("name")
            if not name:
                continue
            payload[name] = inp.get("value") or ""

        for btn in form.find_all("button"):
            name = btn.get("name")
            if not name:
                continue
            if name in payload:
                continue
            if (btn.get("type") or "").lower() not in {"submit", ""}:
                continue
            payload[name] = btn.get("value") or "submit"

        password_field = None
        for inp in inputs:
            if (inp.get("type") or "").lower() == "password" and inp.get("name"):
                password_field = inp.get("name")
                break

        username_field = None
        for inp in inputs:
            t = (inp.get("type") or "").lower()
            n = (inp.get("name") or "").lower()
            if inp.get("name") and (
                n in {"username", "user", "userid", "account"}
                or (t in {"text", "email"} and "user" in n)
            ):
                username_field = inp.get("name")
                break

        if not username_field:
            for inp in inputs:
                t = (inp.get("type") or "").lower()
                if inp.get("name") and t in {"text", "email"}:
                    username_field = inp.get("name")
                    break

        if not username_field:
            username_field = "username"
            payload.setdefault(username_field, "")

        if not password_field:
            password_field = "password"
            payload.setdefault(password_field, "")

        payload[username_field] = cas_account
        payload[password_field] = cas_password

        action = form.get("action")
        if not action:
            post_url = login_url
        else:
            action_url = httpx.URL(urljoin(str(login_url), action))
            if (
                action_url.host == login_url.host
                and action_url.path == login_url.path
                and "service" not in action_url.params
                and "service" in login_url.params
            ):
                action_url = action_url.copy_merge_params({"service": login_url.params["service"]})
            post_url = action_url

        r2 = await _request_with_retry(client, "POST", str(post_url), data=payload, label="cas.login.post")
        r2.raise_for_status()

        if "cas.sustech.edu.cn" in str(r2.url) and "/cas/login" in str(r2.url):
            err_text = ""
            page_title = ""
            try:
                s2 = BeautifulSoup(r2.text, "html.parser")
                if s2.title:
                    page_title = s2.title.get_text(" ", strip=True)
                candidates = [
                    s2.find(attrs={"role": "alert"}),
                    s2.select_one(".errors, .error, .alert, .alert-danger, .alert-error"),
                    s2.find(id=re.compile(r"^(error|errors|msg|message)$", re.I)),
                    s2.find(class_=re.compile(r"\b(error|errors|alert|msg|message)\b", re.I)),
                ]
                for node in candidates:
                    if node:
                        txt = node.get_text(" ", strip=True)
                        if txt:
                            err_text = txt
                            break
                if not err_text and re.search(r"captcha|验证码", r2.text, re.I):
                    err_text = "captcha required"
            except Exception:
                err_text = ""

            msg = "CAS authentication failed"
            if page_title:
                msg = f"{msg} ({page_title})"
            if err_text:
                msg = f"{msg}: {err_text}"
            raise PermissionError(msg)

        return

    post_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": str(login_url),
        "Origin": f"{login_url.scheme}://{login_url.host}",
    }

    max_attempts = 6
    last_r2: httpx.Response | None = None

    for attempt in range(1, max_attempts + 1):
        r1 = await _request_with_retry(client, "GET", str(login_url), label="cas.login.get")
        if _is_retryable_status(r1.status_code):
            logger.warning(
                "cas.http: retry attempt=%d/%d status=%d method=GET url=%s",
                attempt,
                max_attempts,
                r1.status_code,
                str(login_url),
            )

            if "bb.sustech.edu.cn" in str(service_url):
                await _request_with_retry(client, "GET", f"{BLACKBOARD_BASE}/", label=f"bb.home.warmup{attempt}")
                r_sso = await _request_with_retry(client, "GET", str(service_url), label=f"bb.sso.warmup{attempt}")
                await _request_with_retry(
                    client,
                    "GET",
                    f"{BLACKBOARD_BASE}/webapps/portal/execute/defaultTab",
                    label=f"bb.defaultTab.warmup{attempt}",
                )
                if (
                    r_sso.status_code < 500
                    and "/cas/login" not in str(r_sso.url)
                    and "/authentication/require" not in str(r_sso.url)
                ):
                    return

            if attempt >= max_attempts:
                raise ConnectionError(f"CAS login page server error: status={r1.status_code}")
            await asyncio.sleep(_backoff_seconds(attempt))
            continue

        r1.raise_for_status()

        soup = BeautifulSoup(r1.text, "html.parser")
        forms = list(soup.find_all("form"))
        form = None
        for f in forms:
            if f.find("input", attrs={"type": re.compile(r"^password$", re.I)}):
                form = f
                break
        if form is None:
            form = soup.find("form")
        if not form:
            raise ConnectionError("CAS login form not found")

        payload: dict[str, str] = {}
        inputs = list(form.find_all("input"))
        for inp in inputs:
            name = inp.get("name")
            if not name:
                continue
            payload[name] = inp.get("value") or ""

        for btn in form.find_all("button"):
            name = btn.get("name")
            if not name:
                continue
            if name in payload:
                continue
            if (btn.get("type") or "").lower() not in {"submit", ""}:
                continue
            payload[name] = btn.get("value") or "submit"

        password_field = None
        for inp in inputs:
            if (inp.get("type") or "").lower() == "password" and inp.get("name"):
                password_field = inp.get("name")
                break

        username_field = None
        for inp in inputs:
            t = (inp.get("type") or "").lower()
            n = (inp.get("name") or "").lower()
            if inp.get("name") and (
                n in {"username", "user", "userid", "account"}
                or (t in {"text", "email"} and "user" in n)
            ):
                username_field = inp.get("name")
                break

        if not username_field:
            for inp in inputs:
                t = (inp.get("type") or "").lower()
                if inp.get("name") and t in {"text", "email"}:
                    username_field = inp.get("name")
                    break

        if not username_field:
            username_field = "username"
            payload.setdefault(username_field, "")

        if not password_field:
            password_field = "password"
            payload.setdefault(password_field, "")

        payload[username_field] = cas_account
        payload[password_field] = cas_password

        action = form.get("action")
        if not action:
            post_url = login_url
        else:
            action_url = httpx.URL(urljoin(str(login_url), action))
            if (
                action_url.host == login_url.host
                and action_url.path == login_url.path
                and "service" not in action_url.params
                and "service" in login_url.params
            ):
                action_url = action_url.copy_merge_params({"service": login_url.params["service"]})
            post_url = action_url

        try:
            r2 = await client.request("POST", str(post_url), headers=post_headers, data=payload)
        except httpx.HTTPError as exc:
            logger.exception(
                "cas.http: error attempt=%d/%d method=POST url=%s err=%s",
                attempt,
                max_attempts,
                str(post_url),
                _request_error_summary(exc),
            )
            if attempt >= max_attempts:
                raise
            await asyncio.sleep(_backoff_seconds(attempt))
            continue

        _bb_sink_add("cas.login.post", r2)
        last_r2 = r2

        if _is_retryable_status(r2.status_code):
            logger.warning(
                "cas.http: retry attempt=%d/%d status=%d method=POST url=%s",
                attempt,
                max_attempts,
                r2.status_code,
                str(post_url),
            )

            u2 = str(r2.url)
            if "bb.sustech.edu.cn" in str(service_url) and "/webapps/bb-sso-BBLEARN/execute/authValidate/customLogin" in u2:
                await _request_with_retry(client, "GET", f"{BLACKBOARD_BASE}/", label=f"bb.home.bounce{attempt}")
                await _request_with_retry(
                    client,
                    "GET",
                    f"{BLACKBOARD_BASE}/webapps/portal/execute/defaultTab",
                    label=f"bb.defaultTab.bounce{attempt}",
                )

            if attempt >= max_attempts:
                break
            await asyncio.sleep(_backoff_seconds(attempt))
            continue

        break

    if last_r2 is None:
        raise ConnectionError("CAS login failed: no response")

    r2 = last_r2

    if r2.status_code >= 500:
        u2 = str(r2.url)
        if "bb.sustech.edu.cn" in str(service_url) and "/webapps/bb-sso-BBLEARN/execute/authValidate/customLogin" in u2:
            for i in range(1, 4):
                await asyncio.sleep(_backoff_seconds(i))
                r_home = await _request_with_retry(client, "GET", f"{BLACKBOARD_BASE}/", label=f"bb.home.warmup{i}")
                r_sso = await _request_with_retry(client, "GET", service_url, label=f"bb.sso.warmup{i}")
                r_tab = await _request_with_retry(
                    client,
                    "GET",
                    f"{BLACKBOARD_BASE}/webapps/portal/execute/defaultTab",
                    label=f"bb.defaultTab.warmup{i}",
                )

                if (
                    r_sso.status_code < 500
                    and "/cas/login" not in str(r_sso.url)
                    and "/authentication/require" not in str(r_sso.url)
                ):
                    return
                if r_home.status_code < 500 and "/cas/login" not in str(r_home.url):
                    return
                if r_tab.status_code < 500 and "/cas/login" not in str(r_tab.url):
                    return

        _bb_sink_dump(f"cas_login_{r2.status_code}")
        raise ConnectionError(f"CAS/SSO server error: status={r2.status_code} url={u2}")

    r2.raise_for_status()

    if "cas.sustech.edu.cn" in str(r2.url) and "/cas/login" in str(r2.url):
        err_text = ""
        page_title = ""
        try:
            s2 = BeautifulSoup(r2.text, "html.parser")
            if s2.title:
                page_title = s2.title.get_text(" ", strip=True)
            candidates = [
                s2.find(attrs={"role": "alert"}),
                s2.select_one(".errors, .error, .alert, .alert-danger, .alert-error"),
                s2.find(id=re.compile(r"^(error|errors|msg|message)$", re.I)),
                s2.find(class_=re.compile(r"\b(error|errors|alert|msg|message)\b", re.I)),
            ]
            for node in candidates:
                if node:
                    txt = node.get_text(" ", strip=True)
                    if txt:
                        err_text = txt
                        break
            if not err_text and re.search(r"captcha|验证码", r2.text, re.I):
                err_text = "captcha required"
        except Exception:
            err_text = ""

        msg = "CAS authentication failed"
        if page_title:
            msg = f"{msg} ({page_title})"
        if err_text:
            msg = f"{msg}: {err_text}"
        raise PermissionError(msg)


async def _cas_login_enhanced(client: httpx.AsyncClient, cas_account: str, cas_password: str, service_url: str) -> None:
    """
    Enhanced CAS login with more robust handling based on bb_login.py patterns
    """
    login_url = httpx.URL("https://cas.sustech.edu.cn/cas/login").copy_merge_params({"service": service_url})

    # Enhanced headers with realistic browser headers
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Origin": f"{login_url.scheme}://{login_url.host}",
        "Referer": str(login_url),
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
    }

    max_attempts = 6
    last_r2: httpx.Response | None = None

    for attempt in range(1, max_attempts + 1):
        r1 = await _request_with_retry(client, "GET", str(login_url), headers=headers, label="cas.login.get")
        if _is_retryable_status(r1.status_code):
            logger.warning(
                "cas.http: retry attempt=%d/%d status=%d method=GET url=%s",
                attempt,
                max_attempts,
                r1.status_code,
                str(login_url),
            )
            if attempt >= max_attempts:
                raise ConnectionError(f"CAS login page server error: status={r1.status_code}")
            await asyncio.sleep(_backoff_seconds(attempt))
            continue

        r1.raise_for_status()

        soup = BeautifulSoup(r1.text, "html.parser")
        forms = list(soup.find_all("form"))
        form = None
        for f in forms:
            if f.find("input", attrs={"type": re.compile(r"^password$", re.I)}):
                form = f
                break
        if form is None:
            form = soup.find("form")
        if not form:
            raise ConnectionError("CAS login form not found")

        action = form.get("action") or "/cas/login"
        payload: dict[str, str] = {}

        # Extract all inputs
        inputs = list(form.find_all("input"))
        for inp in inputs:
            name = inp.get("name")
            if not name:
                continue
            payload[name] = inp.get("value") or ""

        # Find username and password fields
        username_field = None
        password_field = None

        for inp in inputs:
            t = (inp.get("type") or "").lower()
            n = (inp.get("name") or "").lower()
            if t == "password":
                password_field = inp.get("name")
            elif inp.get("name") and (
                n in {"username", "user", "userid", "account"}
                or (t in {"text", "email"} and "user" in n)
            ):
                username_field = inp.get("name")

        # Fallback fields
        if not username_field:
            username_field = "username"
        if not password_field:
            password_field = "password"

        # Set credentials
        payload[username_field] = cas_account
        payload[password_field] = cas_password
        payload.setdefault("_eventId", "submit")

        # Build post URL
        post_url = action if action.startswith("http") else urljoin(str(login_url), action)
        if (
            httpx.URL(post_url).host == login_url.host
            and httpx.URL(post_url).path == login_url.path
            and "service" not in httpx.URL(post_url).params
            and "service" in login_url.params
        ):
            post_url = httpx.URL(post_url).copy_merge_params({"service": login_url.params["service"]})

        # Try login
        try:
            r2 = await client.request("POST", str(post_url), headers=headers, data=payload)
            _bb_sink_add("cas.login.post", r2)
            last_r2 = r2
        except httpx.HTTPError as exc:
            logger.exception(
                "cas.http: error attempt=%d/%d method=POST url=%s err=%s",
                attempt,
                max_attempts,
                str(post_url),
                _request_error_summary(exc),
            )
            if attempt >= max_attempts:
                raise
            await asyncio.sleep(_backoff_seconds(attempt))
            continue

        # Check for redirect to Blackboard
        if 300 <= r2.status_code < 400:
            location = r2.headers.get("Location", "")
            if "bb.sustech.edu.cn" in location:
                # Follow redirect to BB
                await _request_with_retry(client, "GET", location, headers=headers, label="bb.from_cas")
                # Warm up BB session
                await _request_with_retry(client, "GET", f"{BLACKBOARD_BASE}/", label="bb.warmup_after_login")
                return

        # Handle retryable errors
        if _is_retryable_status(r2.status_code):
            u2 = str(r2.url)
            if "bb.sustech.edu.cn" in str(service_url) and "/webapps/bb-sso-BBLEARN/execute/authValidate/customLogin" in u2:
                await _request_with_retry(client, "GET", f"{BLACKBOARD_BASE}/", label=f"bb.home.bounce{attempt}")
                await _request_with_retry(
                    client,
                    "GET",
                    f"{BLACKBOARD_BASE}/webapps/portal/execute/defaultTab",
                    label=f"bb.defaultTab.bounce{attempt}",
                )

            if attempt >= max_attempts:
                break
            await asyncio.sleep(_backoff_seconds(attempt))
            continue

        # TIS may occasionally return 403 right after CAS redirects; do a light warmup then retry.
        if r2.status_code == 403 and "tis.sustech.edu.cn" in str(service_url):
            await _request_with_retry(
                client,
                "GET",
                f"{ACADEMIC_SYSTEM_BASE}/authentication/main",
                label=f"tis.main.bounce{attempt}",
            )
            if attempt >= max_attempts:
                break
            await asyncio.sleep(_backoff_seconds(attempt))
            continue

        break

    # Check if we got a successful response
    if last_r2 is None:
        raise ConnectionError("CAS login failed: no response")

    r2 = last_r2

    # Handle SSO redirect and warmup
    u2 = str(r2.url)
    if "bb.sustech.edu.cn" in u2:
        # We're being redirected to BB, follow and warm up
        await _request_with_retry(client, "GET", u2, headers=headers, label="bb.from_cas")
        await _request_with_retry(client, "GET", f"{BLACKBOARD_BASE}/", label="bb.warmup_after_login")
        return

    # Handle server errors with warmup
    if r2.status_code >= 500:
        if "bb.sustech.edu.cn" in str(service_url) and "/webapps/bb-sso-BBLEARN/execute/authValidate/customLogin" in u2:
            for i in range(1, 4):
                await asyncio.sleep(_backoff_seconds(i))
                r_home = await _request_with_retry(client, "GET", f"{BLACKBOARD_BASE}/", label=f"bb.home.warmup{i}")
                r_sso = await _request_with_retry(client, "GET", service_url, label=f"bb.sso.warmup{i}")
                r_tab = await _request_with_retry(
                    client,
                    "GET",
                    f"{BLACKBOARD_BASE}/webapps/portal/execute/defaultTab",
                    label=f"bb.defaultTab.warmup{i}",
                )

                if (
                    r_sso.status_code < 500
                    and "/cas/login" not in str(r_sso.url)
                    and "/authentication/require" not in str(r_sso.url)
                ):
                    return
                if r_home.status_code < 500 and "/cas/login" not in str(r_home.url):
                    return
                if r_tab.status_code < 500 and "/cas/login" not in str(r_tab.url):
                    return

        _bb_sink_dump(f"cas_login_{r2.status_code}")
        raise ConnectionError(f"CAS/SSO server error: status={r2.status_code} url={u2}")

    if r2.status_code == 403 and "tis.sustech.edu.cn" in str(service_url):
        _bb_sink_dump("tis_403")
        raise ConnectionError(f"TIS forbidden after CAS login: status=403 url={u2}")

    r2.raise_for_status()

    # Check for authentication errors
    if "cas.sustech.edu.cn" in u2 and "/cas/login" in u2:
        err_text = ""
        page_title = ""
        try:
            s2 = BeautifulSoup(r2.text, "html.parser")
            if s2.title:
                page_title = s2.title.get_text(" ", strip=True)
            candidates = [
                s2.find(attrs={"role": "alert"}),
                s2.select_one(".errors, .error, .alert, .alert-danger, .alert-error"),
                s2.find(id=re.compile(r"^(error|errors|msg|message)$", re.I)),
                s2.find(class_=re.compile(r"\b(error|errors|alert|msg|message)\b", re.I)),
            ]
            for node in candidates:
                if node:
                    txt = node.get_text(" ", strip=True)
                    if txt:
                        err_text = txt
                        break
            if not err_text and re.search(r"captcha|验证码", r2.text, re.I):
                err_text = "captcha required"
        except Exception:
            err_text = ""

        msg = "CAS authentication failed"
        if page_title:
            msg = f"{msg} ({page_title})"
        if err_text:
            msg = f"{msg}: {err_text}"
        raise PermissionError(msg)


async def fetch_blackboard(cas_account: str, cas_password: str) -> list[Deadline]:
    """
    使用 CAS 统一认证登录 Blackboard，爬取当前学期所有未完成作业/考试的截止时间。

    Args:
        cas_account:  南科大 CAS 账号
        cas_password: CAS 密码（已由调用方解密）

    Returns:
        list[Deadline]，按截止时间升序排列

    Raises:
        ConnectionError: CAS 或 Blackboard 服务不可达
        PermissionError: CAS 认证失败（账号密码错误）
    """
    _ensure_file_logging()
    logger.debug("bb.fetch: enter account=%s", cas_account)

    if not cas_account or not cas_password:
        logger.error("bb.fetch: invalid credentials cas_account=%s password_len=%s", bool(cas_account), len(cas_password or ""))
        raise ValueError("Missing CAS credentials")

    service_url = f"{BLACKBOARD_BASE}/webapps/bb-sso-BBLEARN/index.jsp"
    tab_url = f"{BLACKBOARD_BASE}/webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1"
    default_tab_url = f"{BLACKBOARD_BASE}/webapps/portal/execute/defaultTab"

    # Enhanced headers with realistic browser headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }

    token = _bb_sink_var.set([])

    cached = _BB_COOKIE_CACHE.get(cas_account)
    cookies: httpx.Cookies | None = None
    if cached and (time.time() - cached[0]) < _BB_COOKIE_TTL_SECONDS:
        cookies = _import_cookies(cached[1])

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            headers=headers,
            timeout=10.0,
            trust_env=False,
            cookies=cookies,
        ) as client:
            async def _bb_warmup(label_suffix: str) -> None:
                await _request_with_retry(client, "GET", service_url, label=f"bb.sso{label_suffix}")
                await _request_with_retry(client, "GET", f"{BLACKBOARD_BASE}/", label=f"bb.home{label_suffix}")
                await _request_with_retry(
                    client,
                    "GET",
                    f"{BLACKBOARD_BASE}/webapps/portal/execute/defaultTab",
                    label=f"bb.defaultTab{label_suffix}",
                )

            def _looks_like_transient_bb_500(r: httpx.Response) -> bool:
                if r.status_code >= 500:
                    return True
                u = str(r.url)
                if "/webapps/bb-sso-BBLEARN/execute/authValidate/customLogin" in u:
                    return True
                return False

            async def _frontdoor_home(label_suffix: str) -> httpx.Response:
                r = await _request_with_retry(client, "GET", f"{BLACKBOARD_BASE}/", label=f"bb.home{label_suffix}")

                for _ in range(10):
                    if not (300 <= r.status_code < 400):
                        break
                    loc = r.headers.get("Location") or ""
                    if not loc:
                        break
                    loc = urljoin(str(r.url), loc)
                    r = await _request_with_retry(client, "GET", loc, label=f"bb.redirect{label_suffix}")

                return r

            async def _bb_open_frontdoor(label_suffix: str) -> httpx.Response:
                await _frontdoor_home(label_suffix)
                await _request_with_retry(
                    client,
                    "GET",
                    f"{BLACKBOARD_BASE}/webapps/portal/execute/defaultTab",
                    label=f"bb.defaultTab{label_suffix}",
                )
                return await _request_with_retry(client, "GET", tab_url, label=f"bb.tab{label_suffix}")

            # Initial frontdoor request
            r0 = await _bb_open_frontdoor(".entry")

            # If redirected to CAS, login
            if "cas.sustech.edu.cn" in str(r0.url):
                logger.info("bb.fetch: redirected to CAS, starting login")
                await _cas_login_enhanced(client, cas_account, cas_password, service_url)
                await _bb_warmup(".after_login")
                r0 = await _bb_open_frontdoor(".after_login")

            # Handle transient 500 errors
            if _looks_like_transient_bb_500(r0):
                logger.warning("bb.fetch: detected transient 500 error, attempting recovery")
                for attempt in range(1, 4):
                    await asyncio.sleep(_backoff_seconds(attempt))
                    await _bb_warmup(f".recover{attempt}")
                    r0 = await _request_with_retry(client, "GET", tab_url, label=f"bb.tab.recover{attempt}")
                    if not _looks_like_transient_bb_500(r0):
                        logger.info("bb.fetch: recovery successful on attempt %d", attempt)
                        break

            if _looks_like_transient_bb_500(r0):
                err_id = r0.headers.get("X-Blackboard-errorid") or r0.headers.get("x-blackboard-errorid")
                raise ConnectionError(
                    f"Blackboard login unstable: status={r0.status_code} url={str(r0.url)} errorid={err_id or ''}".strip()
                )

            # Update cookie cache
            _BB_COOKIE_CACHE[cas_account] = (time.time(), _export_cookies(client.cookies))

            base_url = str(r0.url)

            # Extract course IDs from various sources
            course_ids = _extract_course_ids(r0.text)

            # Crawl portal for courses and upload URLs
            portal_course_ids, portal_upload_urls = await _crawl_portal_upload_urls(
                client,
                [
                    tab_url,
                    default_tab_url,
                ],
            )

            course_ids |= portal_course_ids

            # Extract URLs from initial page
            upload_url_set: set[str] = set(_extract_upload_assignment_urls(r0.text, base_url))
            upload_url_set |= set(portal_upload_urls)

            # Try DWR method (browser uses tabAction as page+referer)
            dwr_urls = await _fetch_upload_urls_via_tool_activity_dwr(client, tab_url)
            upload_url_set |= set(dwr_urls)

            # Crawl each course for upload URLs (human flow starts from tabAction -> launcher)
            for course_id in sorted(course_ids):
                course_urls = await _crawl_course_upload_urls(client, course_id, tab_url)
                upload_url_set |= course_urls

            upload_urls = sorted(upload_url_set)

            logger.info(
                "bb.fetch: base=%s course_ids=%d upload_urls(seed)=%d dwr_urls=%d total=%d",
                base_url,
                len(course_ids),
                len(_extract_upload_assignment_urls(r0.text, base_url)),
                len(dwr_urls),
                len(upload_urls),
            )

            # Fallback if no URLs found
            if not upload_urls:
                logger.warning("bb.fetch: no upload urls after seed+dwr+course crawl; running portal fallback")
                portal_course_ids2, portal_upload_urls2 = await _crawl_portal_upload_urls(
                    client,
                    [
                        tab_url,
                        default_tab_url,
                    ],
                )
                course_ids |= portal_course_ids2
                upload_url_set |= portal_upload_urls2
                for course_id in sorted(portal_course_ids2):
                    course_urls = await _crawl_course_upload_urls(client, course_id, tab_url)
                    upload_url_set |= course_urls
                upload_urls = sorted(upload_url_set)

            # Fetch deadlines from all URLs
            async def fetch_one(u: str) -> Deadline | None:
                try:
                    r = await _request_with_retry(
                        client,
                        "GET",
                        u,
                        headers={
                            "Referer": tab_url,
                            **headers
                        },
                        label="bb.upload_assignment",
                    )
                except httpx.HTTPError as exc:
                    logger.warning("bb.fetch: request failed url=%s err=%s", u, type(exc).__name__)
                    return None

                if r.status_code >= 400:
                    if r.status_code == 500 and _looks_like_transient_bb_500(r):
                        logger.warning("bb.fetch: transient 500 error on url=%s", u)
                        return None
                    logger.warning(
                        "bb.fetch: bad status=%s url=%s body_len=%d",
                        r.status_code,
                        u,
                        len(r.text or ""),
                    )
                    return None

                try:
                    return _parse_deadline_from_upload_assignment_html(r.text, u)
                except Exception as exc:
                    logger.exception(
                        "bb.fetch: parse failed url=%s err=%s body_preview=%s",
                        u,
                        type(exc).__name__,
                        (r.text or "")[:2000],
                    )
                    return None

            # Gather all deadlines
            now_local = datetime.now()
            deadlines_raw = await asyncio.gather(*(fetch_one(u) for u in upload_urls))
            deadlines = [
                d
                for d in deadlines_raw
                if d and d.type == "assignment" and d.due_at and d.due_at >= now_local
            ]

            # Final fallback if no deadlines found
            if not deadlines and upload_urls:
                logger.warning(
                    "bb.fetch: %d upload urls fetched but 0 parsed deadlines; trying portal+course refresh",
                    len(upload_urls),
                )
                portal_course_ids3, portal_upload_urls3 = await _crawl_portal_upload_urls(
                    client,
                    [
                        tab_url,
                        default_tab_url,
                    ],
                )
                upload_url_set2 = set(upload_urls)
                upload_url_set2 |= portal_upload_urls3
                for course_id in sorted(portal_course_ids3):
                    course_urls = await _crawl_course_upload_urls(client, course_id, tab_url)
                    upload_url_set2 |= course_urls

                deadlines_raw2 = await asyncio.gather(*(fetch_one(u) for u in sorted(upload_url_set2)))
                deadlines = [
                    d
                    for d in deadlines_raw2
                    if d and d.type == "assignment" and d.due_at and d.due_at >= now_local
                ]

            deadlines.sort(key=lambda x: x.due_at)
            logger.info("bb.fetch: deadlines=%d", len(deadlines))
            if not deadlines:
                _bb_sink_dump("deadlines_empty")
            logger.debug("bb.fetch: exit deadlines=%d", len(deadlines))
            return deadlines
    finally:
        try:
            _bb_sink_var.reset(token)
        except Exception:
            logger.exception("bb.fetch: sink reset failed")


_TIS_WEEK1_MONDAY = datetime(2026, 2, 23)

_SUSTECH_CLASS_PERIODS: dict[int, tuple[str, str]] = {
    1: ("08:00", "08:50"),
    2: ("09:00", "09:50"),
    3: ("10:20", "11:10"),
    4: ("11:20", "12:10"),
    5: ("14:00", "14:50"),
    6: ("15:00", "15:50"),
    7: ("16:20", "17:10"),
    8: ("17:20", "18:10"),
    9: ("19:00", "19:50"),
    10: ("20:00", "20:50"),
}


def _tis_iter_dicts(obj: object):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _tis_iter_dicts(v)
        return

    if isinstance(obj, list):
        for item in obj:
            yield from _tis_iter_dicts(item)
        return

    if isinstance(obj, str):
        s = obj.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                parsed = json.loads(s)
            except Exception:
                return
            yield from _tis_iter_dicts(parsed)


def _tis_extract_xn_xq(payload: object) -> tuple[str, str] | None:
    if isinstance(payload, dict):
        xn = payload.get("xn") or payload.get("XN") or payload.get("xndm") or payload.get("XNDM")
        xq = payload.get("xq") or payload.get("XQ") or payload.get("xqdm") or payload.get("XQDM")
        if isinstance(xn, str) and isinstance(xq, (str, int)) and xn.strip():
            return xn.strip(), str(xq).strip()

    text = str(payload or "")
    m = re.search(r"\b(20\d{2}-20\d{2})\b", text)
    if not m:
        return None
    xn = m.group(1)
    m2 = re.search(r"\b(xq|XQ|xqdm|XQDM)\s*[:=]\s*['\"]?(1|2)['\"]?\b", text)
    if m2:
        return xn, m2.group(2)
    return None


def _tis_parse_weekday(v: object) -> int | None:
    if isinstance(v, int) and 1 <= v <= 7:
        return v
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit():
            n = int(s)
            if 1 <= n <= 7:
                return n
        m = re.search(r"(?:星期|周)([一二三四五六日天])", s)
        if m:
            mp = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}
            return mp.get(m.group(1))
        if len(s) == 1 and s in "一二三四五六日天":
            mp = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}
            return mp.get(s)
    return None


def _tis_parse_sections(v: object) -> tuple[int, int] | None:
    if isinstance(v, (tuple, list)) and len(v) == 2:
        try:
            a = int(v[0])
            b = int(v[1])
            if 1 <= a <= b <= 16:
                return a, b
        except Exception:
            return None

    if isinstance(v, int) and 1 <= v <= 16:
        return v, v

    if isinstance(v, str):
        s = v.strip()

        m = re.search(r"(\d{1,2})\s*[-~]\s*(\d{1,2})(?:\s*节)?", s)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 1 <= a <= b <= 16:
                return a, b

        m = re.search(r"(\d{1,2})\s*[,，、]\s*(\d{1,2})", s)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 1 <= a <= b <= 16:
                return a, b

        m = re.search(r"(\d{1,2})", s)
        if m:
            a = int(m.group(1))
            if 1 <= a <= 16:
                return a, a

    return None


def _tis_parse_weeks(v: object) -> list[int]:
    if isinstance(v, list):
        out: list[int] = []
        for item in v:
            try:
                n = int(str(item).strip())
            except Exception:
                continue
            if 1 <= n <= 40:
                out.append(n)
        return sorted(set(out))

    if isinstance(v, int) and 1 <= v <= 40:
        return [v]

    if not isinstance(v, str):
        return []

    s = v.strip()
    odd_only = "单" in s
    even_only = "双" in s

    m = re.search(r"(\d{1,2})\s*[-~]\s*(\d{1,2})(?:\s*周)?", s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        nums = list(range(min(a, b), max(a, b) + 1))
    else:
        nums = [int(x) for x in re.findall(r"(\d{1,2})", s)]

    if odd_only:
        nums = [n for n in nums if n % 2 == 1]
    if even_only:
        nums = [n for n in nums if n % 2 == 0]

    nums = [n for n in nums if 1 <= n <= 40]
    return sorted(set(nums))


def _tis_parse_zc_bitset(v: object) -> list[int]:
    if not isinstance(v, str):
        return []

    s = v.strip()
    if not s or any(ch not in "01" for ch in s):
        return []

    out: list[int] = []
    for i, ch in enumerate(s):
        if ch != "1":
            continue
        if i <= 0:
            continue
        if 1 <= i <= 40:
            out.append(i)

    return out


def _tis_dt(day0: datetime, hhmm: str) -> datetime:
    hh, mm = hhmm.split(":", 1)
    return datetime(day0.year, day0.month, day0.day, int(hh), int(mm))


def _tis_extract_meetings(payload: object) -> list[dict[str, object]]:
    meetings: list[dict[str, object]] = []

    for d in _tis_iter_dicts(payload):
        if not isinstance(d, dict):
            continue

        desc_src = d.get("SKSJ") or d.get("SKSJ_EN")

        course_name = (
            d.get("kcmc")
            or d.get("KCMC")
            or d.get("course")
            or d.get("courseName")
            or d.get("name")
            or d.get("title")
        )
        teacher = d.get("jsxm") or d.get("JSXM") or d.get("teacher") or d.get("instructor")
        location = d.get("cdmc") or d.get("CDMC") or d.get("room") or d.get("location")

        weekday = None
        for k in ("xq", "XQ", "xqj", "XQJ", "weekday", "dayOfWeek", "xqjmc", "weekDay"):
            if k in d:
                weekday = _tis_parse_weekday(d.get(k))
                if weekday:
                    break

        if not weekday:
            key = d.get("KEY") or d.get("key")
            if isinstance(key, str):
                m = re.search(r"xq([1-7])", key)
                if m:
                    weekday = int(m.group(1))

        sections = None
        if ("ksjc" in d and "jsjc" in d) or ("KSJC" in d and "JSJC" in d):
            sections = _tis_parse_sections((d.get("ksjc") or d.get("KSJC"), d.get("jsjc") or d.get("JSJC")))

        if not sections:
            for k in ("jcs", "JCS", "jc", "JC", "qzjc", "QZJC"):
                if k in d:
                    sections = _tis_parse_sections(d.get(k))
                    if sections:
                        break

        weeks = _tis_parse_zc_bitset(d.get("ZC") or d.get("zc"))
        if not weeks:
            for k in ("zcs", "ZCS", "weeks", "week", "kkzc", "KKZC", "weekRange"):
                if k in d:
                    weeks = _tis_parse_weeks(d.get(k))
                    if weeks:
                        break

        desc = ""
        if isinstance(desc_src, str) and ("周" in desc_src and "节" in desc_src):
            desc = desc_src
        else:
            for v in d.values():
                if isinstance(v, str) and ("周" in v and "节" in v):
                    desc = v
                    break

        if desc and (not course_name or not weekday or not sections or not weeks):
            txt = desc
            if not course_name:
                course_name = txt.split("[", 1)[0].strip() or course_name
            if not teacher:
                m = re.search(r"\[([^\[\]]+)\]", txt)
                if m:
                    teacher = m.group(1).strip()
            if not weeks:
                m = re.search(r"\[(\d{1,2}\s*[-~]\s*\d{1,2}\s*周(?:[^\]]*)?)\]", txt)
                if m:
                    weeks = _tis_parse_weeks(m.group(1))
            if not sections:
                m = re.search(r"\[(\d{1,2}\s*[-~]\s*\d{1,2}\s*节)\]", txt)
                if m:
                    sections = _tis_parse_sections(m.group(1))
            if not weekday:
                m = re.search(r"\[(?:周|星期)([一二三四五六日天])\]", txt)
                if m:
                    weekday = _tis_parse_weekday(m.group(0))

            if not location:
                m = re.search(r"\[([^\[\]]*(?:楼|教|场|室|房|馆|地点)[^\[\]]*)\]", txt)
                if m:
                    location = m.group(1).strip()

        if not weekday or not sections or not weeks or not course_name:
            continue

        start_sec, end_sec = sections
        kind: Literal["lecture", "experiment", "other"] = "lecture"
        name_lower = str(course_name).lower()
        if "实验" in str(course_name) or "lab" in name_lower:
            kind = "experiment"

        meetings.append(
            {
                "course_id": str(d.get("RWH") or d.get("rwh") or d.get("kch") or d.get("KCH") or d.get("courseCode") or course_name),
                "course_name": str(course_name),
                "weekday": weekday,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "weeks": weeks,
                "location": str(location or ""),
                "teacher": str(teacher) if teacher else None,
                "kind": kind,
            }
        )

    return meetings


def _tis_meetings_to_occurrences(meetings: list[dict[str, object]]) -> list[CourseOccurrence]:
    occs: list[CourseOccurrence] = []

    for m in meetings:
        weekday = int(m["weekday"])
        start_sec = int(m["start_sec"])
        end_sec = int(m["end_sec"])
        weeks = [int(x) for x in (m.get("weeks") or [])]

        if start_sec not in _SUSTECH_CLASS_PERIODS or end_sec not in _SUSTECH_CLASS_PERIODS:
            continue

        start_hhmm = _SUSTECH_CLASS_PERIODS[start_sec][0]
        end_hhmm = _SUSTECH_CLASS_PERIODS[end_sec][1]

        for w in weeks:
            day0 = _TIS_WEEK1_MONDAY + timedelta(days=(w - 1) * 7 + (weekday - 1))
            start_at = _tis_dt(day0, start_hhmm)
            end_at = _tis_dt(day0, end_hhmm)
            if end_at <= start_at:
                continue
            occs.append(
                CourseOccurrence(
                    course_id=str(m["course_id"]),
                    start_at=start_at,
                    end_at=end_at,
                    location=str(m.get("location") or ""),
                    kind=m.get("kind") or "lecture",
                    instructor=m.get("teacher"),
                    notes=str(m.get("course_name") or ""),
                )
            )

    occs.sort(key=lambda x: (x.start_at, x.course_id))
    return occs


async def fetch_course_schedule(cas_account: str, cas_password: str) -> list[CourseOccurrence]:
    """
    使用 CAS 认证登录教务系统，爬取当前学期固定课表。

    Args:
        cas_account:  CAS 账号
        cas_password: CAS 密码（已解密）

    Returns:
        list[CourseOccurrence]

    Raises:
        ConnectionError: 服务不可达
        PermissionError: 认证失败
    """
    _ensure_file_logging()

    service_url = f"{ACADEMIC_SYSTEM_BASE}/cas"
    main_url = f"{ACADEMIC_SYSTEM_BASE}/authentication/main"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(20.0),
        headers=headers,
        trust_env=False,
    ) as client:
        r0 = await _request_with_retry(client, "GET", main_url, label="tis.main")
        if "cas.sustech.edu.cn" in str(r0.url):
            await _cas_login(client, cas_account, cas_password, service_url)
            r0 = await _request_with_retry(client, "GET", main_url, label="tis.main.after_login")

        if r0.status_code >= 400:
            raise ConnectionError(f"Academic system unreachable: status={r0.status_code}")

        xhr_headers = {
            "Origin": ACADEMIC_SYSTEM_BASE,
            "Referer": main_url,
            "X-Requested-With": "XMLHttpRequest",
        }

        async def _tis_post(
            path: str,
            *,
            data: dict[str, str] | None = None,
            label: str,
        ) -> httpx.Response:
            url = f"{ACADEMIC_SYSTEM_BASE}{path}"
            req_headers = {**xhr_headers, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}

            r = await _request_with_retry(client, "POST", url, headers=req_headers, data=data or {}, label=label)
            if _tis_needs_auth_response(r):
                await _cas_login(client, cas_account, cas_password, service_url)
                r = await _request_with_retry(
                    client,
                    "POST",
                    url,
                    headers=req_headers,
                    data=data or {},
                    label=f"{label}.retry",
                )

            if _tis_needs_auth_response(r):
                raise PermissionError("TIS authentication required")

            return r

        r_term = await _tis_post("/component/querydangqianxnxq", label="tis.term")

        term_payload: object
        try:
            term_payload = r_term.json()
        except Exception:
            term_payload = r_term.text
            s = (term_payload or "").strip()
            if s.startswith("{") or s.startswith("["):
                try:
                    term_payload = json.loads(s)
                except Exception:
                    term_payload = r_term.text

        xn_xq = _tis_extract_xn_xq(term_payload)
        if not xn_xq:
            xn_xq = ("2025-2026", "2")
        xn, xq = xn_xq

        await _tis_post("/component/querysfxsbjkb", label="tis.sfxsbjkb")

        for ep, label in (
            ("/xszykb/queryxskbbz", "tis.kbbz"),
            ("/xszykb/querykbsffb", "tis.kbsffb"),
        ):
            await _tis_post(ep, data={"xn": xn, "xq": xq}, label=label)

        r_kb = await _tis_post("/xszykb/queryxszykbzong", data={"xn": xn, "xq": xq}, label="tis.kb.zong")

        try:
            kb_payload: object = r_kb.json()
        except Exception:
            kb_payload = r_kb.text
            s = (kb_payload or "").strip()
            if s.startswith("{") or s.startswith("["):
                try:
                    kb_payload = json.loads(s)
                except Exception:
                    kb_payload = r_kb.text

        meetings = _tis_extract_meetings(kb_payload)
        if not meetings:
            _tis_dump_test5(
                reason="meetings_empty",
                r_term=r_term,
                term_payload=term_payload,
                r_kb=r_kb,
                kb_payload=kb_payload,
                meetings_count=0,
            )
            if _tis_needs_auth_response(r_kb):
                raise PermissionError("TIS authentication required")
            raise RuntimeError("Academic schedule empty or unparseable")

        return _tis_meetings_to_occurrences(meetings)


def detect_conflicts(
    deadlines: list[Deadline],
    course_slots: list[CourseOccurrence],
) -> ScheduleData:
    """
    将截止时间列表与固定课表合并，检测时间冲突。
    纯本地逻辑，不访问网络。

    冲突定义：截止时间在某个固定课时的 2 小时内（即截止时间太紧，没有充足准备时间）。

    Args:
        deadlines:    fetch_blackboard 的返回值
        course_slots: fetch_course_schedule 的返回值

    Returns:
        ScheduleData，包含 events 列表（所有事件）和 conflicts 列表（检测到的冲突）
    """

    def _safe_id(prefix: str, raw: str) -> str:
        s = (raw or "").strip()
        s = re.sub(r"\s+", "_", s)
        if len(s) > 200:
            s = s[:200]
        return f"{prefix}:{s}" if s else prefix

    events_with_time: list[tuple[datetime, ScheduleEvent]] = []
    conflicts: list[ScheduleConflict] = []

    for o in course_slots or []:
        title = (o.notes or o.course_id or "").strip() or "Course"
        start = o.start_at
        end = o.end_at
        time_s = f"{start.isoformat()}~{end.isoformat()}"

        detail_parts: list[str] = [f"course_id={o.course_id}"]
        if o.location:
            detail_parts.append(f"location={o.location}")
        if o.instructor:
            detail_parts.append(f"instructor={o.instructor}")
        detail = " ".join(detail_parts)

        event = ScheduleEvent(
            event_id=_safe_id("tis", f"{o.course_id}:{start.isoformat()}"),
            title=title,
            time=time_s,
            source="教务系统",
            detail=detail,
        )
        events_with_time.append((start, event))

    window = timedelta(hours=2)

    for d in deadlines or []:
        title = (d.title or "").strip() or "Deadline"
        due = d.due_at
        time_s = due.isoformat()

        detail_parts: list[str] = [f"course_id={d.course_id}", f"type={d.type}"]
        if d.url:
            detail_parts.append(f"url={d.url}")
        detail = " ".join(detail_parts)

        raw_id = f"{d.course_id}:{due.isoformat()}:{d.url or title}"
        event = ScheduleEvent(
            event_id=_safe_id("bb", raw_id),
            title=title,
            time=time_s,
            source="Blackboard",
            detail=detail,
        )
        events_with_time.append((due, event))

        start_window = due - window
        for o in course_slots or []:
            if not (o.start_at < due and o.end_at > start_window):
                continue
            course_title = (o.notes or o.course_id or "").strip() or o.course_id
            slot_time = f"{o.start_at.isoformat()}~{o.end_at.isoformat()}"
            parts = [
                f"deadline_at={due.isoformat()}",
                f"course={course_title}",
                f"course_time={slot_time}",
            ]
            if o.location:
                parts.append(f"location={o.location}")
            conflicts.append(
                ScheduleConflict(
                    title=title,
                    detail=" ".join(parts),
                )
            )

    events_with_time.sort(key=lambda x: x[0])
    events = [e for _t, e in events_with_time]
    return ScheduleData(events=events, conflicts=conflicts)


async def refresh(db, user) -> ScheduleData:
    """
    完整刷新流程：爬取 + 冲突检测 + 结果返回。
    供 /api/schedule/refresh 路由调用。

    Args:
        db:   数据库 Session（当前版本暂不写入 DB，后续可缓存）
        user: User ORM 对象（用于解密 CAS 凭据）

    Returns:
        最新的 ScheduleData
    """
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

    deadlines, slots = await asyncio.gather(
        fetch_blackboard(cas_account, cas_password),
        fetch_course_schedule(cas_account, cas_password),
    )
    return detect_conflicts(deadlines, slots)

# ---------------------------------------------------------------------------
# Re-export public API from split modules (override in-file definitions)
from .constants import Deadline, Course, CourseOccurrence
from .fetch_bb import fetch_blackboard
from .fetch_tis import fetch_course_schedule
from .conflicts import detect_conflicts
from .refresh import refresh

__all__ = [
    "Deadline",
    "Course",
    "CourseOccurrence",
    "fetch_blackboard",
    "fetch_course_schedule",
    "detect_conflicts",
    "refresh",
]

