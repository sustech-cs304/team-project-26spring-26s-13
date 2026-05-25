"""
backend/agent/tools/time_utils.py
系统时间工具：LLM 通过调用此工具获取当前北京时间，而非依赖训练数据或 system prompt。
"""

from datetime import datetime, timezone, timedelta

from pydantic_ai import RunContext

from backend.agent.core import AgentDeps, agent


@agent.tool
async def get_current_time(ctx: RunContext[AgentDeps]) -> str:
    """
    获取当前精确北京时间（Asia/Shanghai, UTC+8）。

    在以下场景使用此工具：
      - 用户询问"今天几号""现在几点""今天星期几"
      - 用户询问"昨天是几号""明天星期几"
      - 用户提及"今天""明天""本周""下周"等时间概念需要计算时
      - 任何需要以当前时间为基准进行日期推算的场景
      - 任何涉及日期的 scheduler / personal task 查询之前

    返回格式: {"date": "2026-05-24", "time": "17:22:08", "weekday_cn": "周日",
              "weekday_en": "Sunday", "iso": "2026-05-24T17:22:08.123456+08:00",
              "tz": "Asia/Shanghai"}
    """
    import json

    now = datetime.now(timezone(timedelta(hours=8)))
    weekday_en = now.strftime("%A")
    _cn_map = {
        "Monday": "周一",
        "Tuesday": "周二",
        "Wednesday": "周三",
        "Thursday": "周四",
        "Friday": "周五",
        "Saturday": "周六",
        "Sunday": "周日",
    }
    return json.dumps(
        {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "weekday_cn": _cn_map.get(weekday_en, weekday_en),
            "weekday_en": weekday_en,
            "iso": now.isoformat(),
            "tz": "Asia/Shanghai",
        },
        ensure_ascii=False,
    )
