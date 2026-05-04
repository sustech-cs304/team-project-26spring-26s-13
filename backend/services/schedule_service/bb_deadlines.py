import asyncio
from datetime import datetime

import httpx

from .bb_auth import _blackboard_authenticated_session, _looks_like_transient_bb_500
from .bb_common import (
    _crawl_course_upload_urls,
    _crawl_portal_upload_urls,
    _extract_course_ids,
    _extract_upload_assignment_urls,
    _fetch_upload_urls_via_tool_activity_dwr,
    _parse_deadline_from_upload_assignment_html,
)
from .enums import DeadlineType
from .http_utils import _request_with_retry
from .log_utils import _bb_sink_dump, _bb_sink_var, _ensure_file_logging, logger
from .models import Deadline
from .service_config import BLACKBOARD_BASE


async def fetch_blackboard(cas_account: str, cas_password: str) -> list[Deadline]:
    _ensure_file_logging()
    logger.debug("bb.fetch: enter account=%s", cas_account)

    if not cas_account or not cas_password:
        logger.error(
            "bb.fetch: invalid credentials cas_account=%s password_len=%s",
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

            portal_course_ids, portal_upload_urls = await _crawl_portal_upload_urls(
                client,
                [tab_url, default_tab_url],
            )
            course_ids |= portal_course_ids

            seed_upload_urls = set(
                _extract_upload_assignment_urls(response.text, base_url)
            )
            upload_url_set: set[str] = set(seed_upload_urls)
            upload_url_set |= set(portal_upload_urls)

            dwr_urls = await _fetch_upload_urls_via_tool_activity_dwr(client, tab_url)
            upload_url_set |= set(dwr_urls)

            course_added = 0
            for course_id in sorted(course_ids):
                before = len(upload_url_set)
                course_urls = await _crawl_course_upload_urls(
                    client, course_id, tab_url
                )
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
                logger.warning(
                    "bb.fetch: no upload urls after seed+dwr+course crawl; running portal fallback"
                )
                portal_course_ids2, portal_upload_urls2 = (
                    await _crawl_portal_upload_urls(
                        client,
                        [tab_url, default_tab_url],
                    )
                )
                course_ids |= portal_course_ids2
                upload_url_set |= portal_upload_urls2
                for course_id in sorted(portal_course_ids2):
                    course_urls = await _crawl_course_upload_urls(
                        client, course_id, tab_url
                    )
                    upload_url_set |= course_urls
                upload_urls = sorted(upload_url_set)

            async def fetch_one(url: str) -> Deadline | None:
                try:
                    response = await _request_with_retry(
                        client,
                        "GET",
                        url,
                        headers={"Referer": tab_url, **headers},
                        label="bb.upload_assignment",
                    )
                except httpx.HTTPError as exc:
                    logger.warning(
                        "bb.fetch: request failed url=%s err=%s",
                        url,
                        type(exc).__name__,
                    )
                    return None

                if response.status_code >= 400:
                    if response.status_code == 500 and _looks_like_transient_bb_500(
                        response
                    ):
                        logger.warning("bb.fetch: transient 500 error on url=%s", url)
                        return None
                    logger.warning(
                        "bb.fetch: bad status=%s url=%s body_len=%d",
                        response.status_code,
                        url,
                        len(response.text or ""),
                    )
                    return None

                try:
                    return _parse_deadline_from_upload_assignment_html(
                        response.text, url
                    )
                except Exception as exc:
                    logger.exception(
                        "bb.fetch: parse failed url=%s err=%s body_preview=%s",
                        url,
                        type(exc).__name__,
                        (response.text or "")[:2000],
                    )
                    return None

            now_local = datetime.now()
            deadlines_raw = await asyncio.gather(
                *(fetch_one(url) for url in upload_urls)
            )
            deadlines = [
                deadline
                for deadline in deadlines_raw
                if deadline
                and deadline.type == DeadlineType.ASSIGNMENT
                and deadline.due_at
                and deadline.due_at >= now_local
            ]

            if not deadlines and upload_urls:
                logger.warning(
                    "bb.fetch: %d upload urls fetched but 0 parsed deadlines; trying portal+course refresh",
                    len(upload_urls),
                )
                portal_course_ids3, portal_upload_urls3 = (
                    await _crawl_portal_upload_urls(
                        client,
                        [tab_url, default_tab_url],
                    )
                )
                upload_url_set2 = set(upload_urls)
                upload_url_set2 |= portal_upload_urls3
                for course_id in sorted(portal_course_ids3):
                    course_urls = await _crawl_course_upload_urls(
                        client, course_id, tab_url
                    )
                    upload_url_set2 |= course_urls

                deadlines_raw2 = await asyncio.gather(
                    *(fetch_one(url) for url in sorted(upload_url_set2))
                )
                deadlines = [
                    deadline
                    for deadline in deadlines_raw2
                    if deadline
                    and deadline.type == DeadlineType.ASSIGNMENT
                    and deadline.due_at
                    and deadline.due_at >= now_local
                ]

            deadlines.sort(key=lambda item: item.due_at)
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
