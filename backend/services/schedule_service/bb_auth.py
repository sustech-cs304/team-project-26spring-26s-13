import asyncio
from contextlib import asynccontextmanager
import time
from urllib.parse import urljoin

import httpx

from .cas_auth import (
    _apply_cached_cas_cookies,
    _cas_login_for_blackboard,
    _clear_cas_cookie_cache,
    _store_cas_cookie_cache,
)
from .http_utils import _backoff_seconds, _request_with_retry
from .log_utils import logger
from .service_config import BLACKBOARD_BASE

DEFAULT_BLACKBOARD_HEADERS = {
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

_BB_COOKIE_CACHE: dict[str, tuple[float, list[tuple[str, str, str, str]]]] = {}
_BB_COOKIE_TTL_SECONDS = 15 * 60.0


def _looks_like_transient_bb_500(response: httpx.Response) -> bool:
    if response.status_code >= 500:
        return True
    url = str(response.url)
    return "/webapps/bb-sso-BBLEARN/execute/authValidate/customLogin" in url


def _export_cookies(cookies: httpx.Cookies) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    for cookie in cookies.jar:
        out.append((cookie.name, cookie.value, cookie.domain or "", cookie.path or "/"))
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


@asynccontextmanager
async def _blackboard_authenticated_session(
    cas_account: str,
    cas_password: str,
):
    service_url = f"{BLACKBOARD_BASE}/webapps/bb-sso-BBLEARN/index.jsp"
    tab_url = (
        f"{BLACKBOARD_BASE}/webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1"
    )
    default_tab_url = f"{BLACKBOARD_BASE}/webapps/portal/execute/defaultTab"

    headers = dict(DEFAULT_BLACKBOARD_HEADERS)
    cached = _BB_COOKIE_CACHE.get(cas_account)
    cookies: httpx.Cookies | None = None
    if cached and (time.time() - cached[0]) < _BB_COOKIE_TTL_SECONDS:
        cookies = _import_cookies(cached[1])

    async with httpx.AsyncClient(
        follow_redirects=True,
        headers=headers,
        timeout=10.0,
        trust_env=False,
        cookies=cookies,
    ) as client:
        _apply_cached_cas_cookies(client, cas_account)

        async def _bb_warmup(label_suffix: str) -> None:
            await _request_with_retry(
                client, "GET", service_url, label=f"bb.sso{label_suffix}"
            )
            await _request_with_retry(
                client, "GET", f"{BLACKBOARD_BASE}/", label=f"bb.home{label_suffix}"
            )
            await _request_with_retry(
                client,
                "GET",
                default_tab_url,
                label=f"bb.defaultTab{label_suffix}",
            )

        async def _frontdoor_home(label_suffix: str) -> httpx.Response:
            response = await _request_with_retry(
                client, "GET", f"{BLACKBOARD_BASE}/", label=f"bb.home{label_suffix}"
            )

            for _ in range(10):
                if not (300 <= response.status_code < 400):
                    break
                location = response.headers.get("Location") or ""
                if not location:
                    break
                location = urljoin(str(response.url), location)
                response = await _request_with_retry(
                    client, "GET", location, label=f"bb.redirect{label_suffix}"
                )

            return response

        async def _bb_open_frontdoor(label_suffix: str) -> httpx.Response:
            await _frontdoor_home(label_suffix)
            await _request_with_retry(
                client,
                "GET",
                default_tab_url,
                label=f"bb.defaultTab{label_suffix}",
            )
            return await _request_with_retry(
                client, "GET", tab_url, label=f"bb.tab{label_suffix}"
            )

        response = await _bb_open_frontdoor(".entry")

        if "cas.sustech.edu.cn" in str(response.url):
            logger.info("bb.fetch: redirected to CAS, starting login")
            _clear_cas_cookie_cache(cas_account)
            await _cas_login_for_blackboard(
                client, cas_account, cas_password, service_url
            )
            await _bb_warmup(".after_login")
            _store_cas_cookie_cache(cas_account, client.cookies)
            response = await _bb_open_frontdoor(".after_login")
            if "cas.sustech.edu.cn" in str(response.url):
                logger.warning(
                    "bb.fetch: still redirected to CAS after login, clearing CAS cache and retrying once"
                )
                _clear_cas_cookie_cache(cas_account)
                await _cas_login_for_blackboard(
                    client, cas_account, cas_password, service_url
                )
                await _bb_warmup(".after_relogin")
                _store_cas_cookie_cache(cas_account, client.cookies)
                response = await _bb_open_frontdoor(".after_relogin")

        if _looks_like_transient_bb_500(response):
            logger.warning(
                "bb.fetch: detected transient 500 error, attempting recovery"
            )
            _clear_cas_cookie_cache(cas_account)
            for attempt in range(1, 4):
                await asyncio.sleep(_backoff_seconds(attempt))
                await _bb_warmup(f".recover{attempt}")
                response = await _request_with_retry(
                    client, "GET", tab_url, label=f"bb.tab.recover{attempt}"
                )
                if "cas.sustech.edu.cn" in str(response.url):
                    logger.warning(
                        "bb.fetch: recovery redirected to CAS on attempt %d", attempt
                    )
                    _clear_cas_cookie_cache(cas_account)
                    await _cas_login_for_blackboard(
                        client, cas_account, cas_password, service_url
                    )
                    await _bb_warmup(f".recover{attempt}.after_login")
                    _store_cas_cookie_cache(cas_account, client.cookies)
                    response = await _request_with_retry(
                        client,
                        "GET",
                        tab_url,
                        label=f"bb.tab.recover{attempt}.after_login",
                    )
                if not _looks_like_transient_bb_500(response):
                    logger.info("bb.fetch: recovery successful on attempt %d", attempt)
                    break

        if _looks_like_transient_bb_500(response):
            error_id = response.headers.get(
                "X-Blackboard-errorid"
            ) or response.headers.get("x-blackboard-errorid")
            raise ConnectionError(
                f"Blackboard login unstable: status={response.status_code} url={str(response.url)} errorid={error_id or ''}".strip()
            )

        _BB_COOKIE_CACHE[cas_account] = (time.time(), _export_cookies(client.cookies))
        _store_cas_cookie_cache(cas_account, client.cookies)
        yield client, headers, tab_url, default_tab_url, response
