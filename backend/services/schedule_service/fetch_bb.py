import asyncio
from datetime import datetime
import re
import secrets
import time
from urllib.parse import unquote_plus, urljoin

import httpx
from bs4 import BeautifulSoup

from .constants import (
    BLACKBOARD_BASE,
    Deadline,
    _apply_cached_cas_cookies,
    _backoff_seconds,
    _bb_sink_dump,
    _bb_sink_var,
    _clear_cas_cookie_cache,
    _cas_login_for_blackboard,
    _ensure_file_logging,
    _request_with_retry,
    _store_cas_cookie_cache,
    logger,
)


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

        for tag in soup.find_all(["a", "area", "frame", "iframe", "link", "script", "form"]):
            for attr in ("href", "data-href", "src", "action", "data-url", "data-action"):
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
                            if "/webapps/blackboard/execute/announcement" not in abs_url:
                                continue

            if "/webapps/blackboard/content/listContent.jsp" in abs_url:
                enqueue(abs_url, final_url)
                continue

            if "/webapps/blackboard/content/launchLink.jsp" in abs_url:
                enqueue(abs_url, final_url)
                continue

            if "/webapps/blackboard/execute/announcement" in abs_url:
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

        for course_id in _extract_course_ids(f"{final_url}\n{html}"):
            if course_id in seen_course_ids:
                continue
            seen_course_ids.add(course_id)
            enqueue(f"{BLACKBOARD_BASE}/webapps/blackboard/execute/courseMain?course_id={course_id}", final_url)

        soup = BeautifulSoup(html, "html.parser")
        raw_candidates: set[str] = set()

        for tag in soup.find_all(["a", "area", "frame", "iframe", "link", "script", "form"]):
            for attr in ("href", "data-href", "src", "action", "data-url", "data-action"):
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

            if "/webapps/blackboard/execute/announcement" in abs_url:
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
            title = title[len(prefix):].strip()
            break

    return title


def _extract_assignment_title(soup: BeautifulSoup) -> str:
    # Prefer in-page headings because browser <title> text may already be elided.
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
        m = re.match(r"^(?:上载作业：|上载作业:|Upload Assignment:)\s*(.*?)\s*[–-]\s*(.+)$", title_text)
        if m:
            candidates.append(m.group(1).strip())
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
        course_name=course_name or None,
        url=page_url,
    )


async def fetch_blackboard(cas_account: str, cas_password: str) -> list[Deadline]:
    _ensure_file_logging()
    logger.debug("bb.fetch: enter account=%s", cas_account)

    if not cas_account or not cas_password:
        logger.error("bb.fetch: invalid credentials cas_account=%s password_len=%s", bool(cas_account), len(cas_password or ""))
        raise ValueError("Missing CAS credentials")

    service_url = f"{BLACKBOARD_BASE}/webapps/bb-sso-BBLEARN/index.jsp"
    tab_url = f"{BLACKBOARD_BASE}/webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1"
    default_tab_url = f"{BLACKBOARD_BASE}/webapps/portal/execute/defaultTab"

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
            _apply_cached_cas_cookies(client, cas_account)

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

            r0 = await _bb_open_frontdoor(".entry")

            if "cas.sustech.edu.cn" in str(r0.url):
                logger.info("bb.fetch: redirected to CAS, starting login")
                _clear_cas_cookie_cache(cas_account)
                await _cas_login_for_blackboard(client, cas_account, cas_password, service_url)
                await _bb_warmup(".after_login")
                _store_cas_cookie_cache(cas_account, client.cookies)
                r0 = await _bb_open_frontdoor(".after_login")
                if "cas.sustech.edu.cn" in str(r0.url):
                    logger.warning("bb.fetch: still redirected to CAS after login, clearing CAS cache and retrying once")
                    _clear_cas_cookie_cache(cas_account)
                    await _cas_login_for_blackboard(client, cas_account, cas_password, service_url)
                    await _bb_warmup(".after_relogin")
                    _store_cas_cookie_cache(cas_account, client.cookies)
                    r0 = await _bb_open_frontdoor(".after_relogin")

            if _looks_like_transient_bb_500(r0):
                logger.warning("bb.fetch: detected transient 500 error, attempting recovery")
                _clear_cas_cookie_cache(cas_account)
                for attempt in range(1, 4):
                    await asyncio.sleep(_backoff_seconds(attempt))
                    await _bb_warmup(f".recover{attempt}")
                    r0 = await _request_with_retry(client, "GET", tab_url, label=f"bb.tab.recover{attempt}")
                    if "cas.sustech.edu.cn" in str(r0.url):
                        logger.warning("bb.fetch: recovery redirected to CAS on attempt %d", attempt)
                        _clear_cas_cookie_cache(cas_account)
                        await _cas_login_for_blackboard(client, cas_account, cas_password, service_url)
                        await _bb_warmup(f".recover{attempt}.after_login")
                        _store_cas_cookie_cache(cas_account, client.cookies)
                        r0 = await _request_with_retry(
                            client,
                            "GET",
                            tab_url,
                            label=f"bb.tab.recover{attempt}.after_login",
                        )
                    if not _looks_like_transient_bb_500(r0):
                        logger.info("bb.fetch: recovery successful on attempt %d", attempt)
                        break

            if _looks_like_transient_bb_500(r0):
                err_id = r0.headers.get("X-Blackboard-errorid") or r0.headers.get("x-blackboard-errorid")
                raise ConnectionError(
                    f"Blackboard login unstable: status={r0.status_code} url={str(r0.url)} errorid={err_id or ''}".strip()
                )

            _BB_COOKIE_CACHE[cas_account] = (time.time(), _export_cookies(client.cookies))
            _store_cas_cookie_cache(cas_account, client.cookies)

            base_url = str(r0.url)
            course_ids = _extract_course_ids(r0.text)

            portal_course_ids, portal_upload_urls = await _crawl_portal_upload_urls(
                client,
                [
                    tab_url,
                    default_tab_url,
                ],
            )

            course_ids |= portal_course_ids

            seed_upload_urls = set(_extract_upload_assignment_urls(r0.text, base_url))
            upload_url_set: set[str] = set(seed_upload_urls)
            upload_url_set |= set(portal_upload_urls)

            dwr_urls = await _fetch_upload_urls_via_tool_activity_dwr(client, tab_url)
            upload_url_set |= set(dwr_urls)

            course_added = 0
            for course_id in sorted(course_ids):
                before = len(upload_url_set)
                course_urls = await _crawl_course_upload_urls(client, course_id, tab_url)
                upload_url_set |= course_urls
                course_added += len(upload_url_set) - before

            upload_urls = sorted(upload_url_set)

            logger.info(
                "bb.fetch: base=%s course_ids=%d seed=%d portal=%d dwr=%d course_added=%d total=%d",
                base_url,
                len(course_ids),
                len(seed_upload_urls),
                len(portal_upload_urls),
                len(dwr_urls),
                course_added,
                len(upload_urls),
            )

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

            async def fetch_one(u: str) -> Deadline | None:
                try:
                    r = await _request_with_retry(
                        client,
                        "GET",
                        u,
                        headers={"Referer": tab_url, **headers},
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

            now_local = datetime.now()
            deadlines_raw = await asyncio.gather(*(fetch_one(u) for u in upload_urls))
            deadlines = [
                d
                for d in deadlines_raw
                if d and d.type == "assignment" and d.due_at and d.due_at >= now_local
            ]

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
