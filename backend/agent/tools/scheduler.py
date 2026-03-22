"""
backend/agent/tools/scheduler.py
日程相关工具：爬取 Blackboard DDL、教务系统课表，检测时间冲突。

所有工具函数通过 @agent.tool 装饰器注册到 PydanticAI Agent。
工具函数必须是 async，第一个参数固定为 RunContext[AgentDeps]。
工具返回值是字符串（LLM 消费），结构化数据通过 ctx.deps 传出（或在 loop.py 中拦截）。
"""

from pydantic_ai import RunContext

from backend.agent.loop import AgentDeps, agent
from backend.schemas.agent import ScheduleData, ScheduleEvent, ScheduleConflict
from backend.services import schedule_service


@agent.tool
async def fetch_blackboard_deadlines(ctx: RunContext[AgentDeps]) -> str:
    """
    爬取 Blackboard 上当前用户的所有未完成作业/考试截止时间。
    使用用户的 CAS 账号密码（已存储）模拟登录。

    Returns:
        JSON 字符串，格式：
        [{"title": str, "course": str, "deadline": "ISO8601", "type": "assignment"|"exam"|"quiz"}]

    Raises（以字符串形式返回给 LLM）：
        "ERROR:CAS_LOGIN_FAILED" - CAS 登录失败
        "ERROR:BLACKBOARD_UNREACHABLE" - Blackboard 无法访问
    """
    # TODO:
    # result = await schedule_service.fetch_blackboard(
    #     cas_account=ctx.deps.cas_account,
    #     cas_password=ctx.deps.cas_password,
    # )
    # return result.model_dump_json()
    raise NotImplementedError


@agent.tool
async def fetch_course_schedule(ctx: RunContext[AgentDeps]) -> str:
    """
    爬取教务系统当前学期的完整课表（固定时间段的课程安排）。

    Returns:
        JSON 字符串，格式：
        [{"course": str, "weekday": 1-7, "start_time": "HH:MM", "end_time": "HH:MM",
          "location": str, "weeks": [1,2,...,16]}]

    Raises（字符串）：
        "ERROR:CAS_LOGIN_FAILED"
        "ERROR:ACADEMIC_SYSTEM_UNREACHABLE"
    """
    # TODO: return await schedule_service.fetch_course_schedule(ctx.deps.cas_account, ctx.deps.cas_password)
    raise NotImplementedError


@agent.tool
async def detect_schedule_conflicts(
    ctx: RunContext[AgentDeps],
    deadlines_json: str,
    course_schedule_json: str,
) -> str:
    """
    将 Blackboard DDL 列表与固定课表合并，检测时间冲突。
    不需要爬网页，纯本地逻辑。

    Args:
        deadlines_json:       fetch_blackboard_deadlines 的返回值
        course_schedule_json: fetch_course_schedule 的返回值

    Returns:
        JSON 字符串，格式：
        {
          "events":    [...],   # 所有事件，格式同 ScheduleEvent
          "conflicts": [...]    # 检测到的冲突，格式同 ScheduleConflict
        }
    """
    # TODO: return schedule_service.detect_conflicts(deadlines_json, course_schedule_json)
    raise NotImplementedError
