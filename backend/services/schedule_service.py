"""
backend/services/schedule_service.py
日程爬取与冲突检测业务逻辑。
网络请求通过 httpx.AsyncClient，HTML 解析通过 BeautifulSoup。
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from backend.schemas.agent import ScheduleConflict, ScheduleData, ScheduleEvent

# SUSTech 相关 URL
BLACKBOARD_BASE = "https://bb.sustech.edu.cn"
ACADEMIC_SYSTEM_BASE = "https://tis.sustech.edu.cn"


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
    notes: str | None = None # 事件备注

@dataclass
class FixedPersonalEvent:
    # We assume that this fixed personal event occupied all time 
    # from start_at to end_at, thus no duration needed
    title: str
    start_at: datetime
    end_at: datetime
    location: str | None = None

@dataclass
class TimeWindow:
    weekdays: set[int]
    start_time: str # HH:MM, 24h format
    end_time: str # HH:MM, 24h format

@dataclass
class PersonalTask:
    title: str
    duration_minutes: int
    target_occurrences: int
    period: Literal["day", "week", "month", "year"]
    earliest_start: datetime | None = None
    deadline: datetime | None = None
    time_windows: list[TimeWindow] | None = None
    location: str | None = None
    importance: int | None = None
    notes: str | None = None


def _parse_due_at_zh_cn(text: str) -> datetime | None:
    m = re.search(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日.*?(上午|下午)\s*(\d{1,2}):(\d{2})",
        text,
    )
    if not m:
        return None
    y, mo, d, ampm, hh, mm = m.groups()
    hour = int(hh)
    minute = int(mm)
    if ampm == "下午" and hour != 12:
        hour += 12
    if ampm == "上午" and hour == 12:
        hour = 0
    return datetime(int(y), int(mo), int(d), hour, minute)


def _parse_deadline_from_upload_assignment_html(html: str, page_url: str) -> Deadline | None:
    soup = BeautifulSoup(html, "html.parser")

    title_text = soup.title.get_text(" ", strip=True) if soup.title else ""
    assignment_title = title_text
    m = re.match(r"^上载作业：\s*(.*?)\s*[–-]\s*(.+)$", title_text)
    if m:
        assignment_title = m.group(1).strip()

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

    label = soup.find("div", class_="metaLabel", string=lambda s: s and "到期日期" in s)
    if not label:
        return None

    section = label.find_parent("div", class_="metaSection")
    if not section:
        return None

    field = section.find("div", class_="metaField")
    if not field:
        return None

    due_at = _parse_due_at_zh_cn(field.get_text(" ", strip=True))
    if not due_at or not course_id:
        return None

    return Deadline(
        title=assignment_title,
        course_id=course_id,
        due_at=due_at,
        type="assignment",
        url=page_url,
    )


async def _cas_login(client: httpx.AsyncClient, cas_account: str, cas_password: str, service_url: str) -> None:
    login_url = httpx.URL("https://cas.sustech.edu.cn/cas/login").copy_merge_params({"service": service_url})
    r1 = await client.get(str(login_url))
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

    r2 = await client.post(str(post_url), data=payload)
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


async def fetch_blackboard(cas_account: str, cas_password: str) -> list[Deadline]:
    """
    使用 CAS 统一认证登录 Blackboard，爬取当前学期所有未完成作业/考试的截止时间。

    Args:
        cas_account:  南科大 CAS 账号
        cas_password: CAS 密码（已由调用方解密）

    Returns:
        list[Deadline]，按截止时间升序排列

    Raises:
        ConnectionError: CAS 或 Blackboard 服务不可达
        PermissionError: CAS 认证失败（账号密码错误）
    """
    service_url = f"{BLACKBOARD_BASE}/webapps/bb-sso-BBLEARN/index.jsp"
    headers = {"User-Agent": "Mozilla/5.0"}

    async with httpx.AsyncClient(
        follow_redirects=True,
        headers=headers,
        timeout=30.0,
        trust_env=False,
    ) as client:
        await _cas_login(client, cas_account, cas_password, service_url)

        start_urls = [f"{BLACKBOARD_BASE}/webapps/portal/execute/defaultTab"]
        to_visit: list[str] = start_urls[:]
        visited: set[str] = set()
        upload_urls: list[str] = []

        while to_visit and len(visited) < 25 and len(upload_urls) < 50:
            url = to_visit.pop(0)
            if url in visited:
                continue
            visited.add(url)

            r = await client.get(url)
            if r.status_code >= 400:
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not href or href.startswith("javascript:"):
                    continue
                abs_url = urljoin(url, href)

                if "/webapps/assignment/uploadAssignment" in abs_url:
                    if abs_url not in upload_urls:
                        upload_urls.append(abs_url)
                    continue

                if "/webapps/blackboard/content/listContent.jsp" in abs_url:
                    if abs_url not in visited and abs_url not in to_visit:
                        to_visit.append(abs_url)

        deadlines: list[Deadline] = []
        for u in upload_urls:
            r = await client.get(u)
            if r.status_code >= 400:
                continue
            d = _parse_deadline_from_upload_assignment_html(r.text, u)
            if d:
                deadlines.append(d)

        deadlines.sort(key=lambda x: x.due_at)
        return deadlines


async def fetch_course_schedule(cas_account: str, cas_password: str) -> list[CourseOccurrence]:
    """
    使用 CAS 认证登录教务系统，爬取当前学期固定课表。

    Args:
        cas_account:  CAS 账号
        cas_password: CAS 密码（已解密）

    Returns:
        list[CourseOccurrence]

    Raises:
        ConnectionError: 服务不可达
        PermissionError: 认证失败
    """
    # TODO: 类似 fetch_blackboard，目标是教务系统
    raise NotImplementedError


def detect_conflicts(
    deadlines: list[Deadline],
    course_slots: list[CourseOccurrence],
) -> ScheduleData:
    """
    将截止时间列表与固定课表合并，检测时间冲突。
    纯本地逻辑，不访问网络。

    冲突定义：截止时间在某个固定课时的 2 小时内（即截止时间太紧，没有充足准备时间）。

    Args:
        deadlines:    fetch_blackboard 的返回值
        course_slots: fetch_course_schedule 的返回值

    Returns:
        ScheduleData，包含 events 列表（所有事件）和 conflicts 列表（检测到的冲突）
    """
    # TODO:
    # 1. 将 deadlines 和 course_slots 转换为统一时间轴
    # 2. 对每个 deadline，检查其前 2 小时内是否有课
    # 3. 构造 events 和 conflicts 列表
    # 4. return ScheduleData(events=[...], conflicts=[...])
    raise NotImplementedError


async def refresh(db, user) -> ScheduleData:
    """
    完整刷新流程：爬取 + 冲突检测 + 结果返回。
    供 /api/schedule/refresh 路由调用。

    Args:
        db:   数据库 Session（当前版本暂不写入 DB，后续可缓存）
        user: User ORM 对象（用于解密 CAS 凭据）

    Returns:
        最新的 ScheduleData
    """
    # TODO:
    # from backend.utils.crypto import decrypt
    # cas_password = decrypt(user.cas_password_encrypted)
    # deadlines = await fetch_blackboard(user.cas_account, cas_password)
    # slots = await fetch_course_schedule(user.cas_account, cas_password)
    # return detect_conflicts(deadlines, slots)
    raise NotImplementedError
