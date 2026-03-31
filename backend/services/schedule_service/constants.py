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
