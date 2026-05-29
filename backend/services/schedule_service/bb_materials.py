import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
import gc
import json
import os
from pathlib import Path, PurePosixPath
import re
from urllib.parse import unquote, urljoin

import httpx
from bs4 import BeautifulSoup

from .bb_auth import _blackboard_authenticated_session
from .bb_common import (
    _crawl_portal_upload_urls,
    _discover_course_ids_via_my_courses,
    _extract_course_ids,
    _extract_course_name,
    _maybe_unquote_url,
)
from .http_utils import _request_with_retry
from .log_utils import (
    _bb_sink_dump,
    _bb_sink_var,
    _dump_failure_snapshot,
    _ensure_file_logging,
    _trace_filter,
    get_trace_id,
    is_diag_mode,
    logger,
)
from .service_config import BLACKBOARD_BASE

_COURSE_LISTCONTENT_REFERER_CACHE: dict[str, str] = {}


class BlackboardMaterialFetchError(RuntimeError):
    def __init__(
        self,
        step: str,
        url: str,
        *,
        course_id: str = "",
        content_id: str = "",
        referer: str = "",
        status_code: int | None = None,
        headers: dict[str, str] | None = None,
        body_snippet: str = "",
        cause: str = "",
    ) -> None:
        super().__init__(
            f"{step}: url={url} status={status_code or ''} {cause}".strip()
        )
        self.step = step
        self.url = url
        self.course_id = course_id
        self.content_id = content_id
        self.referer = referer
        self.status_code = status_code
        self.headers = headers or {}
        self.body_snippet = body_snippet
        self.cause = cause

    def to_debug_dict(self) -> dict[str, object]:
        return {
            "step": self.step,
            "url": self.url,
            "course_id": self.course_id,
            "content_id": self.content_id,
            "referer": self.referer,
            "status_code": self.status_code,
            "headers": self.headers,
            "body_snippet": self.body_snippet,
            "cause": self.cause,
        }


def _redact_headers(headers: dict[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    out: dict[str, str] = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk in {"cookie", "set-cookie", "authorization"}:
            out[k] = "<redacted>"
        else:
            out[k] = v
    return out


def _body_snippet(text: str | bytes | None, limit: int = 1200) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        try:
            s = text.decode("utf-8", errors="ignore")
        except Exception:
            s = ""
    else:
        s = text
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"(?i)\b(cookie|set-cookie)\b\s*:\s*.+", r"\1: <redacted>", s)
    s = s.strip()
    return s[:limit]


def _redirect_urls(response: httpx.Response) -> list[str]:
    urls: list[str] = []
    for r in getattr(response, "history", []) or []:
        try:
            urls.append(str(r.url))
        except Exception:
            continue
        loc = (r.headers.get("Location") or "").strip()
        if loc:
            try:
                urls.append(str(httpx.URL(str(r.url)).join(loc)))
            except Exception:
                pass
    try:
        urls.append(str(response.url))
    except Exception:
        pass
    out: list[str] = []
    seen: set[str] = set()
    for u in urls:
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def _looks_like_file_download(response: httpx.Response) -> bool:
    content_type = (response.headers.get("Content-Type") or "").lower()
    if response.status_code >= 400:
        return False
    if "text/html" in content_type or "text/x-json" in content_type:
        return False
    return bool(response.content)


@dataclass
class BlackboardMaterial:
    title: str
    course_id: str
    course_name: str | None
    content_id: str
    file_name: str
    file_type: str
    source_url: str
    download_url: str
    file_bytes: bytes
    skipped_reason: str = ""
    _tmp_path: str = ""


_CONTENT_FILE_VIEW_URL_RE = re.compile(
    r"(?:https?://bb\.sustech\.edu\.cn)?/webapps/blackboard/execute/content/file\?[^'\"\s<>]+",
    re.I,
)
_CMS_COURSE_FILE_URL_RE = re.compile(
    r"(?:https?://bb\.sustech\.edu\.cn)?/webapps/cmsmain/webui/courses/[^'\"\s<>]+",
    re.I,
)
_BBCSWEBDAV_URL_RE = re.compile(
    r"(?:https?://bb\.sustech\.edu\.cn)?/bbcswebdav/[^'\"\s<>]+",
    re.I,
)


def _is_content_file_view_url(url: str) -> bool:
    try:
        parsed = httpx.URL(url)
    except Exception:
        return False

    if "/webapps/blackboard/execute/content/file" not in parsed.path:
        return False

    cmd = (parsed.params.get("cmd") or "").lower()
    if cmd and cmd not in {"view", "download"}:
        return False

    return bool(parsed.params.get("content_id") and parsed.params.get("course_id"))


def _is_cms_course_file_url(url: str) -> bool:
    try:
        parsed = httpx.URL(url)
    except Exception:
        return False

    if "/webapps/cmsmain/webui/courses/" not in parsed.path:
        return False

    action = (parsed.params.get("action") or "").lower()
    if action and action not in {"details", "download"}:
        return False

    return bool(parsed.params.get("course_id"))


def _is_cms_course_path(url: str) -> bool:
    try:
        return "/webapps/cmsmain/webui/courses/" in httpx.URL(url).path
    except Exception:
        return False


def _check_course_semester_prune(
    course_id: str,
    urls: set[str],
    course_name: str = "",
) -> str:
    target_year = os.getenv("BB_TARGET_SEMESTER_YEAR", "2026")
    target_terms: set[str] = set(
        t
        for t in os.getenv("BB_TARGET_SEMESTER_TERMS", "SP,Spring,spring,春").split(",")
        if t
    )

    def _extract_semester(text: str) -> tuple[str, str] | None:
        m = re.search(
            r"-(\d{4})(SP|Spring|spring|春|FA|Fall|fall|秋|SU|Summer|summer|夏)?(?:[/\-]|$)",
            text,
        )
        if m:
            return m.group(1), m.group(2) or ""
        m = re.search(
            r"(\d{4})\s*(SP|Spring|spring|春|FA|Fall|fall|秋|SU|Summer|summer|夏)", text
        )
        if m:
            return m.group(1), m.group(2)
        return None

    for url in urls:
        parsed: httpx.URL | None = None
        try:
            parsed = httpx.URL(url)
        except Exception:
            continue
        path = parsed.path
        sem = _extract_semester(path)
        if not sem:
            query = (
                parsed.query.decode()
                if isinstance(parsed.query, bytes)
                else (parsed.query or "")
            )
            sem = _extract_semester(query)
        if not sem:
            continue
        year, term = sem
        if year == target_year and term in target_terms:
            return ""
        reason = f"semester={year}{term} (target={target_year}{','.join(sorted(target_terms))}) url={path[:120]}"
        logger.warning(
            "bb.materials: prune_semester course_id=%s %s trace=%s",
            course_id,
            reason,
            get_trace_id(),
        )
        return reason

    if course_name:
        sem = _extract_semester(course_name)
        if sem:
            year, term = sem
            if year == target_year and term in target_terms:
                return ""
            reason = f"semester={year}{term} from_name course_name={course_name[:80]}"
            logger.warning(
                "bb.materials: prune_semester course_id=%s %s trace=%s",
                course_id,
                reason,
                get_trace_id(),
            )
            return reason

    reason = "semester=unknown no semester info in any URL or course_name"
    logger.warning(
        "bb.materials: prune_semester course_id=%s %s trace=%s",
        course_id,
        reason,
        get_trace_id(),
    )
    return reason


def _ensure_course_id_param(url: str, course_id: str) -> str:
    if not course_id:
        return url
    try:
        parsed = httpx.URL(url)
    except Exception:
        return url
    if parsed.params.get("course_id"):
        return url
    try:
        return str(parsed.copy_add_param("course_id", course_id))
    except Exception:
        return url


def _extract_cms_course_file_urls(text: str, base_url: str) -> list[str]:
    urls: set[str] = set()
    for match in _CMS_COURSE_FILE_URL_RE.finditer(text or ""):
        raw = match.group(0)
        absolute_url = raw if raw.lower().startswith("http") else urljoin(base_url, raw)
        absolute_url = absolute_url.split("#", 1)[0]
        if not _is_cms_course_path(absolute_url):
            continue
        urls.add(absolute_url)
    return sorted(urls)


def _strip_query(url: str) -> str:
    try:
        parsed = httpx.URL(url)
    except Exception:
        return url
    try:
        return str(parsed.copy_with(query=b""))
    except Exception:
        return url.split("?", 1)[0]


def _iter_string_values(obj: object) -> list[str]:
    out: list[str] = []
    stack: list[object] = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, str):
            out.append(cur)
            continue
        if isinstance(cur, dict):
            stack.extend(cur.values())
            continue
        if isinstance(cur, list):
            stack.extend(cur)
            continue
    return out


def _extract_download_candidate_urls(text: str, base_url: str) -> list[str]:
    urls: set[str] = set()

    for match in _BBCSWEBDAV_URL_RE.finditer(text or ""):
        raw = match.group(0)
        absolute_url = raw if raw.lower().startswith("http") else urljoin(base_url, raw)
        urls.add(absolute_url.split("#", 1)[0])

    for match in _CONTENT_FILE_VIEW_URL_RE.finditer(text or ""):
        raw = match.group(0)
        absolute_url = raw if raw.lower().startswith("http") else urljoin(base_url, raw)
        absolute_url = absolute_url.split("#", 1)[0]
        if _is_content_file_view_url(absolute_url):
            urls.add(absolute_url)

    for match in _CMS_COURSE_FILE_URL_RE.finditer(text or ""):
        raw = match.group(0)
        absolute_url = raw if raw.lower().startswith("http") else urljoin(base_url, raw)
        absolute_url = absolute_url.split("#", 1)[0]
        if _is_cms_course_path(absolute_url):
            urls.add(absolute_url)

    return sorted(urls)


def _bbcswebdav_courses_url_from_cms_url(url: str) -> str:
    try:
        parsed = httpx.URL(url)
    except Exception:
        return ""

    raw_path = parsed.raw_path.split(b"?", 1)[0].decode("utf-8", errors="ignore")
    idx = raw_path.lower().find("/courses/")
    if idx < 0:
        return ""

    rel = raw_path[idx + len("/courses/") :].lstrip("/")
    if not rel:
        return ""

    return f"{BLACKBOARD_BASE}/bbcswebdav/courses/{rel}"


def _bbcswebdav_xid_urls(xythos_id: str) -> list[str]:
    xid = (xythos_id or "").strip()
    if not xid:
        return []
    candidates: list[str] = []
    if xid.lower().startswith("xid-"):
        candidates.append(f"{BLACKBOARD_BASE}/bbcswebdav/{xid}")
    else:
        candidates.append(f"{BLACKBOARD_BASE}/bbcswebdav/xid-{xid}")
    if xid.endswith("_1"):
        candidates.append(f"{BLACKBOARD_BASE}/bbcswebdav/xid-{xid[:-2]}")
    return list(dict.fromkeys(candidates))


def _extract_content_file_urls(text: str, base_url: str) -> list[str]:
    urls: set[str] = set()
    for match in _CONTENT_FILE_VIEW_URL_RE.finditer(text or ""):
        raw = match.group(0)
        absolute_url = raw if raw.lower().startswith("http") else urljoin(base_url, raw)
        absolute_url = absolute_url.split("#", 1)[0]
        if not _is_content_file_view_url(absolute_url):
            continue
        urls.add(absolute_url)
    return sorted(urls)


def _extract_content_id_from_url(url: str) -> str:
    try:
        return str(httpx.URL(url).params.get("content_id") or "").strip()
    except Exception:
        return ""


def _normalize_material_title(raw: str) -> str:
    title = " ".join((raw or "").split()).strip()
    if not title:
        return ""
    for prefix in ("文件：", "文件:", "File:", "Document:", "Item:"):
        if title.startswith(prefix):
            return title[len(prefix) :].strip()
    return title


def _extract_material_title(soup: BeautifulSoup) -> str:
    candidates: list[str] = []

    for element_id in ("pageTitleText", "crumb_3", "pageTitleHeader"):
        node = soup.find(id=element_id)
        if node:
            candidates.append(node.get_text(" ", strip=True))

    heading = soup.find("h1")
    if heading:
        candidates.append(heading.get_text(" ", strip=True))

    if soup.title:
        candidates.append(soup.title.get_text(" ", strip=True))

    for candidate in candidates:
        normalized = _normalize_material_title(candidate)
        if normalized:
            return normalized

    return ""


def _extract_bbcswebdav_url(text: str, base_url: str) -> str:
    for match in _BBCSWEBDAV_URL_RE.finditer(text or ""):
        raw = match.group(0)
        absolute_url = raw if raw.lower().startswith("http") else urljoin(base_url, raw)
        return absolute_url.split("#", 1)[0]
    return ""


def _filename_from_response(response: httpx.Response, fallback_title: str) -> str:
    final_url = str(response.url)
    name = PurePosixPath(unquote(httpx.URL(final_url).path)).name
    if name:
        return name
    title = " ".join((fallback_title or "").split()).strip()
    return title or "blackboard_file"


def _parse_blackboard_material_page(
    html: str, page_url: str
) -> tuple[str, str, str | None, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = _extract_material_title(soup)
    course_name = _extract_course_name(soup) or None
    content_id = _extract_content_id_from_url(page_url)
    download_url = _extract_bbcswebdav_url(html, page_url)
    return title, content_id, course_name, download_url


async def _fetch_cms_course_file_material(
    client: httpx.AsyncClient,
    page_url: str,
    referer: str,
    extra_headers: dict[str, str],
    *,
    strict: bool = False,
) -> BlackboardMaterial | None:
    try:
        parsed = httpx.URL(page_url)
        course_id = str(parsed.params.get("course_id") or "").strip()
        content_id = str(parsed.params.get("ctxMenuXythosId") or "").strip()
        file_name = PurePosixPath(unquote(parsed.path)).name
    except Exception:
        logger.debug("bb.material_cms: parse_url_failed url=%s", page_url)
        if strict:
            raise BlackboardMaterialFetchError("parse_url", page_url)
        return None

    if not course_id and referer:
        try:
            course_id = str(httpx.URL(referer).params.get("course_id") or "").strip()
        except Exception:
            course_id = course_id

    if not course_id:
        logger.debug(
            "bb.material_cms: missing_course_id url=%s file=%s", page_url, file_name
        )
        if strict:
            raise BlackboardMaterialFetchError(
                "missing_course_id",
                page_url,
                course_id=course_id,
                content_id=content_id,
                referer=referer,
            )
        return None

    file_name = file_name or "blackboard_file"
    title = PurePosixPath(file_name).stem or file_name
    content_id = content_id or file_name

    download_url = _bbcswebdav_courses_url_from_cms_url(page_url)
    menu_referer = referer or page_url
    if "/webapps/blackboard/content/listContent.jsp" in (menu_referer or ""):
        try:
            cached_course_id = str(
                httpx.URL(menu_referer).params.get("course_id") or ""
            ).strip()
        except Exception:
            cached_course_id = ""
        if cached_course_id:
            _COURSE_LISTCONTENT_REFERER_CACHE[cached_course_id] = menu_referer
    if "/webapps/blackboard/content/listContent.jsp" not in (menu_referer or ""):
        cached = _COURSE_LISTCONTENT_REFERER_CACHE.get(course_id)
        if cached:
            menu_referer = cached
        else:
            candidate = (
                f"{BLACKBOARD_BASE}/webapps/blackboard/content/listContent.jsp"
                f"?course_id={course_id}&mode=reset"
            )
            try:
                r = await _request_with_retry(
                    client,
                    "GET",
                    candidate,
                    headers={"Referer": referer} if referer else None,
                    label="bb.material_listcontent",
                )
                if r.status_code < 400:
                    final = str(r.url)
                    if "/webapps/blackboard/content/listContent.jsp" in final:
                        menu_referer = final
                        _COURSE_LISTCONTENT_REFERER_CACHE[course_id] = menu_referer
            except httpx.HTTPError:
                menu_referer = candidate

    download: httpx.Response | None = None

    raw_file_url = _strip_query(page_url)
    if raw_file_url and raw_file_url != page_url:
        try:
            candidate = await _request_with_retry(
                client,
                "GET",
                raw_file_url,
                headers={"Referer": menu_referer},
                label="bb.material_cms_raw",
            )
        except httpx.HTTPError:
            candidate = None
        if candidate is not None and _looks_like_file_download(candidate):
            download = candidate
            download_url = str(candidate.url)

    if content_id:
        for xid_url in _bbcswebdav_xid_urls(content_id):
            try:
                candidate = await _request_with_retry(
                    client,
                    "GET",
                    xid_url,
                    headers={"Referer": menu_referer},
                    label="bb.material_xid_asset",
                )
            except httpx.HTTPError:
                continue
            if _looks_like_file_download(candidate):
                download = candidate
                download_url = str(candidate.url)
                break

    if download is None:
        try:
            details_url = page_url
            try:
                details_parsed = httpx.URL(page_url)
                details_parsed = details_parsed.copy_set_param("action", "details")
                details_parsed = details_parsed.copy_remove_param("subaction")
                details_parsed = details_parsed.copy_remove_param("uniq")
                details_url = str(details_parsed)
            except Exception:
                details_url = page_url
            details = await _request_with_retry(
                client,
                "GET",
                details_url,
                headers={"Referer": menu_referer},
                label="bb.material_cms_details",
            )
        except httpx.HTTPError:
            details = None
        if details is not None and details.status_code < 400:
            extracted = _extract_bbcswebdav_url(details.text, str(details.url))
            if extracted:
                try:
                    candidate = await _request_with_retry(
                        client,
                        "GET",
                        extracted,
                        headers={"Referer": str(details.url)},
                        label="bb.material_asset",
                    )
                except httpx.HTTPError:
                    candidate = None
                if candidate is not None and _looks_like_file_download(candidate):
                    download = candidate
                    download_url = str(candidate.url)

    cms_download_candidates: list[str] = []
    try:
        cms_parsed = httpx.URL(page_url)
        if "/webapps/cmsmain/webui/courses/" in cms_parsed.path:
            try:
                u = cms_parsed.copy_set_param("action", "download")
                u = u.copy_remove_param("subaction")
                u = u.copy_remove_param("uniq")
                cms_download_candidates.append(str(u))
            except Exception:
                pass
    except Exception:
        pass

    for candidate_url in cms_download_candidates:
        try:
            candidate = await _request_with_retry(
                client,
                "GET",
                candidate_url,
                headers={"Referer": menu_referer},
                label="bb.material_cms_download",
            )
        except httpx.HTTPError:
            continue
        if _looks_like_file_download(candidate):
            download = candidate
            download_url = str(candidate.url)
            break
        for u in _redirect_urls(candidate):
            if "/bbcswebdav/" not in u:
                continue
            try:
                r2 = await _request_with_retry(
                    client,
                    "GET",
                    u,
                    headers={"Referer": menu_referer},
                    label="bb.material_cms_redirect_asset",
                )
            except httpx.HTTPError:
                continue
            if _looks_like_file_download(r2):
                download = r2
                download_url = str(r2.url)
                break
        if download is not None:
            break

    if download_url:
        try:
            candidate = await _request_with_retry(
                client,
                "GET",
                download_url,
                headers={"Referer": menu_referer},
                label="bb.material_asset",
            )
            content_type = (candidate.headers.get("Content-Type") or "").lower()
            if (
                candidate.status_code < 400
                and "text/html" not in content_type
                and "text/x-json" not in content_type
                and bool(candidate.content)
            ):
                download = candidate
                download_url = str(candidate.url)
        except httpx.HTTPError:
            download = None

    if download is None:
        menu_response: httpx.Response | None = None
        menu_url = page_url
        try:
            menu_parsed = httpx.URL(page_url)
            if (
                menu_parsed.params.get("subaction") or ""
            ).lower() != "generatefilemenuitem":
                menu_parsed = menu_parsed.copy_set_param("action", "details")
                menu_parsed = menu_parsed.copy_set_param(
                    "subaction", "generateFileMenuItem"
                )
                menu_url = str(menu_parsed)
        except Exception:
            menu_url = page_url
        try:
            menu = await _request_with_retry(
                client,
                "POST",
                menu_url,
                content="nav_item=&overwriteNavItems=",
                headers={
                    **extra_headers,
                    "Accept": "text/javascript, text/html, application/xml, text/xml, */*",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Origin": BLACKBOARD_BASE,
                    "Referer": menu_referer,
                    "X-Prototype-Version": "1.7",
                    "X-Requested-With": "XMLHttpRequest",
                },
                label="bb.material_menu",
            )
            menu_response = menu
        except httpx.HTTPError as exc:
            logger.debug(
                "bb.material_cms: menu_req_fail url=%s file=%s course=%s err=%s",
                page_url,
                file_name,
                course_id,
                type(exc).__name__,
            )
            if strict:
                raise BlackboardMaterialFetchError(
                    "menu_request_failed",
                    page_url,
                    course_id=course_id,
                    content_id=content_id,
                    referer=menu_referer,
                    cause=type(exc).__name__,
                ) from exc
            menu = None

        if menu is None or menu.status_code >= 400:
            logger.debug(
                "bb.material_cms: menu_status_fail url=%s file=%s course=%s status=%s",
                page_url,
                file_name,
                course_id,
                menu_response.status_code if menu_response else None,
            )
            if strict:
                raise BlackboardMaterialFetchError(
                    "menu_http_status",
                    page_url,
                    course_id=course_id,
                    content_id=content_id,
                    referer=menu_referer,
                    status_code=(menu_response.status_code if menu_response else None),
                    headers=_redact_headers(
                        dict(menu_response.headers) if menu_response else None
                    ),
                    body_snippet=_body_snippet(
                        menu_response.text if menu_response else None
                    ),
                )
            return None

        menu_text = menu.text if isinstance(menu.text, str) else ""
        extracted_urls: list[str] = []
        extracted_urls.extend(
            _extract_download_candidate_urls(menu_text, str(menu.url))
        )
        try:
            payload = json.loads(menu_text)
        except Exception:
            payload = None
        if payload is not None:
            for s in _iter_string_values(payload):
                extracted_urls.extend(
                    _extract_download_candidate_urls(s, str(menu.url))
                )
        extracted_urls = list(dict.fromkeys(extracted_urls))
        extracted = extracted_urls[0] if extracted_urls else ""

        if not extracted:
            r_ctx = None
            try:
                r_ctx = await _request_with_retry(
                    client,
                    "GET",
                    menu_referer,
                    headers={"Referer": referer} if referer else None,
                    label="bb.material_context",
                )
            except Exception:
                r_ctx = None

            ctx_html = r_ctx.text if r_ctx is not None else ""
            if ctx_html:
                needle_candidates = [file_name, content_id]
                for needle in needle_candidates:
                    if not needle:
                        continue
                    idx = ctx_html.lower().find(str(needle).lower())
                    if idx < 0:
                        continue
                    window = ctx_html[max(0, idx - 2000) : idx + 2000]
                    window_urls = _extract_download_candidate_urls(window, menu_referer)
                    if window_urls:
                        extracted_urls = window_urls
                        extracted = extracted_urls[0]
                        break
                if not extracted_urls:
                    ctx_urls = _extract_download_candidate_urls(ctx_html, menu_referer)
                    if ctx_urls:
                        extracted_urls = ctx_urls
                        extracted = extracted_urls[0]

        candidates = extracted_urls or ([extracted] if extracted else [])
        for candidate_url in candidates:
            if not candidate_url:
                continue
            try:
                candidate = await _request_with_retry(
                    client,
                    "GET",
                    candidate_url,
                    headers={"Referer": menu_referer},
                    label="bb.material_asset",
                )
            except httpx.HTTPError:
                continue
            if _looks_like_file_download(candidate):
                download = candidate
                download_url = str(candidate.url)
                break

        if download is None:
            logger.debug(
                "bb.material_cms: menu_no_dl url=%s file=%s course=%s "
                "extracted=%d candidates=%d ref=%s",
                page_url,
                file_name,
                course_id,
                len(extracted_urls),
                len(candidates),
                menu_referer[:80] if menu_referer else "none",
            )
            if strict:
                raise BlackboardMaterialFetchError(
                    "menu_no_download_url",
                    page_url,
                    course_id=course_id,
                    content_id=content_id,
                    referer=menu_referer,
                    status_code=menu.status_code,
                    headers=_redact_headers(dict(menu.headers)),
                    body_snippet=_body_snippet(menu_text),
                )
            return None

    if download is None:
        logger.debug(
            "bb.material_cms: no_download url=%s file=%s course=%s cid=%s",
            page_url,
            file_name,
            course_id,
            content_id,
        )
        _dump_failure_snapshot(
            label="cms_all_failed",
            url=page_url,
            status_code=None,
            response_headers=None,
            response_body=None,
            extra={
                "file_name": file_name,
                "course_id": course_id,
                "content_id": content_id,
            },
        )
        return None

    content_bytes = download.content
    if content_bytes:
        head = content_bytes[:128]
        if head.lstrip()[:1] == b"<" and (
            b"<html" in head[:256].lower() or b"<!doctype" in head[:256].lower()
        ):
            logger.debug(
                "bb.material_cms: html_not_file url=%s file=%s course=%s status=%d ct=%s",
                page_url,
                file_name,
                course_id,
                download.status_code,
                download.headers.get("Content-Type", ""),
            )
            _dump_failure_snapshot(
                label="cms_html_body",
                url=page_url,
                status_code=download.status_code,
                response_headers=dict(download.headers),
                response_body=content_bytes,
            )
            return None

    file_type = (
        (download.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    )
    actual_name = _filename_from_response(download, title)
    preferred_name = (file_name or "").strip()
    if preferred_name:
        lowered = actual_name.lower()
        if (
            lowered.startswith("xid-")
            or (("." not in actual_name) and ("." in preferred_name))
            or actual_name == content_id
        ):
            actual_name = preferred_name

    logger.debug(
        "bb.material_cms: success file=%s course=%s dl_url=%s",
        actual_name,
        course_id,
        download_url,
    )
    return BlackboardMaterial(
        title=title or actual_name,
        course_id=course_id,
        course_name=None,
        content_id=content_id,
        file_name=actual_name,
        file_type=file_type,
        source_url=page_url,
        download_url=download_url,
        file_bytes=download.content,
    )


async def _crawl_course_material_urls(
    client: httpx.AsyncClient,
    course_id: str,
    referer: str,
    course_name_cache: dict[str, str] | None = None,
) -> dict[str, str]:
    start_url = f"{BLACKBOARD_BASE}/webapps/blackboard/execute/launcher?type=Course&id={course_id}&url="
    to_visit: list[tuple[str, str]] = [(start_url, referer)]
    queued: set[str] = {start_url}
    visited: set[str] = set()
    material_urls: dict[str, str] = {}

    def add_material(u: str, ref: str) -> None:
        if not u:
            return
        material_urls.setdefault(u, ref or "")

    def enqueue(next_url: str, ref: str) -> None:
        if not next_url or not next_url.startswith(BLACKBOARD_BASE):
            return
        next_url = next_url.split("#", 1)[0]
        if next_url in visited or next_url in queued:
            return
        queued.add(next_url)
        to_visit.append((next_url, ref))

    seed_ref = referer or start_url
    enqueue(
        f"{BLACKBOARD_BASE}/webapps/blackboard/execute/courseMain?course_id={course_id}&task=true&src=",
        seed_ref,
    )
    for tool_id in ("_156_1", "_136_1"):
        enqueue(
            f"{BLACKBOARD_BASE}/webapps/blackboard/content/launchLink.jsp?course_id={course_id}&tool_id={tool_id}&tool_type=TOOL&mode=view",
            seed_ref,
        )

    while to_visit and len(visited) < 200 and len(material_urls) < 1200:
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
            label=f"bb.course_material_crawl:{course_id}",
        )
        if response.status_code >= 400:
            logger.warning(
                "bb.course_material_crawl: status=%d url=%s course_id=%s",
                response.status_code,
                str(response.url),
                course_id,
            )
            continue

        final_url = str(response.url)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")
        if course_name_cache is not None:
            try:
                extracted_course_name = _extract_course_name(soup)
            except Exception:
                extracted_course_name = ""
            if extracted_course_name:
                course_name_cache.setdefault(course_id, extracted_course_name)

        for material_url in _extract_content_file_urls(html, final_url):
            add_material(material_url, final_url)
        for cms_url in _extract_cms_course_file_urls(html, final_url):
            add_material(cms_url, final_url)
        raw_candidates: set[str] = set()

        for tag in soup.find_all(
            ["a", "area", "frame", "iframe", "link", "script", "form"]
        ):
            for attr in (
                "href",
                "data-href",
                "src",
                "action",
                "data-url",
                "data-action",
            ):
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

            if _is_content_file_view_url(absolute_url):
                add_material(absolute_url, final_url)
                continue

            if _is_cms_course_path(absolute_url):
                add_material(
                    _ensure_course_id_param(absolute_url, course_id), final_url
                )
                continue

            if (
                course_id not in absolute_url
                and f"course_id={course_id}" not in absolute_url
            ):
                if "/webapps/blackboard/content/listContent.jsp" not in absolute_url:
                    if "/webapps/blackboard/content/launchLink.jsp" not in absolute_url:
                        if "/webapps/blackboard/execute/courseMain" not in absolute_url:
                            if (
                                "/webapps/blackboard/execute/announcement"
                                not in absolute_url
                            ):
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

    _prune_reason = _check_course_semester_prune(
        course_id,
        set(material_urls.keys()),
        course_name_cache.get(course_id, "") if course_name_cache else "",
    )
    if _prune_reason:
        return {}

    logger.debug(
        "bb.materials: crawl_done course_id=%s material_urls=%d",
        course_id,
        len(material_urls),
    )
    return material_urls


async def fetch_blackboard_course_materials(
    cas_account: str,
    cas_password: str,
    *,
    course_keyword: str | None = None,
    keyword: str | None = None,
    limit: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[list[BlackboardMaterial], list[BlackboardMaterial]]:
    _ensure_file_logging()
    logger.debug("bb.materials: enter account=%s trace=%s", cas_account, get_trace_id())

    if not cas_account or not cas_password:
        logger.error(
            "bb.materials: invalid credentials cas_account=%s password_len=%s",
            bool(cas_account),
            len(cas_password or ""),
        )
        raise ValueError("Missing CAS credentials")

    token = _bb_sink_var.set([])
    try:
        async with _blackboard_authenticated_session(cas_account, cas_password) as (
            client,
            headers,
            tab_url,
            default_tab_url,
            response,
        ):
            base_url = str(response.url)
            course_ids = _extract_course_ids(response.text)

            extra_tabs = [
                f"{BLACKBOARD_BASE}/webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_{i}_1"
                for i in range(1, 7)
            ]
            safe_tab_url = _maybe_unquote_url(tab_url)
            safe_default_tab_url = _maybe_unquote_url(default_tab_url)
            portal_course_ids, _portal_upload_urls = await _crawl_portal_upload_urls(
                client,
                list(dict.fromkeys([safe_tab_url, safe_default_tab_url, *extra_tabs])),
            )
            course_ids |= portal_course_ids

            my_courses_ids = await _discover_course_ids_via_my_courses(client, headers)
            course_ids |= my_courses_ids
            logger.debug("bb.materials: my_courses_ids=%s", sorted(my_courses_ids))

            course_name_cache: dict[str, str] = {}
            material_url_map: dict[str, str] = {}

            def add_seed(u: str, ref: str) -> None:
                if not u:
                    return
                material_url_map.setdefault(u, ref or "")

            for u in _extract_content_file_urls(response.text, base_url):
                add_seed(u, base_url)
            for u in _extract_cms_course_file_urls(response.text, base_url):
                add_seed(u, base_url)
            logger.info("bb.materials: course_ids=%s", sorted(course_ids))
            for course_id in sorted(course_ids):
                logger.debug("bb.materials: crawling course_id=%s", course_id)
                found = await _crawl_course_material_urls(
                    client, course_id, tab_url, course_name_cache
                )
                for u, ref in found.items():
                    material_url_map.setdefault(u, ref)

            async def fetch_one(page_url: str) -> BlackboardMaterial | None:
                if not page_url:
                    return None
                ref = material_url_map.get(page_url) or tab_url
                try:
                    course_id_hint = str(
                        httpx.URL(page_url).params.get("course_id") or ""
                    ).strip()
                except Exception:
                    course_id_hint = ""
                if _is_cms_course_path(page_url):
                    normalized = (
                        _ensure_course_id_param(page_url, course_id_hint)
                        if course_id_hint
                        else page_url
                    )
                    try:
                        material = await _fetch_cms_course_file_material(
                            client,
                            normalized,
                            ref,
                            headers,
                        )
                        if (
                            material is not None
                            and not material.course_name
                            and course_id_hint
                        ):
                            material.course_name = course_name_cache.get(course_id_hint)  # type: ignore[misc]
                        return material
                    except RuntimeError as exc:
                        if "client has been closed" in str(exc).lower():
                            return None
                        raise

                try:
                    page = await _request_with_retry(
                        client,
                        "GET",
                        page_url,
                        headers={"Referer": ref, **headers},
                        label="bb.material_page",
                    )
                except httpx.HTTPError as exc:
                    logger.warning(
                        "bb.materials: page fetch failed url=%s err=%s",
                        page_url,
                        type(exc).__name__,
                    )
                    return None
                except RuntimeError as exc:
                    if "client has been closed" in str(exc).lower():
                        return None
                    raise

                if page.status_code >= 400:
                    logger.warning(
                        "bb.materials: page status=%d url=%s",
                        page.status_code,
                        page_url,
                    )
                    return None

                if _looks_like_file_download(page):
                    content_bytes = page.content
                    if content_bytes:
                        head = content_bytes[:128]
                        if head.lstrip()[:1] == b"<" and (
                            b"<html" in head[:256].lower()
                            or b"<!doctype" in head[:256].lower()
                        ):
                            logger.debug(
                                "bb.materials: html_not_file fetch_one url=%s "
                                "status=%d ct=%s",
                                page_url,
                                page.status_code,
                                page.headers.get("Content-Type", ""),
                            )
                            return None
                    try:
                        page_params = httpx.URL(page_url).params
                        course_id = str(page_params.get("course_id") or "").strip()
                        content_id = str(page_params.get("content_id") or "").strip()
                    except Exception:
                        course_id = ""
                        content_id = ""
                    if not course_id or not content_id:
                        return None
                    file_type = (
                        (page.headers.get("Content-Type") or "")
                        .split(";", 1)[0]
                        .strip()
                        .lower()
                    )
                    file_name = _filename_from_response(page, content_id)
                    return BlackboardMaterial(
                        title=file_name,
                        course_id=course_id,
                        course_name=course_name_cache.get(course_id),
                        content_id=content_id,
                        file_name=file_name,
                        file_type=file_type,
                        source_url=page_url,
                        download_url=str(page.url),
                        file_bytes=page.content,
                    )

                title, content_id, course_name, download_url = (
                    _parse_blackboard_material_page(page.text, page_url)
                )
                if not course_name and course_id_hint:
                    course_name = course_name_cache.get(course_id_hint)
                if not download_url:
                    logger.warning("bb.materials: no download url in page=%s", page_url)
                    return None

                try:
                    download = await _request_with_retry(
                        client,
                        "GET",
                        download_url,
                        headers={"Referer": page_url},
                        label="bb.material_asset",
                    )
                except httpx.HTTPError as exc:
                    logger.warning(
                        "bb.materials: asset fetch failed url=%s err=%s",
                        download_url,
                        type(exc).__name__,
                    )
                    return None
                except RuntimeError as exc:
                    if "client has been closed" in str(exc).lower():
                        return None
                    raise

                if download.status_code >= 400:
                    logger.warning(
                        "bb.materials: asset status=%d url=%s",
                        download.status_code,
                        download_url,
                    )
                    return None

                try:
                    page_params = httpx.URL(page_url).params
                    course_id = str(page_params.get("course_id") or "").strip()
                except Exception:
                    course_id = ""

                if not course_id or not content_id:
                    logger.warning(
                        "bb.materials: missing identifiers page=%s course_id=%s content_id=%s",
                        page_url,
                        course_id,
                        content_id,
                    )
                    return None

                file_type = (
                    (download.headers.get("Content-Type") or "")
                    .split(";", 1)[0]
                    .strip()
                    .lower()
                )
                file_name = _filename_from_response(download, title)
                return BlackboardMaterial(
                    title=title or file_name,
                    course_id=course_id,
                    course_name=course_name or course_name_cache.get(course_id),
                    content_id=content_id,
                    file_name=file_name,
                    file_type=file_type,
                    source_url=page_url,
                    download_url=str(download.url),
                    file_bytes=download.content,
                )

            material_pages = list(material_url_map.keys())
            desired = None
            if limit is not None:
                try:
                    desired = max(0, int(limit))
                except Exception:
                    desired = None

            course_kw = (course_keyword or "").strip().lower()
            file_kw = (keyword or "").strip().lower()

            def _score(u: str) -> tuple[int, object, str]:
                lu = u.lower()
                score = 0
                if file_kw and file_kw in lu:
                    score -= 2
                if course_kw and course_kw in lu:
                    score -= 1
                is_cms = 1 if _is_cms_course_path(u) else 0
                score -= is_cms
                if "2026sp" in lu or "2026-spring" in lu:
                    score -= 2
                return (score, (0 if is_cms else 1), lu)

            material_pages.sort(key=_score)

            if desired == 0:
                return []

            cms_candidates = sum(1 for u in material_pages if _is_cms_course_path(u))
            content_candidates = sum(
                1 for u in material_pages if _is_content_file_view_url(u)
            )
            logger.info(
                "bb.materials: candidates total=%d cms=%d content_file=%d",
                len(material_pages),
                cms_candidates,
                content_candidates,
            )

            scan_limit = desired or 50
            try:
                configured_scan_limit = int(
                    os.getenv("BB_MATERIAL_SCAN_LIMIT", "0").strip() or "0"
                )
            except Exception:
                configured_scan_limit = 0

            if configured_scan_limit > 0:
                scan_limit = configured_scan_limit
            elif desired is None:
                scan_limit = 9999
            elif file_kw or course_kw:
                scan_limit = max(120, scan_limit * 4)
                scan_limit = min(scan_limit, 9999)
            else:
                scan_limit = max(100, scan_limit * 3)
                scan_limit = min(scan_limit, 9999)

            material_pages = material_pages[:scan_limit]

            concurrency = 10
            try:
                concurrency = int(os.getenv("BB_MATERIAL_CONCURRENCY", "10").strip())
            except Exception:
                concurrency = 10
            concurrency = max(1, min(concurrency, 5))
            sem = asyncio.Semaphore(concurrency)
            batch_size = max(8, concurrency * 2)

            _MAX_FILE_MB = 40

            def _extract_url_filename(url: str) -> str:
                try:
                    path = httpx.URL(url).path
                    name = path.rstrip("/").rsplit("/", 1)[-1]
                    name = unquote(name)
                    if name and "." in name and not name.startswith("xid-"):
                        return name
                    qp = httpx.URL(url).params
                    xid = qp.get("ctxMenuXythosId") or qp.get("content_id") or ""
                    if xid:
                        return xid
                except Exception:
                    pass
                return url.rsplit("/", 1)[-1][:120]

            _SKIP_EXTENSIONS = {
                ".mp4",
                ".mov",
                ".avi",
                ".mkv",
                ".webm",
                ".flv",
                ".zip",
                ".rar",
                ".7z",
                ".tar",
                ".gz",
                ".bz2",
                ".iso",
                ".exe",
                ".msi",
                ".dmg",
                ".app",
                ".bin",
                ".dat",
                ".dll",
            }

            def _has_skip_extension(url: str) -> bool:
                try:
                    path = httpx.URL(url).path
                    name = unquote(path.rstrip("/").rsplit("/", 1)[-1])
                    dot = name.rfind(".")
                    if dot >= 0:
                        ext = name[dot:].lower()
                        return ext in _SKIP_EXTENSIONS
                except Exception:
                    pass
                return False

            async def _bound_fetch(u: str) -> BlackboardMaterial | None:
                async with sem:
                    fname = _extract_url_filename(u)
                    if _has_skip_extension(u):
                        logger.debug(
                            "bb.materials: skip_ext url=%s name=%s",
                            u,
                            fname,
                        )
                        return BlackboardMaterial(
                            title=fname,
                            course_id="",
                            course_name=None,
                            content_id="",
                            file_name=fname,
                            file_type="",
                            source_url=u,
                            download_url=u,
                            file_bytes=b"",
                            skipped_reason="unsupported_file_type",
                        )
                    try:
                        head = await client.head(
                            u,
                            headers=headers,
                            timeout=5.0,
                            follow_redirects=True,
                        )
                        cl = head.headers.get("Content-Length")
                        if cl:
                            size_mb = int(cl) / (1024 * 1024)
                            if size_mb > _MAX_FILE_MB:
                                fname = _extract_url_filename(u)
                                logger.debug(
                                    "bb.materials: skip_large url=%s name=%s size_mb=%.1f",
                                    u,
                                    fname,
                                    size_mb,
                                )
                                return BlackboardMaterial(
                                    title=fname,
                                    course_id="",
                                    course_name=None,
                                    content_id="",
                                    file_name=fname,
                                    file_type="",
                                    source_url=u,
                                    download_url=u,
                                    file_bytes=b"",
                                    skipped_reason=f"file_too_large ({size_mb:.1f}MB > {_MAX_FILE_MB}MB)",
                                )
                    except Exception:
                        pass
                    try:
                        _dl_t0 = _time2.monotonic()
                        fname_display = (fname or u)[:100]
                        logger.debug(
                            "bb.materials: dl_start url=%s",
                            u[:120],
                        )
                        result = await fetch_one(u)
                        _dl_elapsed = _time2.monotonic() - _dl_t0
                        status = "ok" if result else "failed"
                        logger.debug(
                            "bb.materials: dl_done status=%s elapsed=%.1fs url=%s",
                            status,
                            _dl_elapsed,
                            u[:120],
                        )
                        if result is None:
                            return BlackboardMaterial(
                                title=fname,
                                course_id="",
                                course_name=None,
                                content_id="",
                                file_name=fname,
                                file_type="",
                                source_url=u,
                                download_url=u,
                                file_bytes=b"",
                                skipped_reason="download_failed",
                            )
                        return result
                    except Exception:
                        return BlackboardMaterial(
                            title=fname,
                            course_id="",
                            course_name=None,
                            content_id="",
                            file_name=fname,
                            file_type="",
                            source_url=u,
                            download_url=u,
                            file_bytes=b"",
                            skipped_reason="download_failed",
                        )

            deduped: dict[tuple[str, str], BlackboardMaterial] = {}
            skipped: dict[str, BlackboardMaterial] = {}
            _flushed_keys: set[tuple[str, str]] = set()

            import uuid as _uuid

            _tmp_dir = Path(__file__).resolve().parents[3] / "temp" / "bb_bytes"
            _tmp_dir.mkdir(parents=True, exist_ok=True)
            for _old_tmp in _tmp_dir.glob("*.dat"):
                _old_tmp.unlink(missing_ok=True)

            def _flush_batch_to_disk() -> None:
                for key, mat in deduped.items():
                    if key in _flushed_keys:
                        continue
                    if not mat.file_bytes or mat.skipped_reason:
                        continue
                    tmp_name = f"{_uuid.uuid4().hex}.dat"
                    tmp_path = _tmp_dir / tmp_name
                    try:
                        tmp_path.write_bytes(mat.file_bytes)
                        mat._tmp_path = str(tmp_path)
                        mat.file_bytes = b""
                        _flushed_keys.add(key)
                    except Exception:
                        pass

            total_batches = (len(material_pages) + batch_size - 1) // batch_size
            for batch_start in range(0, len(material_pages), batch_size):
                batch = material_pages[batch_start : batch_start + batch_size]
                batch_num = batch_start // batch_size + 1
                logger.debug(
                    "bb.materials: batch_start batch=%d/%d urls=%d",
                    batch_num,
                    total_batches,
                    len(batch),
                )
                import time as _time2

                _batch_t0 = _time2.monotonic()
                tasks = [asyncio.create_task(_bound_fetch(url)) for url in batch]
                try:
                    raw_materials = await asyncio.gather(*tasks)
                finally:
                    for t in tasks:
                        if not t.done():
                            t.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                _batch_elapsed = _time2.monotonic() - _batch_t0
                for item in raw_materials:
                    if item is None:
                        continue
                    if item.skipped_reason:
                        skipped.setdefault(item.file_name, item)
                        continue
                    key = (item.course_id, item.content_id)
                    existing = deduped.get(key)
                    if existing is None or (
                        not existing.file_bytes and item.file_bytes
                    ):
                        deduped[key] = item
                raw_materials.clear()
                del raw_materials
                gc.collect()
                _flush_batch_to_disk()
                logger.debug(
                    "bb.materials: batch progress batch=%d/%d deduped=%d skipped=%d elapsed=%.1fs",
                    batch_start // batch_size + 1,
                    total_batches,
                    len(deduped),
                    len(skipped),
                    _batch_elapsed,
                )
                if progress_callback is not None:
                    try:
                        result = progress_callback(len(deduped), len(material_pages))
                        if asyncio.iscoroutine(result):
                            asyncio.ensure_future(result)
                    except Exception:
                        pass

            materials = sorted(
                deduped.values(),
                key=lambda item: (
                    (item.course_name or ""),
                    item.file_name.lower(),
                    item.content_id,
                ),
            )

            only_current_term = os.getenv(
                "BB_ONLY_CURRENT_TERM", "1"
            ).strip().lower() not in {"0", "false", "no", "off"}
            term_keywords_env = os.getenv("BB_TERM_KEYWORDS", "").strip()
            term_keywords: list[str] = []
            if term_keywords_env:
                term_keywords = [
                    k.strip().lower() for k in term_keywords_env.split(",") if k.strip()
                ]
            elif only_current_term:
                today = date.today()
                year = today.year
                is_spring = today.month <= 7
                if is_spring:
                    term_keywords = [
                        f"spring {year}",
                        f"{year} spring",
                        f"{year}春",
                        f"{year} spring ",
                        f"{year}sp",
                    ]
                else:
                    term_keywords = [
                        f"fall {year}",
                        f"{year} fall",
                        f"{year}秋",
                        f"{year} fall ",
                        f"{year}fa",
                    ]

            if term_keywords:
                strict_term_filter = os.getenv(
                    "BB_TERM_FILTER_STRICT", "1"
                ).strip().lower() not in {"0", "false", "no", "off"}
                filtered = [
                    item
                    for item in materials
                    if any(
                        k
                        in (
                            " ".join(
                                [
                                    str(item.course_name or ""),
                                    str(item.source_url or ""),
                                    str(item.download_url or ""),
                                ]
                            )
                        ).lower()
                        for k in term_keywords
                    )
                ]
                if filtered:
                    logger.info(
                        "bb.materials: term_filter keywords=%s before=%d after=%d",
                        ",".join(term_keywords),
                        len(materials),
                        len(filtered),
                    )
                    materials = filtered
                elif strict_term_filter:
                    logger.warning(
                        "bb.materials: term_filter empty keywords=%s before=%d strict=1",
                        ",".join(term_keywords),
                        len(materials),
                    )
                    materials = []
                else:
                    logger.warning(
                        "bb.materials: term_filter yielded 0 keywords=%s before=%d (returning unfiltered)",
                        ",".join(term_keywords),
                        len(materials),
                    )

            skipped_list = sorted(
                skipped.values(), key=lambda item: item.file_name.lower()
            )

            logger.info(
                "bb.materials: exit trace=%s raw_skipped=%d course_ids=%d pages=%d materials=%d skipped=%d",
                get_trace_id(),
                len(skipped),
                len(course_ids),
                len(material_pages),
                len(materials),
                len(skipped_list),
            )
            if not materials:
                _bb_sink_dump("materials_empty")
            return materials, skipped_list
    finally:
        try:
            _bb_sink_var.reset(token)
        except Exception:
            logger.exception("bb.materials: sink reset failed")
