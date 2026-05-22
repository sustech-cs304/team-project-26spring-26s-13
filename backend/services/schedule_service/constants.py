import asyncio
import contextvars
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup


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
    notes: str | None = None


BLACKBOARD_BASE = "https://bb.sustech.edu.cn"
ACADEMIC_SYSTEM_BASE = "https://tis.sustech.edu.cn"

logger = logging.getLogger(__name__)

_CAS_COOKIE_CACHE: dict[str, tuple[float, list[tuple[str, str, str, str]]]] = {}
_CAS_COOKIE_TTL_SECONDS = float(os.getenv("SPA_CAS_COOKIE_TTL_SECONDS", "900"))
_CAS_BROWSER_WAIT_SECONDS = float(os.getenv("SPA_CAS_BROWSER_WAIT_SECONDS", "240"))
_CAS_BROWSER_FALLBACK_ENABLED = os.getenv("SPA_ENABLE_CAS_BROWSER_FALLBACK", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}
_cas_browser_login_lock: asyncio.Lock | None = None


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


def _cas_requires_browser_verification(message: str) -> bool:
    lowered = message.lower()
    return "browser-side human verification required" in lowered or "captcha required" in lowered


def _get_cas_browser_login_lock() -> asyncio.Lock:
    global _cas_browser_login_lock
    if _cas_browser_login_lock is None:
        _cas_browser_login_lock = asyncio.Lock()
    return _cas_browser_login_lock


def _cas_cookie_cache_dir() -> Path:
    root = Path(__file__).resolve().parents[3]
    path = root / "temp" / "cas_cookie_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cas_cookie_cache_path(cas_account: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", (cas_account or "").strip()) or "default"
    return _cas_cookie_cache_dir() / f"{safe}.bin"


def _export_cookie_state(cookies: httpx.Cookies) -> list[tuple[str, str, str, str]]:
    state: list[tuple[str, str, str, str]] = []
    for cookie in cookies.jar:
        state.append(
            (
                cookie.name,
                cookie.value,
                getattr(cookie, "domain", "") or "",
                getattr(cookie, "path", "") or "/",
            )
        )
    return state


def _merge_cookie_state_into_client(
    client: httpx.AsyncClient,
    state: list[tuple[str, str, str, str]],
) -> None:
    for name, value, domain, path in state:
        kwargs: dict[str, str] = {}
        if domain:
            kwargs["domain"] = domain
        if path:
            kwargs["path"] = path
        client.cookies.set(name, value, **kwargs)


def _store_cas_cookie_cache(cas_account: str, cookies: httpx.Cookies) -> None:
    if not cas_account:
        return
    state = _export_cookie_state(cookies)
    if not state:
        return
    _CAS_COOKIE_CACHE[cas_account] = (time.time(), state)
    try:
        from backend.utils.crypto import encrypt

        payload = json.dumps(
            {
                "stored_at": time.time(),
                "cookies": state,
            },
            ensure_ascii=False,
        )
        _cas_cookie_cache_path(cas_account).write_bytes(encrypt(payload))
    except Exception:
        logger.exception("cas.cookie: failed to persist cookie cache for account=%s", cas_account)


def _clear_cas_cookie_cache(cas_account: str) -> None:
    if cas_account:
        _CAS_COOKIE_CACHE.pop(cas_account, None)
    try:
        _cas_cookie_cache_path(cas_account).unlink(missing_ok=True)
    except Exception:
        logger.exception("cas.cookie: failed to clear persisted cache for account=%s", cas_account)


def _apply_cached_cas_cookies(client: httpx.AsyncClient, cas_account: str) -> bool:
    cached = _CAS_COOKIE_CACHE.get(cas_account)
    if not cached:
        try:
            from backend.utils.crypto import decrypt

            raw = _cas_cookie_cache_path(cas_account).read_bytes()
            payload = json.loads(decrypt(raw))
            cached = (float(payload.get("stored_at", 0.0)), list(payload.get("cookies", [])))
            _CAS_COOKIE_CACHE[cas_account] = cached
        except FileNotFoundError:
            return False
        except Exception:
            logger.exception("cas.cookie: failed to load persisted cache for account=%s", cas_account)
            _clear_cas_cookie_cache(cas_account)
            return False
    ts, state = cached
    if (time.time() - ts) >= _CAS_COOKIE_TTL_SECONDS:
        _clear_cas_cookie_cache(cas_account)
        return False
    _merge_cookie_state_into_client(client, state)
    return True


def _cas_error_message(response: httpx.Response) -> str:
    err_text = ""
    page_title = ""
    try:
        soup = BeautifulSoup(response.text, "html.parser")
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
        if not err_text:
            has_human_verification_input = bool(
                soup.find("input", attrs={"name": "g-recaptcha-response"})
                or soup.find("input", attrs={"id": "g-recaptcha-response"})
            )
            has_slide_verify_script = any(
                "slideVerify(" in (script.string or script.get_text(" ", strip=False) or "")
                for script in soup.find_all("script")
            )
            submit_button = soup.find("button", attrs={"id": "submit"}) or soup.find(
                "button",
                attrs={"name": "submit"},
            )
            submit_disabled = bool(
                submit_button
                and (
                    submit_button.has_attr("disabled")
                    or str(submit_button.get("disabled") or "").lower() in {"true", "disabled"}
                )
            )
            if has_human_verification_input and (has_slide_verify_script or submit_disabled):
                err_text = "browser-side human verification required"
            elif re.search(r"(请输入验证码|向右滑动完成验证|进行人机身份验证|Are you a robot)", response.text, re.I):
                err_text = "browser-side human verification required"
    except Exception:
        err_text = ""

    msg = "CAS authentication failed"
    if page_title:
        msg = f"{msg} ({page_title})"
    if err_text:
        msg = f"{msg}: {err_text}"
    return msg


def _manual_cas_browser_login_sync(
    *,
    cas_account: str,
    cas_password: str,
    service_url: str,
    wait_seconds: float,
    headless: bool = False,
) -> list[tuple[str, str, str, str]]:
    try:
        from selenium import webdriver
        from selenium.common.exceptions import WebDriverException
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.chrome.options import Options
    except Exception as exc:
        raise RuntimeError(f"Selenium unavailable: {type(exc).__name__}") from exc

    login_url = httpx.URL("https://cas.sustech.edu.cn/cas/login").copy_merge_params({"service": service_url})

    with tempfile.TemporaryDirectory(prefix="spa-cas-login-") as profile_dir:
        options = Options()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-search-engine-choice-screen")
        options.add_argument("--disable-popup-blocking")

        driver = None
        try:
            driver = webdriver.Chrome(options=options)
            driver.set_window_size(1280, 920)
            driver.get(str(login_url))

            try:
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
            except Exception as exc:
                raise RuntimeError("CAS login form did not load in Chrome") from exc

            inputs = driver.find_elements(By.CSS_SELECTOR, "input")
            password_input = None
            username_input = None
            fallback_text_inputs = []

            for inp in inputs:
                if not inp.is_displayed() or not inp.is_enabled():
                    continue
                input_type = (inp.get_attribute("type") or "").strip().lower()
                input_name = (inp.get_attribute("name") or "").strip().lower()
                if input_type == "password" and password_input is None:
                    password_input = inp
                    continue
                if input_type in {"text", "email", ""}:
                    fallback_text_inputs.append(inp)
                    if username_input is None and (
                        input_name in {"username", "user", "userid", "account"}
                        or "user" in input_name
                        or "account" in input_name
                    ):
                        username_input = inp

            if username_input is None and fallback_text_inputs:
                username_input = fallback_text_inputs[0]

            if username_input is None or password_input is None:
                raise RuntimeError("CAS username/password fields not found in Chrome")

            username_input.clear()
            username_input.send_keys(cas_account)
            password_input.clear()
            password_input.send_keys(cas_password)

            if sys.platform == "darwin":
                subprocess.run(
                    ["osascript", "-e", 'tell application "Google Chrome" to activate'],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            try:
                WebDriverWait(driver, 10).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                pass

            try:
                driver.execute_script(
                    """
                    const candidates = [
                      document.getElementById('su-recaptcha-btn'),
                      document.querySelector('#su-recaptcha .captcha-btn-text'),
                      document.querySelector('#su-recaptcha .captcha-btn-icon'),
                      document.getElementById('su-recaptcha'),
                    ].filter(Boolean);
                    if (candidates.length > 0) {
                      candidates[0].click();
                      return true;
                    }
                    return false;
                    """
                )
            except Exception:
                pass

            submit_clicked = False
            deadline = time.monotonic() + wait_seconds
            while time.monotonic() < deadline:
                try:
                    current_url = driver.current_url
                except WebDriverException as exc:
                    raise RuntimeError("Chrome window was closed before CAS verification completed") from exc

                if current_url and not ("cas.sustech.edu.cn" in current_url and "/cas/login" in current_url):
                    # 检查是否由于反爬或频率限制导致 403
                    page_lower = driver.page_source.lower()
                    if "forbidden" in page_lower or "403" in page_lower:
                         # 如果是静默模式遇到 403，让它超时，从而触发有界面模式供用户观察
                        time.sleep(1.0)
                        continue

                    # 关键修复：等待目标系统（TIS/BB）完成重定向并设置 Session Cookies
                    time.sleep(2.0)
                    cookies = driver.get_cookies()
                    return [
                        (
                            str(cookie.get("name") or ""),
                            str(cookie.get("value") or ""),
                            str(cookie.get("domain") or ""),
                            str(cookie.get("path") or "/"),
                        )
                        for cookie in cookies
                        if cookie.get("name")
                    ]

                try:
                    submit_state = driver.execute_script(
                        """
                        const btn = document.getElementById('submit');
                        if (!btn) return null;
                        return {
                          disabled: !!btn.disabled,
                          ariaDisabled: btn.getAttribute('aria-disabled') || '',
                          text: btn.innerText || btn.textContent || ''
                        };
                        """
                    )
                    verification_token = driver.execute_script(
                        """
                        const input = document.getElementById('g-recaptcha-response');
                        return input ? (input.value || '') : '';
                        """
                    )
                except WebDriverException:
                    submit_state = None
                    verification_token = ""

                if submit_state and not bool(submit_state.get("disabled")):
                    if not submit_clicked:
                        driver.execute_script(
                            """
                            const btn = document.getElementById('submit');
                            if (btn && !btn.disabled) {
                              btn.click();
                            }
                            """
                        )
                        submit_clicked = True
                elif verification_token:
                    submit_clicked = False
                else:
                    submit_clicked = False

                time.sleep(1.0)

            raise TimeoutError("Timed out waiting for manual CAS verification in Chrome")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass


async def _manual_cas_browser_login(
    client: httpx.AsyncClient,
    *,
    cas_account: str,
    cas_password: str,
    service_url: str,
) -> None:
    if not _CAS_BROWSER_FALLBACK_ENABLED:
        raise PermissionError("CAS authentication failed: browser-side human verification required")

    async with _get_cas_browser_login_lock():
        if _apply_cached_cas_cookies(client, cas_account):
            r = await _request_with_retry(client, "GET", service_url, label="cas.manual.cache")
            if "cas.sustech.edu.cn" not in str(r.url) and r.status_code == 200:
                _store_cas_cookie_cache(cas_account, client.cookies)
                return
            _clear_cas_cookie_cache(cas_account)

        logger.warning("cas.manual: captcha detected, opening Chrome for manual verification service=%s", service_url)

        # 第一阶段：尝试静默（无窗口）登录
        try:
            state = await asyncio.to_thread(
                _manual_cas_browser_login_sync,
                cas_account=cas_account,
                cas_password=cas_password,
                service_url=service_url,
                wait_seconds=20, # 静默等待时间缩短
                headless=True,
            )
            logger.info("cas.manual: headless verification successful account=%s", cas_account)
        except Exception as e:
            logger.warning("cas.manual: headless failed, falling back to visible window. error=%s", e)
            # 第二阶段：静默失败，弹出窗口让用户操作（如滑动验证码）
            try:
                state = await asyncio.to_thread(
                    _manual_cas_browser_login_sync,
                    cas_account=cas_account,
                    cas_password=cas_password,
                    service_url=service_url,
                    wait_seconds=_CAS_BROWSER_WAIT_SECONDS,
                    headless=False,
                )
            except TimeoutError as exc:
                raise PermissionError(
                    "CAS authentication failed: please complete the captcha in the opened Chrome window and try again."
                ) from exc
            except RuntimeError as exc:
                raise PermissionError(f"CAS authentication failed: manual browser fallback unavailable ({exc})") from exc

        _merge_cookie_state_into_client(client, state)
        _store_cas_cookie_cache(cas_account, client.cookies)

        r = await _request_with_retry(client, "GET", service_url, label="cas.manual.resume")
        if ("cas.sustech.edu.cn" in str(r.url) and "/cas/login" in str(r.url)) or r.status_code != 200:
            msg = f"CAS authentication failed: page returned {r.status_code}"
            if "cas.sustech.edu.cn" in str(r.url):
                msg = "CAS verification did not complete (still at login/captcha page)"
            raise PermissionError(msg)


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


async def _cas_login(
    client: httpx.AsyncClient,
    cas_account: str,
    cas_password: str,
    service_url: str,
) -> None:
    return await _cas_login_enhanced(client, cas_account, cas_password, service_url)


async def _cas_login_enhanced(client: httpx.AsyncClient, cas_account: str, cas_password: str, service_url: str) -> None:
    login_url = httpx.URL("https://cas.sustech.edu.cn/cas/login").copy_merge_params({"service": service_url})
    _apply_cached_cas_cookies(client, cas_account)

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Origin": f"{login_url.scheme}://{login_url.host}",
        "Referer": str(login_url),
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
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

        # if we already have valid session cookies, TIS/BB might redirect and return 403/Forbidden
        # rather than the CAS login page. We handle this below.
        if r1.status_code != 403:
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
            logger.warning("cas.login: form not found on page, likely security challenge. url=%s status=%d", str(r1.url), r1.status_code)
            await _manual_cas_browser_login(
                client,
                cas_account=cas_account,
                cas_password=cas_password,
                service_url=service_url,
            )
            return

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
            if "tis.sustech.edu.cn" in location:
                r_tis = await _request_with_retry(client, "GET", location, headers=headers, label="tis.from_cas")
                if r_tis.status_code == 403:
                    logger.warning("tis.cas: ticket validation got 403, triggering browser fallback")
                    await _manual_cas_browser_login(
                        client,
                        cas_account=cas_account,
                        cas_password=cas_password,
                        service_url=service_url,
                    )
                    return
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
    if "tis.sustech.edu.cn" in u2:
        if r2.status_code == 200:
            _store_cas_cookie_cache(cas_account, client.cookies)
            return
        if r2.status_code == 403:
            # Fall through to browser login if headless keeps getting 403
            pass

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
        logger.warning("tis.403: headless login got 403, triggering browser fallback")
        await _manual_cas_browser_login(
            client,
            cas_account=cas_account,
            cas_password=cas_password,
            service_url=service_url,
        )
        return

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
        raise PermissionError(msg)

    _store_cas_cookie_cache(cas_account, client.cookies)
