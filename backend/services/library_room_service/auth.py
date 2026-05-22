from __future__ import annotations

from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlparse

import httpx

from backend.services.schedule_service.cas_auth import (
    _apply_cached_cas_cookies,
    _cas_login_for_tis,
    _clear_cas_cookie_cache,
    _store_cas_cookie_cache,
)
from backend.services.schedule_service.http_utils import _request_with_retry

BOOKING_BASE = "https://booking.lib.sustech.edu.cn"
BOOKING_API_BASE = f"{BOOKING_BASE}/ic-web"
BOOKING_HOME = f"{BOOKING_BASE}/#/ic/home"
BOOKING_ERROR = f"{BOOKING_BASE}/#/error"

_COMMON_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
}


def _extract_service_url(address: str) -> str:
    parsed = urlparse(address)
    if "cas.sustech.edu.cn" not in parsed.netloc:
        return address
    service = parse_qs(parsed.query).get("service", [])
    return service[0] if service else address


async def _json_get(
    client: httpx.AsyncClient,
    path: str,
    *,
    params: dict[str, object] | None = None,
    label: str = "",
) -> dict:
    response = await _request_with_retry(
        client,
        "GET",
        f"{BOOKING_API_BASE}/{path.lstrip('/')}",
        headers=_COMMON_HEADERS,
        label=label or f"library.{path}",
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except Exception as exc:
        raise ConnectionError(f"Library booking API returned non-JSON: {path}") from exc
    return payload if isinstance(payload, dict) else {}


async def _booking_auth_address(client: httpx.AsyncClient) -> str | None:
    params = {
        "finalAddress": BOOKING_BASE,
        "errPageUrl": BOOKING_ERROR,
        "manager": "false",
        "consoleType": "16",
    }
    response = await client.get(
        f"{BOOKING_API_BASE}/auth/address",
        params=params,
        headers=_COMMON_HEADERS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("code") != 0:
        return None
    data = payload.get("data")
    return str(data).strip() if data else None


async def _refresh_user_token(client: httpx.AsyncClient) -> None:
    payload = await _json_get(client, "auth/userInfo", label="library.auth.userInfo")
    if payload.get("code") != 0:
        raise PermissionError(str(payload.get("message") or "Library CAS login failed"))
    data = payload.get("data")
    if isinstance(data, dict):
        token = str(data.get("token") or "").strip()
        if token:
            client.headers["token"] = token


async def _ensure_library_login(
    client: httpx.AsyncClient,
    cas_account: str,
    cas_password: str,
) -> None:
    _apply_cached_cas_cookies(client, cas_account)

    user_info = await _json_get(client, "auth/userInfo", label="library.auth.check")
    if user_info.get("code") == 0:
        data = user_info.get("data")
        if isinstance(data, dict) and data.get("token"):
            client.headers["token"] = str(data["token"])
        return

    _clear_cas_cookie_cache(cas_account)
    address = await _booking_auth_address(client)
    service_url = BOOKING_HOME
    if address:
        response = await client.get(address, headers=_COMMON_HEADERS)
        if "cas.sustech.edu.cn" in str(response.url):
            service_url = _extract_service_url(str(response.url))
        else:
            try:
                await _refresh_user_token(client)
                return
            except PermissionError:
                service_url = address
    await _cas_login_for_tis(client, cas_account, cas_password, service_url)
    _store_cas_cookie_cache(cas_account, client.cookies)
    await _refresh_user_token(client)


@asynccontextmanager
async def library_authenticated_session(
    cas_account: str,
    cas_password: str,
):
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(25.0),
        headers=dict(_COMMON_HEADERS),
    ) as client:
        await _ensure_library_login(client, cas_account, cas_password)
        yield client
