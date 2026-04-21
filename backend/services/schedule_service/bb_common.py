from datetime import datetime
import re
import secrets
import time
from urllib.parse import unquote_plus, urljoin

import httpx
from bs4 import BeautifulSoup

from .http_utils import _request_with_retry
from .log_utils import logger
from .models import Deadline
from .service_config import BLACKBOARD_BASE


def _parse_due_at_zh_cn(text: str) -> datetime | None:
    raw = (text or "").strip()
    if not raw:
        return None

    match = re.search(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日.*?(上午|下午)\s*(\d{1,2}):(\d{2})",
        raw,
    )
    if match:
        year, month, day, ampm, hour_text, minute_text = match.groups()
        hour = int(hour_text)
        minute = int(minute_text)
        if ampm == "下午" and hour != 12:
            hour += 12
        if ampm == "上午" and hour == 12:
            hour = 0
        return datetime(int(year), int(month), int(day), hour, minute)

    match = re.search(
        r"\b(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T])(\d{1,2}):(\d{2})(?::(\d{2}))?\b",
        raw,
    )
    if match:
        year, month, day, hour_text, minute_text, _second = match.groups()
        return datetime(int(year), int(month), int(day), int(hour_text), int(minute_text))

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

    match = re.search(
        r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s*(\d{4})\s*(?:at\s*)?(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)\b",
        raw,
        re.I,
    )
    if match:
        month_text, day, year, hour_text, minute_text, _second, ampm = match.groups()
        month = month_map.get(month_text.strip().lower())
        if month is None:
            return None
        hour = int(hour_text)
        minute = int(minute_text)
        if ampm.upper() == "PM" and hour != 12:
            hour += 12
        if ampm.upper() == "AM" and hour == 12:
            hour = 0
        return datetime(int(year), int(month), int(day), hour, minute)

    match = re.search(
        r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\s*(AM|PM))?\b",
        raw,
        re.I,
    )
    if match:
        day, month_text, year, hour_text, minute_text, _second, ampm = match.groups()
        month = month_map.get(month_text.strip().lower())
        if month is None:
            return None
        hour = int(hour_text)
        minute = int(minute_text)
        if ampm:
            if ampm.upper() == "PM" and hour != 12:
                hour += 12
            if ampm.upper() == "AM" and hour == 12:
                hour = 0
        return datetime(int(year), int(month), int(day), hour, minute)

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
_UPLOAD_ASSIGNMENT_URL_RE = re.compile(
    r"(?:https?://bb\.sustech\.edu\.cn)?/webapps/assignment/uploadAssignment\?[^'\"\s<>]+",
    re.I,
)


def _extract_course_ids(text: str) -> set[str]:
    raw = text or ""
    ids = {match.group(1) for match in _COURSE_ID_RE.finditer(raw)}
    ids |= {match.group(1) for match in _COURSE_LAUNCHER_ID_RE.finditer(raw)}
    ids |= {match.group(1) for match in _COURSE_TYPE_ID_RE.finditer(raw)}
    ids |= {match.group(1) for match in _DATA_COURSE_ID_RE.finditer(raw)}

    try:
        decoded_text = unquote_plus(raw)
    except Exception:
        decoded_text = ""
    if decoded_text and decoded_text != raw:
        ids |= {match.group(1) for match in _COURSE_ID_RE.finditer(decoded_text)}
        ids |= {match.group(1) for match in _COURSE_LAUNCHER_ID_RE.finditer(decoded_text)}
        ids |= {match.group(1) for match in _COURSE_TYPE_ID_RE.finditer(decoded_text)}
        ids |= {match.group(1) for match in _DATA_COURSE_ID_RE.finditer(decoded_text)}

    return ids


def _is_upload_assignment_view_url(url: str) -> bool:
    try:
        parsed = httpx.URL(url)
    except Exception:
        return False

    if "action" in parsed.params and (parsed.params.get("action") or "").lower() == "showhistory":
        return False
    if "outcome_id" in parsed.params or "outcome_definition_id" in parsed.params:
        return False
    return bool(parsed.params.get("content_id"))


def _extract_upload_assignment_urls(text: str, base_url: str) -> list[str]:
    urls: set[str] = set()
    for match in _UPLOAD_ASSIGNMENT_URL_RE.finditer(text or ""):
        raw = match.group(0)
        absolute_url = raw if raw.lower().startswith("http") else urljoin(base_url, raw)
        absolute_url = absolute_url.split("#", 1)[0]
        if not _is_upload_assignment_view_url(absolute_url):
            continue
        urls.add(absolute_url)
    return sorted(urls)


def _make_dwr_ids() -> tuple[str, str]:
    http_session_id = secrets.token_hex(16).upper()
    suffix = int(time.time() * 1000) % 1000
    script_session_id = f"{secrets.token_hex(16).upper()}{suffix:03d}"
    return http_session_id, script_session_id


def _page_param_from_url(page_url: str) -> str:
    parsed = httpx.URL(page_url)
    path = parsed.path
    if parsed.query:
        path = f"{path}?{parsed.query.decode('utf-8', errors='ignore')}"
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

    response = await _request_with_retry(
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
    if response.status_code >= 400:
        logger.warning("bb.dwr: status=%d", response.status_code)
        return []

    urls = _extract_upload_assignment_urls(response.text, BLACKBOARD_BASE)
    if urls:
        return urls

    text = response.text
    pairs: set[tuple[str, str]] = set()
    for match in re.finditer(
        r"(?:contentId|content_id)\s*[:=]\s*['\"](?P<content>_\d+_\d+)['\"][\s\S]{0,300}?"
        r"(?:courseId|course_id)\s*[:=]\s*['\"](?P<course>_\d+_\d+)['\"]",
        text,
        re.I,
    ):
        pairs.add((match.group("content"), match.group("course")))

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
    to_visit: list[tuple[str, str | None]] = [(url, None) for url in start_urls]
    queued: set[str] = set(start_urls)
    visited: set[str] = set()
    upload_urls: set[str] = set()
    seen_course_ids: set[str] = set()

    def enqueue(next_url: str, referer: str | None) -> None:
        if not next_url or not next_url.startswith(BLACKBOARD_BASE):
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

        headers: dict[str, str] = {}
        if referer:
            headers["Referer"] = referer

        response = await _request_with_retry(
            client,
            "GET",
            url,
            headers=headers,
            label="bb.portal_crawl",
        )
        if response.status_code >= 400:
            logger.warning("bb.portal_crawl: status=%d url=%s", response.status_code, str(response.url))
            continue

        final_url = str(response.url)
        html = response.text

        for upload_url in _extract_upload_assignment_urls(html, final_url):
            upload_urls.add(upload_url)

        for course_id in _extract_course_ids(f"{final_url}\n{html}"):
            if course_id in seen_course_ids:
                continue
            seen_course_ids.add(course_id)
            enqueue(f"{BLACKBOARD_BASE}/webapps/blackboard/execute/courseMain?course_id={course_id}", final_url)

        soup = BeautifulSoup(html, "html.parser")
        raw_candidates: set[str] = set()

        for tag in soup.find_all(["a", "area", "frame", "iframe", "link", "script", "form"]):
            for attr in ("href", "data-href", "src", "action", "data-url", "data-action"):
                value = (tag.get(attr) or "").strip()
                if not value or value.lower().startswith("javascript:"):
                    continue
                raw_candidates.add(value)

            onclick = tag.get("onclick") or ""
            if onclick:
                for match in re.finditer(
                    r"(?:location\.href|window\.location|document\.location)\s*=\s*['\"]([^'\"]+)['\"]",
                    onclick,
                    re.I,
                ):
                    raw_candidates.add(match.group(1).strip())

        for match in re.finditer(
            r"(https?://bb\.sustech\.edu\.cn/[^'\"\s<>]+|/webapps/[^'\"\s<>]+)",
            html,
            re.I,
        ):
            raw_candidates.add(match.group(1).strip())

        for candidate in raw_candidates:
            absolute_url = urljoin(final_url, candidate)
            if not absolute_url.startswith(BLACKBOARD_BASE):
                continue
            absolute_url = absolute_url.split("#", 1)[0]

            if "/webapps/assignment/uploadAssignment" in absolute_url:
                if _is_upload_assignment_view_url(absolute_url):
                    upload_urls.add(absolute_url)
                continue
            if "/webapps/blackboard/content/launchLink.jsp" in absolute_url:
                enqueue(absolute_url, final_url)
                continue
            if "/webapps/blackboard/content/listContent.jsp" in absolute_url:
                enqueue(absolute_url, final_url)
                continue
            if "/webapps/blackboard/execute/announcement" in absolute_url:
                enqueue(absolute_url, final_url)
                continue
            if "/webapps/blackboard/execute/launcher" in absolute_url and "type=Course" in absolute_url:
                enqueue(absolute_url, final_url)
                continue
            if "/webapps/blackboard/execute/courseMain" in absolute_url:
                enqueue(absolute_url, final_url)
                continue
            if "/webapps/portal/execute/tabs/tabAction" in absolute_url:
                enqueue(absolute_url, final_url)
                continue
            if "/webapps/portal/execute/" in absolute_url:
                enqueue(absolute_url, final_url)
                continue

    return seen_course_ids, upload_urls


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

        response = await _request_with_retry(
            client,
            "GET",
            url,
            headers={"Referer": ref} if ref else None,
            label=f"bb.course_upload_crawl:{course_id}",
        )
        if response.status_code >= 400:
            logger.warning("bb.course_upload_crawl: status=%d url=%s course_id=%s", response.status_code, str(response.url), course_id)
            continue

        final_url = str(response.url)
        html = response.text

        for upload_url in _extract_upload_assignment_urls(html, final_url):
            upload_urls.add(upload_url)

        soup = BeautifulSoup(html, "html.parser")
        raw_candidates: set[str] = set()

        for tag in soup.find_all(["a", "area", "frame", "iframe", "link", "script", "form"]):
            for attr in ("href", "data-href", "src", "action", "data-url", "data-action"):
                value = (tag.get(attr) or "").strip()
                if not value:
                    continue
                if value.lower().startswith("javascript:"):
                    continue
                raw_candidates.add(value)

            onclick = tag.get("onclick") or ""
            if onclick:
                for match in re.finditer(
                    r"(?:location\.href|window\.location|document\.location)\s*=\s*['\"]([^'\"]+)['\"]",
                    onclick,
                    re.I,
                ):
                    raw_candidates.add(match.group(1).strip())

        for match in re.finditer(
            r"(https?://bb\.sustech\.edu\.cn/[^'\"\s<>]+|/webapps/[^'\"\s<>]+)",
            html,
            re.I,
        ):
            raw_candidates.add(match.group(1).strip())

        for candidate in raw_candidates:
            absolute_url = urljoin(final_url, candidate)
            if not absolute_url.startswith(BLACKBOARD_BASE):
                continue
            absolute_url = absolute_url.split("#", 1)[0]

            if "/webapps/assignment/uploadAssignment" in absolute_url:
                if _is_upload_assignment_view_url(absolute_url):
                    upload_urls.add(absolute_url)
                continue

            if course_id not in absolute_url and f"course_id={course_id}" not in absolute_url:
                if "/webapps/blackboard/content/listContent.jsp" not in absolute_url:
                    if "/webapps/blackboard/content/launchLink.jsp" not in absolute_url:
                        if "/webapps/blackboard/execute/courseMain" not in absolute_url:
                            if "/webapps/blackboard/execute/announcement" not in absolute_url:
                                continue

            if "/webapps/blackboard/content/listContent.jsp" in absolute_url:
                enqueue(absolute_url, final_url)
                continue
            if "/webapps/blackboard/content/launchLink.jsp" in absolute_url:
                enqueue(absolute_url, final_url)
                continue
            if "/webapps/blackboard/execute/announcement" in absolute_url:
                enqueue(absolute_url, final_url)
                continue
            if "/webapps/blackboard/execute/courseMain" in absolute_url:
                enqueue(absolute_url, final_url)
                continue

    return upload_urls


def _normalize_assignment_title(raw: str) -> str:
    title = " ".join((raw or "").split()).strip()
    if not title:
        return ""

    for prefix in (
        "上载作业：",
        "上载作业:",
        "Upload Assignment:",
        "Review Submission History:",
        "Review Submission History -",
    ):
        if title.startswith(prefix):
            return title[len(prefix):].strip()

    return title


def _extract_assignment_title(soup: BeautifulSoup) -> str:
    candidates: list[str] = []

    for element_id in ("pageTitleText", "crumb_3", "pageTitleHeader"):
        node = soup.find(id=element_id)
        if node:
            candidates.append(node.get_text(" ", strip=True))

    heading = soup.find("h1")
    if heading:
        candidates.append(heading.get_text(" ", strip=True))

    if soup.title:
        title_text = soup.title.get_text(" ", strip=True)
        match = re.match(r"^(?:上载作业：|上载作业:|Upload Assignment:)\s*(.*?)\s*[–-]\s*(.+)$", title_text)
        if match:
            candidates.append(match.group(1).strip())
        else:
            candidates.append(title_text)

    for candidate in candidates:
        normalized = _normalize_assignment_title(candidate)
        if normalized:
            return normalized

    return ""


def _extract_course_name(soup: BeautifulSoup) -> str:
    candidates: list[str] = []

    crumb = soup.find(id="crumb_1")
    if crumb:
        candidates.append(crumb.get_text(" ", strip=True))

    course_path_link = soup.select_one("li.coursePath a[title]")
    if course_path_link:
        candidates.append(course_path_link.get("title", ""))

    for candidate in candidates:
        normalized = " ".join((candidate or "").split()).strip()
        if normalized:
            return normalized

    return ""


def _parse_deadline_from_upload_assignment_html(html: str, page_url: str) -> Deadline | None:
    soup = BeautifulSoup(html, "html.parser")
    assignment_title = _extract_assignment_title(soup)
    course_name = _extract_course_name(soup)

    course_id: str | None = None
    match = re.search(r"\bstrCourseId\s*=\s*['\"]([^'\"]+)['\"]", html)
    if match:
        course_id = match.group(1).strip()
    if not course_id:
        match = re.search(r"\bstrCourseId=([^&'\"\s]+)", html)
        if match:
            course_id = match.group(1).strip()
    if course_id and "-" in course_id:
        course_id = course_id.split("-", 1)[0]

    if not course_id:
        try:
            parsed = httpx.URL(page_url)
            course_id = parsed.params.get("strCourseId") or parsed.params.get("course_id")
        except Exception:
            course_id = None

    due_at: datetime | None = None
    label = None
    for key in ("到期日期", "截止日期", "Due Date", "Due date"):
        label = soup.find("div", class_="metaLabel", string=lambda value, text=key: value and text in value)
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
        for pattern in patterns:
            match = re.search(pattern, page_text, re.I)
            if not match:
                continue
            due_at = _parse_due_at_zh_cn(match.group(0))
            if due_at:
                break

    if not due_at or not course_id:
        return None

    return Deadline(
        title=assignment_title,
        course_id=course_id,
        due_at=due_at,
        type="assignment",
        course_name=course_name or None,
        url=page_url,
    )
