"""
backend/services/schedule_service.py
日程爬取与冲突检测业务逻辑。
网络请求通过 httpx.AsyncClient，HTML 解析通过 BeautifulSoup。
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import httpx
from bs4 import BeautifulSoup

from backend.schemas.agent import ScheduleConflict, ScheduleData, ScheduleEvent


# SUSTech 相关 URL（仅供参考，实现时按实际接口调整）
BLACKBOARD_BASE = "https://bb.sustech.edu.cn"
ACADEMIC_SYSTEM_BASE = "https://jwxt.sustech.edu.cn"


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
    instructor: str | None = None
    kind: Literal["lecture", "experiment", "other"]
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
    # TODO:
    # 1. async with httpx.AsyncClient(follow_redirects=True) as client:
    # 2.   CAS 认证流程（GET cas/login → POST credentials → 获取 service ticket）
    # 3.   使用 ticket 访问 Blackboard
    # 4.   解析作业列表页面（BeautifulSoup）
    # 5.   return [Deadline(...) for each item]
    raise NotImplementedError


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
