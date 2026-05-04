import asyncio
from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from urllib.parse import unquote, urljoin

import httpx
from bs4 import BeautifulSoup

from .bb_auth import _blackboard_authenticated_session
from .bb_common import (
    _crawl_portal_upload_urls,
    _extract_course_ids,
    _extract_course_name,
)
from .http_utils import _request_with_retry
from .log_utils import _bb_sink_dump, _bb_sink_var, _ensure_file_logging, logger
from .service_config import BLACKBOARD_BASE


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


_CONTENT_FILE_VIEW_URL_RE = re.compile(
    r"(?:https?://bb\.sustech\.edu\.cn)?/webapps/blackboard/execute/content/file\?[^'\"\s<>]+",
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
    if cmd and cmd != "view":
        return False

    return bool(parsed.params.get("content_id") and parsed.params.get("course_id"))


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


async def _crawl_course_material_urls(
    client: httpx.AsyncClient,
    course_id: str,
    referer: str,
) -> set[str]:
    start_url = f"{BLACKBOARD_BASE}/webapps/blackboard/execute/launcher?type=Course&id={course_id}&url="
    to_visit: list[tuple[str, str]] = [(start_url, referer)]
    queued: set[str] = {start_url}
    visited: set[str] = set()
    material_urls: set[str] = set()

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

        for material_url in _extract_content_file_urls(html, final_url):
            material_urls.add(material_url)

        soup = BeautifulSoup(html, "html.parser")
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
                material_urls.add(absolute_url)
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

    return material_urls


async def fetch_blackboard_course_materials(
    cas_account: str, cas_password: str
) -> list[BlackboardMaterial]:
    _ensure_file_logging()
    logger.debug("bb.materials: enter account=%s", cas_account)

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

            portal_course_ids, _portal_upload_urls = await _crawl_portal_upload_urls(
                client,
                [tab_url, default_tab_url],
            )
            course_ids |= portal_course_ids

            material_url_set: set[str] = set(
                _extract_content_file_urls(response.text, base_url)
            )
            for course_id in sorted(course_ids):
                material_url_set |= await _crawl_course_material_urls(
                    client, course_id, tab_url
                )

            async def fetch_one(page_url: str) -> BlackboardMaterial | None:
                try:
                    page = await _request_with_retry(
                        client,
                        "GET",
                        page_url,
                        headers={"Referer": tab_url, **headers},
                        label="bb.material_page",
                    )
                except httpx.HTTPError as exc:
                    logger.warning(
                        "bb.materials: page fetch failed url=%s err=%s",
                        page_url,
                        type(exc).__name__,
                    )
                    return None

                if page.status_code >= 400:
                    logger.warning(
                        "bb.materials: page status=%d url=%s",
                        page.status_code,
                        page_url,
                    )
                    return None

                title, content_id, course_name, download_url = (
                    _parse_blackboard_material_page(page.text, page_url)
                )
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
                    course_name=course_name,
                    content_id=content_id,
                    file_name=file_name,
                    file_type=file_type,
                    source_url=page_url,
                    download_url=str(download.url),
                    file_bytes=download.content,
                )

            material_pages = sorted(material_url_set)
            raw_materials = await asyncio.gather(
                *(fetch_one(url) for url in material_pages)
            )
            deduped: dict[tuple[str, str], BlackboardMaterial] = {}
            for item in raw_materials:
                if item is None:
                    continue
                deduped[(item.course_id, item.content_id)] = item

            materials = sorted(
                deduped.values(),
                key=lambda item: (
                    (item.course_name or ""),
                    item.file_name.lower(),
                    item.content_id,
                ),
            )
            logger.info(
                "bb.materials: course_ids=%d pages=%d materials=%d",
                len(course_ids),
                len(material_pages),
                len(materials),
            )
            if not materials:
                _bb_sink_dump("materials_empty")
            return materials
    finally:
        try:
            _bb_sink_var.reset(token)
        except Exception:
            logger.exception("bb.materials: sink reset failed")
