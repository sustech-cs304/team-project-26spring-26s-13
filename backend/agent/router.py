"""
backend/agent/router.py
根据 Agent 执行结果推断 route，决定前端切换到哪个 Tab。
route 由后端确定，前端无需传入 selected_feature。
"""

from backend.schemas.agent import RouteType


def determine_route(tool_names_called: list[str]) -> RouteType:
    """
    根据本次 Agent 循环中实际调用的工具名列表，推断最合适的前端路由。

    优先级：os_automation > scheduler > encyclopedia > chat
    （多个工具被调用时，取最具体的那个）

    Args:
        tool_names_called: 本次循环中 Agent 实际调用的工具名列表，
                           从 PydanticAI result.all_messages() 中提取

    Returns:
        RouteType: "chat" | "scheduler" | "encyclopedia" | "os_automation"
    """
    # TODO:
    # TOOL_TO_ROUTE = {
    #     "fetch_blackboard_deadlines": "scheduler",
    #     "fetch_course_schedule":      "scheduler",
    #     "detect_schedule_conflicts":  "scheduler",
    #     "query_rag":                  "encyclopedia",
    #     "generate_summary":           "chat",
    #     "generate_quiz":              "chat",
    #     "file_create":                "os_automation",
    #     "file_read":                  "os_automation",
    #     "file_update":                "os_automation",
    #     "file_delete":                "os_automation",
    #     "batch_rename":               "os_automation",
    # }
    # PRIORITY = ["os_automation", "scheduler", "encyclopedia", "chat"]
    # routes_called = {TOOL_TO_ROUTE.get(t, "chat") for t in tool_names_called}
    # for r in PRIORITY:
    #     if r in routes_called:
    #         return r
    # return "chat"
    raise NotImplementedError
