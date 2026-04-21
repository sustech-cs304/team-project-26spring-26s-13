import asyncio
import contextvars
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from urllib.parse import urljoin

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment]

try:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.common.by import By
except ModuleNotFoundError:  # pragma: no cover
    webdriver = None  # type: ignore[assignment]
    WebDriverException = Exception  # type: ignore[assignment]
    By = None  # type: ignore[assignment]


@dataclass
class Deadline:
    title: str
    course_id: str
    due_at: datetime
    type: Literal["assignment", "quiz", "project", "presentation", "other"]
    course_name: str | None = None
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
    notes: str | None = None


BLACKBOARD_BASE = "https://bb.sustech.edu.cn"
ACADEMIC_SYSTEM_BASE = "https://tis.sustech.edu.cn"

logger = logging.getLogger(__name__)


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


_bb_sink_var: contextvars.ContextVar[list[tuple[str, str, int, int, str]] | None] = contextvars.ContextVar(
    "bb_sink",
    default=None,
)

_CAS_COOKIE_CACHE_TTL_SECONDS = 10 * 60.0
_CAS_COOKIE_CACHE: dict[str, tuple[float, list[tuple[str, str, str, str]]]] = {}
_CAS_COOKIE_CACHE_LOCK = threading.RLock()


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


def _is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code <= 599


def _backoff_seconds(attempt: int) -> float:
    return 0.5 * (2 ** (attempt - 1))


def _request_error_summary(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _cas_cookie_cache_key(cas_account: str) -> str:
    return (cas_account or "").strip().lower()


def _export_cookies(cookies: httpx.Cookies) -> list[tuple[str, str, str, str]]:
    exported: list[tuple[str, str, str, str]] = []
    jar = getattr(cookies, "jar", None)
    if jar is None:
        return exported

    for cookie in jar:
        name = getattr(cookie, "name", "") or ""
        value = getattr(cookie, "value", "") or ""
        domain = getattr(cookie, "domain", "") or ""
        path = getattr(cookie, "path", "") or "/"
        if not name:
            continue
        exported.append((name, value, domain, path))
    return exported


def _apply_cookie_state(cookies: httpx.Cookies, state: list[tuple[str, str, str, str]]) -> None:
    for name, value, domain, path in state:
        kwargs: dict[str, str] = {"path": path or "/"}
        if domain:
            kwargs["domain"] = domain
        cookies.set(name, value, **kwargs)


def _apply_cached_cas_cookies(client: httpx.AsyncClient, cas_account: str) -> bool:
    cache_key = _cas_cookie_cache_key(cas_account)
    if not cache_key:
        return False

    with _CAS_COOKIE_CACHE_LOCK:
        entry = _CAS_COOKIE_CACHE.get(cache_key)
        if entry is None:
            return False

        cached_at, state = entry
        age_seconds = time.monotonic() - cached_at
        if age_seconds >= _CAS_COOKIE_CACHE_TTL_SECONDS:
            _CAS_COOKIE_CACHE.pop(cache_key, None)
            logger.info("cas.cookie_cache: expired key=%s age_seconds=%.3f", cache_key, age_seconds)
            return False

    _apply_cookie_state(client.cookies, state)
    logger.info("cas.cookie_cache: applied key=%s cookie_count=%d", cache_key, len(state))
    return True


def _store_cas_cookie_cache(cas_account: str, cookies: httpx.Cookies) -> None:
    cache_key = _cas_cookie_cache_key(cas_account)
    if not cache_key:
        return

    state = _export_cookies(cookies)
    if not state:
        return

    with _CAS_COOKIE_CACHE_LOCK:
        _CAS_COOKIE_CACHE[cache_key] = (time.monotonic(), state)

    logger.info("cas.cookie_cache: stored key=%s cookie_count=%d", cache_key, len(state))


def _clear_cas_cookie_cache(cas_account: str | None = None) -> None:
    if cas_account is None:
        with _CAS_COOKIE_CACHE_LOCK:
            _CAS_COOKIE_CACHE.clear()
        logger.info("cas.cookie_cache: cleared all")
        return

    cache_key = _cas_cookie_cache_key(cas_account)
    if not cache_key:
        return

    with _CAS_COOKIE_CACHE_LOCK:
        _CAS_COOKIE_CACHE.pop(cache_key, None)
    logger.info("cas.cookie_cache: cleared key=%s", cache_key)


def _cas_error_message(resp: httpx.Response) -> str:
    page_title = ""
    err_text = ""

    try:
        html = resp.text or ""
    except Exception:
        html = ""

    try:
        if BeautifulSoup is not None and html:
            soup = BeautifulSoup(html, "html.parser")
            if soup.title:
                page_title = soup.title.get_text(" ", strip=True)
            candidates = [
                soup.find(attrs={"role": "alert"}),
                soup.select_one(".errors, .error, .alert, .alert-danger, .alert-error"),
                soup.find(id=re.compile(r"^(error|errors|msg|message)$", re.I)),
                soup.find(class_=re.compile(r"\b(error|errors|alert|msg|message)\b", re.I)),
            ]
            for node in candidates:
                if node:
                    txt = node.get_text(" ", strip=True)
                    if txt:
                        err_text = txt
                        break
    except Exception:
        page_title = ""
        err_text = ""

    if not err_text and re.search(r"captcha|验证码", html, re.I):
        err_text = "captcha required"

    msg = "CAS authentication failed"
    if page_title:
        msg = f"{msg} ({page_title})"
    if err_text:
        msg = f"{msg}: {err_text}"
    return msg


def _cas_requires_browser_verification(message: str) -> bool:
    text = (message or "").lower()
    keywords = (
        "captcha",
        "verify",
        "verification",
        "browser",
        "challenge",
        "二次验证",
        "验证码",
        "人机验证",
        "浏览器",
    )
    return any(keyword in text for keyword in keywords)


def _is_truthy_env(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _create_selenium_driver() -> object:
    if webdriver is None:
        raise RuntimeError("selenium is not installed")

    browser = (os.getenv("SUSTECH_CAS_BROWSER") or "edge").strip().lower()
    last_error: Exception | None = None

    for candidate in [browser, "edge", "chrome"]:
        try:
            if candidate == "edge":
                options = webdriver.EdgeOptions()
                options.add_argument("--start-maximized")
                return webdriver.Edge(options=options)
            if candidate == "chrome":
                options = webdriver.ChromeOptions()
                options.add_argument("--start-maximized")
                return webdriver.Chrome(options=options)
        except Exception as exc:
            last_error = exc
            if candidate == browser:
                logger.warning("cas.browser: failed to start requested browser=%s err=%s", candidate, exc)

    raise RuntimeError(f"unable to start selenium browser: {last_error}")


def _copy_browser_cookies_to_client(driver: object, client: httpx.AsyncClient) -> None:
    for cookie in driver.get_cookies():
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        if not name:
            continue
        kwargs: dict[str, str] = {"path": str(cookie.get("path") or "/")}
        domain = str(cookie.get("domain") or "").strip()
        if domain:
            kwargs["domain"] = domain
        client.cookies.set(name, value, **kwargs)


async def _manual_cas_browser_login(
    client: httpx.AsyncClient,
    *,
    cas_account: str,
    cas_password: str,
    service_url: str,
) -> None:
    if not _is_truthy_env("SUSTECH_CAS_BROWSER_FALLBACK"):
        raise PermissionError(
            "CAS requires browser verification; set SUSTECH_CAS_BROWSER_FALLBACK=1 to enable selenium fallback"
        )

    login_url = str(httpx.URL("https://cas.sustech.edu.cn/cas/login").copy_merge_params({"service": service_url}))
    timeout_seconds = float(os.getenv("SUSTECH_CAS_BROWSER_TIMEOUT_SECONDS", "180"))
    driver = None

    try:
        driver = _create_selenium_driver()
        logger.warning("cas.browser: launching interactive browser fallback service=%s", service_url)
        driver.get(login_url)

        if By is not None:
            username_candidates = [
                (By.NAME, "username"),
                (By.NAME, "user"),
                (By.NAME, "userid"),
            ]
            password_candidates = [
                (By.NAME, "password"),
            ]

            for by, value in username_candidates:
                try:
                    elements = driver.find_elements(by, value)
                except Exception:
                    elements = []
                if elements:
                    try:
                        elements[0].clear()
                        elements[0].send_keys(cas_account)
                    except Exception:
                        pass
                    break

            for by, value in password_candidates:
                try:
                    elements = driver.find_elements(by, value)
                except Exception:
                    elements = []
                if elements:
                    try:
                        elements[0].clear()
                        elements[0].send_keys(cas_password)
                    except Exception:
                        pass
                    break

        deadline = time.monotonic() + max(timeout_seconds, 30.0)
        while time.monotonic() < deadline:
            current_url = ""
            try:
                current_url = str(driver.current_url or "")
            except Exception:
                current_url = ""

            if (
                ("bb.sustech.edu.cn" in current_url or "tis.sustech.edu.cn" in current_url)
                and "cas.sustech.edu.cn" not in current_url
            ):
                break

            await asyncio.sleep(1.0)
        else:
            raise TimeoutError("browser fallback timed out waiting for CAS verification")

        _copy_browser_cookies_to_client(driver, client)
        _store_cas_cookie_cache(cas_account, client.cookies)
    except WebDriverException as exc:
        raise RuntimeError(f"selenium browser fallback failed: {exc}") from exc
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


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


async def _cas_login_for_tis(client: httpx.AsyncClient, cas_account: str, cas_password: str, service_url: str) -> None:
    login_url = httpx.URL("https://cas.sustech.edu.cn/cas/login").copy_merge_params({"service": service_url})

    if _apply_cached_cas_cookies(client, cas_account):
        cached_resp = await _request_with_retry(client, "GET", service_url, label="cas.cookie_cache.validate")
        cached_url = str(cached_resp.url)
        if (
            cached_resp.status_code < 500
            and "cas.sustech.edu.cn" not in cached_url
            and not (
                "tis.sustech.edu.cn" in str(service_url)
                and "/authentication/require" in cached_url
            )
        ):
            return
        _clear_cas_cookie_cache(cas_account)

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

        if r2.status_code == 403:
            _clear_cas_cookie_cache(cas_account)
        r2.raise_for_status()

        if "cas.sustech.edu.cn" in str(r2.url) and "/cas/login" in str(r2.url):
            msg = _cas_error_message(r2)
            if _cas_requires_browser_verification(msg):
                await _manual_cas_browser_login(
                    client,
                    cas_account=cas_account,
                    cas_password=cas_password,
                    service_url=service_url,
                )
                return
            _clear_cas_cookie_cache(cas_account)
            raise PermissionError(msg)

        _store_cas_cookie_cache(cas_account, client.cookies)
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
                    _store_cas_cookie_cache(cas_account, client.cookies)
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

        if r2.status_code == 403:
            _clear_cas_cookie_cache(cas_account)
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
                    _store_cas_cookie_cache(cas_account, client.cookies)
                    return
                if r_home.status_code < 500 and "/cas/login" not in str(r_home.url):
                    _store_cas_cookie_cache(cas_account, client.cookies)
                    return
                if r_tab.status_code < 500 and "/cas/login" not in str(r_tab.url):
                    _store_cas_cookie_cache(cas_account, client.cookies)
                    return

        _bb_sink_dump(f"cas_login_{r2.status_code}")
        raise ConnectionError(f"CAS/SSO server error: status={r2.status_code} url={u2}")

    if r2.status_code == 403:
        _clear_cas_cookie_cache(cas_account)
    r2.raise_for_status()

    if "cas.sustech.edu.cn" in str(r2.url) and "/cas/login" in str(r2.url):
        msg = _cas_error_message(r2)
        if _cas_requires_browser_verification(msg):
            await _manual_cas_browser_login(
                client,
                cas_account=cas_account,
                cas_password=cas_password,
                service_url=service_url,
            )
            return
        _clear_cas_cookie_cache(cas_account)
        raise PermissionError(msg)

    _store_cas_cookie_cache(cas_account, client.cookies)


async def _cas_login_for_blackboard(
    client: httpx.AsyncClient,
    cas_account: str,
    cas_password: str,
    service_url: str,
) -> None:
    login_url = httpx.URL("https://cas.sustech.edu.cn/cas/login").copy_merge_params({"service": service_url})

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

    if _apply_cached_cas_cookies(client, cas_account):
        cached_resp = await _request_with_retry(client, "GET", service_url, headers=headers, label="cas.cookie_cache.validate")
        cached_url = str(cached_resp.url)
        if (
            cached_resp.status_code < 500
            and "cas.sustech.edu.cn" not in cached_url
            and not (
                "tis.sustech.edu.cn" in str(service_url)
                and "/authentication/require" in cached_url
            )
        ):
            return
        _clear_cas_cookie_cache(cas_account)

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

        inputs = list(form.find_all("input"))
        for inp in inputs:
            name = inp.get("name")
            if not name:
                continue
            payload[name] = inp.get("value") or ""

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

        if not username_field:
            username_field = "username"
        if not password_field:
            password_field = "password"

        payload[username_field] = cas_account
        payload[password_field] = cas_password
        payload.setdefault("_eventId", "submit")

        post_url = action if action.startswith("http") else urljoin(str(login_url), action)
        if (
            httpx.URL(post_url).host == login_url.host
            and httpx.URL(post_url).path == login_url.path
            and "service" not in httpx.URL(post_url).params
            and "service" in login_url.params
        ):
            post_url = httpx.URL(post_url).copy_merge_params({"service": login_url.params["service"]})

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

        if 300 <= r2.status_code < 400:
            location = r2.headers.get("Location", "")
            if "bb.sustech.edu.cn" in location:
                await _request_with_retry(client, "GET", location, headers=headers, label="bb.from_cas")
                await _request_with_retry(client, "GET", f"{BLACKBOARD_BASE}/", label="bb.warmup_after_login")
                _store_cas_cookie_cache(cas_account, client.cookies)
                return

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

        if r2.status_code == 403 and "tis.sustech.edu.cn" in str(service_url):
            _clear_cas_cookie_cache(cas_account)
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

    if last_r2 is None:
        raise ConnectionError("CAS login failed: no response")

    r2 = last_r2

    u2 = str(r2.url)
    if "bb.sustech.edu.cn" in u2:
        await _request_with_retry(client, "GET", u2, headers=headers, label="bb.from_cas")
        await _request_with_retry(client, "GET", f"{BLACKBOARD_BASE}/", label="bb.warmup_after_login")
        _store_cas_cookie_cache(cas_account, client.cookies)
        return

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
                    _store_cas_cookie_cache(cas_account, client.cookies)
                    return
                if r_home.status_code < 500 and "/cas/login" not in str(r_home.url):
                    _store_cas_cookie_cache(cas_account, client.cookies)
                    return
                if r_tab.status_code < 500 and "/cas/login" not in str(r_tab.url):
                    _store_cas_cookie_cache(cas_account, client.cookies)
                    return

        _bb_sink_dump(f"cas_login_{r2.status_code}")
        raise ConnectionError(f"CAS/SSO server error: status={r2.status_code} url={u2}")

    if r2.status_code == 403 and "tis.sustech.edu.cn" in str(service_url):
        _bb_sink_dump("tis_403")
        _clear_cas_cookie_cache(cas_account)
        raise ConnectionError(f"TIS forbidden after CAS login: status=403 url={u2}")

    if r2.status_code == 403:
        _clear_cas_cookie_cache(cas_account)
    r2.raise_for_status()

    if "cas.sustech.edu.cn" in u2 and "/cas/login" in u2:
        msg = _cas_error_message(r2)
        if _cas_requires_browser_verification(msg):
            await _manual_cas_browser_login(
                client,
                cas_account=cas_account,
                cas_password=cas_password,
                service_url=service_url,
            )
            return
        _clear_cas_cookie_cache(cas_account)
        raise PermissionError(msg)

    _store_cas_cookie_cache(cas_account, client.cookies)
