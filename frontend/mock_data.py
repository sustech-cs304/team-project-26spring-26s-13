"""Mock data used by the PyQt6 frontend prototype."""

APP_TITLE = {
    "en": "Student Productivity Agent",
    "zh": "学生生产力助手",
}

HOME_CORE_FEATURES = [
    {
        "title": {"en": "Agentic Loop", "zh": "智能体循环"},
        "detail": {
            "en": "Turn natural language goals into reasoning, tool use, observation, and self-correction.",
            "zh": "把自然语言目标转成推理、工具调用、观察反馈和自我修正流程。",
        },
    },
    {
        "title": {"en": "Schedule Intelligence", "zh": "日程智能"},
        "detail": {
            "en": "Sync Blackboard deadlines and local plans, then surface conflicts before they hurt your week.",
            "zh": "同步 Blackboard 截止时间和本地计划，提前发现冲突，不让它们打乱一周安排。",
        },
    },
    {
        "title": {"en": "Campus Knowledge", "zh": "校园知识检索"},
        "detail": {
            "en": "Search handbook-style content with RAG answers, citations, and a fast student-friendly interface.",
            "zh": "用 RAG 检索校园手册内容，返回带引用的答案，并通过更适合学生使用的界面呈现。",
        },
    },
]

HOME_SKILLS = [
    {
        "icon": "CHAT",
        "title": {"en": "Main Chat", "zh": "主聊天区"},
        "detail": {
            "en": "A chat-first workspace for tasks, questions, and tool-driven execution.",
            "zh": "围绕任务、提问和工具执行组织的聊天式主工作区。",
        },
    },
    {
        "icon": "TRACE",
        "title": {"en": "Thought Trace", "zh": "思维追踪"},
        "detail": {
            "en": "See observation, planning, and tool calls without flooding the main conversation.",
            "zh": "把观察、规划和工具调用独立展示，避免主对话区信息过载。",
        },
    },
    {
        "icon": "HITL",
        "title": {"en": "Safe Approval", "zh": "安全授权"},
        "detail": {
            "en": "Intercept high-risk file and schedule actions before the agent executes them.",
            "zh": "在智能体执行高风险文件或日程操作前先进行人工授权。",
        },
    },
    {
        "icon": "SYNC",
        "title": {"en": "Scheduler", "zh": "日程同步"},
        "detail": {
            "en": "Combine Blackboard, campus events, and personal TODO items into one dashboard.",
            "zh": "把 Blackboard、校历事件和个人 TODO 汇总到一个日程仪表盘中。",
        },
    },
    {
        "icon": "RAG",
        "title": {"en": "Campus QA", "zh": "校园问答"},
        "detail": {
            "en": "Use handbook retrieval and citations to answer degree, dorm, and policy questions.",
            "zh": "通过手册检索和引用回答学分、宿舍、政策等校园问题。",
        },
    },
    {
        "icon": "FILES",
        "title": {"en": "Study Copilot", "zh": "学习辅助"},
        "detail": {
            "en": "Prepare for uploaded notes, slides, and documents to become future study tools.",
            "zh": "为后续接入讲义、课件和文档解析打下基础，支持学习辅助功能。",
        },
    },
]

HOME_BANNER = {
    "title": {
        "en": "Plan, search, and act from one student workspace",
        "zh": "在一个学生工作台里完成计划、检索与执行",
    },
    "detail": {
        "en": "Start from the homepage, sign in, and move into a dashboard built for agent workflows instead of a generic chat box.",
        "zh": "从主页进入登录，再进入一个围绕 agent workflow 设计的主控制台，而不只是普通聊天框。",
    },
}

AUTH_DEMO_ACCOUNTS = [
    {
        "username": "student",
        "password": "123456",
        "major": {"en": "Software Engineering", "zh": "软件工程"},
    }
]

AUTH_FEATURES = [
    {
        "title": {"en": "Agent Chat", "zh": "智能聊天"},
        "detail": {
            "en": "A chat-first workspace for the main planning and execution loop.",
            "zh": "以聊天为中心的主工作区，用于承载规划与执行流程。",
        },
    },
    {
        "title": {"en": "Thought Trace", "zh": "思维追踪"},
        "detail": {
            "en": "Real-time visibility into observation, reasoning, and tool usage.",
            "zh": "实时查看观察、推理和工具调用过程。",
        },
    },
    {
        "title": {"en": "Safe Actions", "zh": "安全操作"},
        "detail": {
            "en": "Human-in-the-Loop approval before risky file or schedule changes.",
            "zh": "在高风险文件或日程修改前要求人工授权。",
        },
    },
    {
        "title": {"en": "Campus Support", "zh": "校园支持"},
        "detail": {
            "en": "Schedule conflict detection and handbook-based campus QA in one place.",
            "zh": "在同一个界面里完成日程冲突检测和基于手册的校园问答。",
        },
    },
]

PROFILE = {
    "name": {"en": "SUSTech Student", "zh": "南科大学生"},
    "major": {"en": "Software Engineering", "zh": "软件工程"},
    "focus": {
        "en": "Schedule planning, campus QA, study support",
        "zh": "日程规划、校园问答、学习辅助",
    },
}

RESOURCE_FILES = [
    "cs304_project_proposal.pdf",
    "student_handbook_2026.pdf",
    "week5_notes.md",
    "midterm_review.pptx",
]

CHAT_MESSAGES = [
    {
        "sender": "agent",
        "text": {
            "en": "Welcome back. I can track your schedule, search campus policies, and explain each tool step in the Thought Trace panel.",
            "zh": "欢迎回来。我可以帮你跟踪日程、查询校园政策，并在思维追踪面板里展示每一步工具调用。",
        },
    },
    {
        "sender": "user",
        "text": {
            "en": "Please check whether my Blackboard deadlines conflict with lab time.",
            "zh": "请帮我检查 Blackboard 的截止时间和实验时间有没有冲突。",
        },
    },
    {
        "sender": "agent",
        "text": {
            "en": "I found a conflict on Thursday 16:00. The chat flow can render the schedule summary directly below.",
            "zh": "我发现周四 16:00 有冲突。聊天区会直接在下方渲染日程摘要。",
        },
    },
]

TRACE_EVENTS = [
    {
        "phase": {"en": "Observation", "zh": "观察"},
        "title": {"en": "Read user goal", "zh": "读取用户目标"},
        "detail": {
            "en": "Need a schedule conflict check and a concise explanation.",
            "zh": "需要完成日程冲突检查，并给出简洁说明。",
        },
        "status": "done",
    },
    {
        "phase": {"en": "Reasoning", "zh": "推理"},
        "title": {"en": "Plan tool sequence", "zh": "规划工具链路"},
        "detail": {
            "en": "Use Blackboard scraper -> merge local calendar -> detect overlap.",
            "zh": "使用 Blackboard 抓取 -> 合并本地日程 -> 检测时间重叠。",
        },
        "status": "done",
    },
    {
        "phase": {"en": "Tool Use", "zh": "工具调用"},
        "title": {"en": "Awaiting authorization", "zh": "等待授权"},
        "detail": {
            "en": "Schedule update requires explicit human approval.",
            "zh": "修改日程需要用户明确授权。",
        },
        "status": "pending",
    },
    {
        "phase": {"en": "Observation", "zh": "观察"},
        "title": {"en": "Collect handbook context", "zh": "收集手册上下文"},
        "detail": {
            "en": "RAG retrieval ready for campus encyclopedia queries.",
            "zh": "RAG 检索已准备好，可用于校园百科问答。",
        },
        "status": "running",
    },
]

SCHEDULE_EVENTS = [
    {
        "title": {"en": "CS304 Team Meeting", "zh": "CS304 小组会议"},
        "time": {"en": "Mon 19:00 - 20:30", "zh": "周一 19:00 - 20:30"},
        "source": {"en": "Local TODO", "zh": "本地 TODO"},
        "detail": {
            "en": "Finalize API contract and UI handoff.",
            "zh": "确认 API 契约和前后端界面交接内容。",
        },
    },
    {
        "title": {"en": "Blackboard Deadline: OOAD Report", "zh": "Blackboard 截止：OOAD 报告"},
        "time": {"en": "Thu 15:30", "zh": "周四 15:30"},
        "source": {"en": "Blackboard", "zh": "Blackboard"},
        "detail": {
            "en": "Upload final report before the submission closes.",
            "zh": "在截止前上传最终报告。",
        },
    },
    {
        "title": {"en": "Embedded Systems Lab", "zh": "嵌入式系统实验"},
        "time": {"en": "Thu 16:00 - 18:00", "zh": "周四 16:00 - 18:00"},
        "source": {"en": "Campus Calendar", "zh": "校园日历"},
        "detail": {
            "en": "Lab room 107, attendance required.",
            "zh": "实验楼 107，必须到场。",
        },
    },
]

CONFLICTS = [
    {
        "title": {
            "en": "OOAD report overlaps with lab preparation",
            "zh": "OOAD 报告截止与实验准备时间重叠",
        },
        "detail": {
            "en": "Deadline is 30 minutes before a fixed lab block on Thursday.",
            "zh": "截止时间距离周四固定实验开始只有 30 分钟。",
        },
    },
    {
        "title": {
            "en": "Two evening tasks exceed available focus time",
            "zh": "两个晚间任务超出了可用专注时间",
        },
        "detail": {
            "en": "Study plan suggests moving document reading to Tuesday night.",
            "zh": "学习计划建议把文档阅读移动到周二晚上。",
        },
    },
]

ENCYCLOPEDIA_RESULTS = {
    "credit": {
        "query": {"en": "credit requirements", "zh": "学分要求"},
        "answer": {
            "en": (
                "### Credit Requirement Summary\n"
                "- Undergraduate students must complete the program credit minimum.\n"
                "- Major core courses and general education courses are validated separately.\n"
                "- The agent should cite the handbook section before giving final advice.\n\n"
                "Recommended next step: ask for your specific major audit to compare earned credits."
            ),
            "zh": (
                "### 学分要求摘要\n"
                "- 本科生需要完成培养方案规定的最低学分要求。\n"
                "- 专业核心课程和通识课程通常分别核算。\n"
                "- 智能体在给出最终建议前，应引用手册中的具体章节。\n\n"
                "建议下一步：结合你的专业培养方案，进一步比对已经获得的学分。"
            ),
        },
        "citations": {
            "en": [
                "Student Handbook / Degree Requirements / General Rules",
                "School Office FAQ / Credit Transfer Notes",
            ],
            "zh": [
                "学生手册 / 学位要求 / 总则",
                "教务 FAQ / 学分转换说明",
            ],
        },
    },
    "dorm": {
        "query": {"en": "dorm policy", "zh": "宿舍规定"},
        "answer": {
            "en": (
                "### Dormitory Policy Snapshot\n"
                "- Quiet hours apply during the evening and late night period.\n"
                "- Guests and appliance usage are controlled by dormitory regulations.\n"
                "- Violations may trigger warnings or access restrictions.\n\n"
                "Ask a follow-up question if you want the rule for visitors, electricity, or curfew."
            ),
            "zh": (
                "### 宿舍规定速览\n"
                "- 晚间和深夜时段通常有安静时间要求。\n"
                "- 访客和电器使用需要遵守宿舍管理规定。\n"
                "- 违规行为可能带来警告或权限限制。\n\n"
                "如果你想继续问访客、电器或门禁规则，可以继续追问。"
            ),
        },
        "citations": {
            "en": ["Student Handbook / Dormitory Life / Conduct Rules"],
            "zh": ["学生手册 / 宿舍生活 / 行为规范"],
        },
    },
    "default": {
        "query": {"en": "campus handbook question", "zh": "校园手册问题"},
        "answer": {
            "en": (
                "### Campus Encyclopedia Result\n"
                "This panel is wired for RAG-style answers. The final backend can replace the "
                "mock response with retrieved handbook snippets and citations."
            ),
            "zh": (
                "### 校园百科结果\n"
                "这个区域已经为 RAG 风格答案预留好了接口。后续后端可以直接把检索到的手册片段和引用替换进来。"
            ),
        },
        "citations": {
            "en": ["Student Handbook / Placeholder Citation"],
            "zh": ["学生手册 / 占位引用"],
        },
    },
}

HITL_REQUEST = {
    "action": {"en": "Overwrite local study calendar", "zh": "覆盖本地学习日程"},
    "risk": {"en": "High", "zh": "高"},
    "reason": {
        "en": "The agent wants to move three study blocks to avoid a deadline collision.",
        "zh": "智能体想调整 3 个学习时间块，以避免截止时间和实验安排冲突。",
    },
    "payload": {
        "en": [
            "Move OOAD report reminder from Thu 15:00 to Wed 21:00",
            "Create a 40-minute buffer before the Thursday lab",
            "Notify the user before editing any protected schedule entry",
        ],
        "zh": [
            "将 OOAD 报告提醒从周四 15:00 调整到周三 21:00",
            "在周四实验前预留 40 分钟缓冲时间",
            "在修改任何受保护日程前先通知用户",
        ],
    },
}
