# Student Productivity Agent — 项目框架说明文档

> **本文档面向所有开发成员。请在开始写代码前通读本文档。**
> 本文档说明：项目结构、数据库设计、API 接口、各模块在哪里写代码、以及必须遵守的开发约定。

---

## 目录

1. [项目简介](#1-项目简介)
2. [快速开始](#2-快速开始)
3. [整体架构](#3-整体架构)
4. [目录结构详解](#4-目录结构详解)
5. [数据库设计](#5-数据库设计)
6. [API 接口一览](#6-api-接口一览)
7. [各 Epic 负责模块指南](#7-各-epic-负责模块指南)
8. [关键设计模式与约定](#8-关键设计模式与约定)
9. [常见问题](#9-常见问题)

---

## 1. 项目简介

**Student Productivity Agent** 是一个面向南科大学生的 AI 智能体桌面应用，集成以下六大功能：

| Epic | 功能 | 描述 |
|------|------|------|
| Epic 1 | Agentic Loop | 核心 AI 推理循环，驱动所有功能 |
| Epic 2 | Intelligent GUI | PyQt6 桌面界面，含 Thought Trace 面板和 HITL 弹窗 |
| Epic 3 | Multi-Source Scheduler | 自动爬取 Blackboard DDL 和教务系统课表，检测冲突 |
| Epic 4 | Campus Encyclopedia (RAG) | 基于向量检索的校园政策问答 |
| Epic 5 | Study Copilot | 教材摘要、概念提取、练习题生成 |
| Epic 6 | OS Automation | 自然语言驱动的文件系统操作（含安全审批） |

---

## 2. 快速开始

### 2.1 创建 conda 虚拟环境（一键完成）

```bash
# 在项目根目录执行
conda env create -f Guideline/environment.yml

# 激活环境
conda activate software-engineering
```

> 所有成员必须使用 `software-engineering` 这个环境名，保证依赖版本一致。

### 2.2 配置环境变量

在项目根目录创建 `.env` 文件（不要提交到 git）：

```env
# PostgreSQL 连接字符串（本地开发改成你自己的）
POSTGRES_DSN=postgresql+asyncpg://postgres:yourpassword@localhost:5432/spa_db

# Fernet 加密密钥（生成方法见下方）
FERNET_KEY=your_fernet_key_here

# JWT 签名密钥
SECRET_KEY=your_jwt_secret_here
```

生成 Fernet Key：
```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

### 2.3 初始化数据库

```bash
# 生成迁移文件（首次或修改 ORM 模型后执行）
alembic revision --autogenerate -m "init"

# 应用迁移
alembic upgrade head
```

### 2.4 启动后端

```bash
python -m backend.main
# 服务运行在 http://127.0.0.1:8000
# API 文档访问 http://127.0.0.1:8000/docs
```

### 2.5 启动前端

```bash
python -m God Xun-Frontend.main
```

---

## 3. 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                     PyQt6 Frontend                          │
│                                                             │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │  Left Panel  │  │   Center Panel   │  │ Right Panel  │  │
│  │              │  │                  │  │              │  │
│  │ User Profile │  │ Chat / Schedule  │  │ Thought      │  │
│  │ Materials    │  │ Encyclopedia     │  │ Trace Panel  │  │
│  │ List         │  │ (Tab Switch)     │  │              │  │
│  └──────────────┘  └──────────────────┘  └──────────────┘  │
│                          │  HTTP (requests)                  │
└──────────────────────────┼──────────────────────────────────┘
                           │
                    REST API (JSON)
                    localhost:8000
                           │
┌──────────────────────────┼──────────────────────────────────┐
│                 FastAPI Backend                              │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   API Routers                        │   │
│  │  /auth  /user  /agent/run  /materials  /dashboard    │   │
│  └───────────────────────┬─────────────────────────────┘   │
│                           │                                  │
│  ┌───────────────────────▼─────────────────────────────┐   │
│  │              PydanticAI Agent Loop                   │   │
│  │                                                      │   │
│  │  Perception → Reasoning → Tool Use → Observation    │   │
│  │                                                      │   │
│  │  Tools: scheduler | rag | os_automation | copilot   │   │
│  └───────────────────────┬─────────────────────────────┘   │
│                           │                                  │
│  ┌───────────┐   ┌────────▼────────┐   ┌──────────────┐   │
│  │  DeepSeek │   │   PostgreSQL    │   │   ChromaDB   │   │
│  │  LLM API  │   │  (用户/历史/    │   │  (RAG向量库) │   │
│  │           │   │   教材/审计)    │   │              │   │
│  └───────────┘   └─────────────────┘   └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 数据流说明

1. **用户在 PyQt6 发消息** → `ChatWidget` emit signal → `DashboardPage.send_message()`
2. **`AgentWorker`（QThread）** 调用 `POST /api/agent/run`，不阻塞 UI
3. **FastAPI 路由** 验证 JWT → 调用 `run_agent()`
4. **PydanticAI Agent** 分析消息 → 选择工具 → 执行工具 → 收集 Trace
5. **工具执行结果** 返回 Agent → Agent 生成最终回复
6. **`AgentResponse`** 返回前端 → `DashboardPage` 分发给各子组件
7. **若遇到高危操作** → 工具抛出 `HITLInterrupt` → 返回 `hitl_request` → 前端弹窗

---

## 4. 目录结构详解

```
team-project-26spring-26s-13/
│
├── backend/                         # FastAPI 后端（服务端）
│   ├── main.py                      # 应用入口，注册所有路由
│   ├── config.py                    # 全局配置（读取 .env）
│   │
│   ├── database/                    # 数据库连接与操作
│   │   ├── postgres.py              # SQLAlchemy 引擎 + ORM 模型定义
│   │   └── chromadb.py              # ChromaDB 客户端 + CRUD 操作
│   │
│   ├── schemas/                     # Pydantic 模型（API 请求/响应的数据契约）
│   │   ├── auth.py                  # 注册/登录请求与响应
│   │   ├── agent.py                 # Agent 请求/响应（最核心的 schema）
│   │   ├── dashboard.py             # Dashboard bootstrap 响应
│   │   ├── material.py              # 教材文件信息
│   │   └── user.py                  # 用户 profile 和配置
│   │
│   ├── api/                         # HTTP 路由处理器（只负责参数校验和调用 service）
│   │   ├── deps.py                  # JWT 认证 dependency（get_current_user）
│   │   ├── auth.py                  # POST /api/auth/*
│   │   ├── user.py                  # GET/PUT /api/user/*
│   │   ├── agent.py                 # POST /api/agent/run（核心入口）
│   │   ├── materials.py             # GET/POST/DELETE /api/materials/*
│   │   ├── dashboard.py             # GET /api/dashboard/bootstrap
│   │   └── schedule.py              # POST /api/schedule/refresh
│   │
│   ├── agent/                       # PydanticAI Agent 逻辑
│   │   ├── loop.py                  # Agent 主循环，AgentDeps 定义
│   │   ├── hitl.py                  # HITL 挂起状态管理器（内存）
│   │   ├── router.py                # 工具调用 → 前端 route 推断
│   │   ├── prompt.py                # System prompt 模板
│   │   └── tools/                   # 所有工具函数
│   │       ├── __init__.py          # 导入所有工具（触发 @agent.tool 注册）
│   │       ├── scheduler.py         # Epic 3：日程爬取工具
│   │       ├── rag.py               # Epic 4：RAG 检索工具
│   │       ├── os_automation.py     # Epic 6：文件系统工具
│   │       └── study_copilot.py     # Epic 5：学习辅助工具
│   │
│   ├── services/                    # 业务逻辑层（工具和路由都调用这里）
│   │   ├── auth_service.py          # 注册/登录/JWT 签发
│   │   ├── user_service.py          # 用户 profile 更新
│   │   ├── material_service.py      # 文件上传 + 向量化流程
│   │   ├── schedule_service/        # Blackboard/教务爬取 + 冲突检测（拆包）
│   │   ├── rag_service.py           # RAG 学科剪枝 + 上下文格式化
│   │   ├── dashboard_service.py     # Bootstrap 数据组装
│   │   └── audit_service.py         # OS 操作审计日志写入
│   │
│   └── utils/                       # 工具函数（无业务依赖）
│       ├── crypto.py                # Fernet 加解密（CAS密码/API Key）
│       └── document_parser.py       # PDF/PPT/MD 文本提取
│
├── frontend/                        # PyQt6 客户端
│   ├── main.py                      # 应用入口（健康检查 → 显示 HomePage）
│   ├── config.py                    # API_BASE_URL 配置
│   │
│   ├── api/
│   │   └── client.py                # HTTP 客户端封装（所有 API 调用从这里走）
│   │
│   ├── views/                       # 页面级组件（页面切换逻辑）
│   │   ├── home_page.py             # 首页
│   │   ├── auth_page.py             # 登录/注册页
│   │   └── dashboard_page.py        # 主界面（协调所有子组件）
│   │
│   ├── components/                  # 可复用 UI 组件
│   │   ├── chat_widget.py           # 聊天区（消息列表 + 输入框）
│   │   ├── trace_widget.py          # Thought Trace 面板
│   │   ├── schedule_widget.py       # 日程展示组件
│   │   ├── encyclopedia_widget.py   # 百科结果展示组件
│   │   ├── materials_widget.py      # 教材列表（上传/删除）
│   │   └── hitl_dialog.py           # HITL 高危操作授权弹窗
│   │
│   └── workers/
│       └── agent_worker.py          # QThread：后台调用 /api/agent/run
│
└── Guideline/                       # 项目文档与规范
    ├── README.md                    # 本文件
    ├── environment.yml              # conda 环境配置（一键安装依赖）
    └── 整体架构图.jpg
```

---

## 5. 数据库设计

### 5.1 PostgreSQL 表结构

#### `users` 表（用户主表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `user_id` | UUID (PK) | 用户唯一标识 |
| `username` | VARCHAR(64) UNIQUE | 登录用户名 |
| `password_hash` | VARCHAR(256) | bcrypt 哈希后的密码 |
| `display_name` | VARCHAR(128) | 界面显示名 |
| `major` | VARCHAR(128) | 专业 |
| `cas_account` | VARCHAR(128) | 南科大 CAS 账号（明文） |
| `cas_password_encrypted` | BYTEA | **Fernet 加密**后的 CAS 密码 |
| `llm_api_key_encrypted` | BYTEA | **Fernet 加密**后的 DeepSeek API Key |
| `preferences` | JSONB | 前端偏好（主题、语言等） |
| `created_at` | TIMESTAMPTZ | 注册时间 |

> **安全要求**：`cas_password_encrypted` 和 `llm_api_key_encrypted` 必须通过 `backend/utils/crypto.py` 的 `encrypt()/decrypt()` 读写，**任何地方不得明文存储密码**。

---

#### `chat_sessions` 表（对话会话）

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | VARCHAR(128) (PK) | 由前端生成，格式 `sess_{timestamp}_{random}` |
| `user_id` | UUID (FK → users) | 归属用户 |
| `created_at` | TIMESTAMPTZ | 会话创建时间 |
| `updated_at` | TIMESTAMPTZ | 最后一条消息时间（自动更新） |

---

#### `chat_messages` 表（对话消息）

| 字段 | 类型 | 说明 |
|------|------|------|
| `message_id` | UUID (PK) | 消息唯一 ID |
| `session_id` | VARCHAR(128) (FK → chat_sessions) | 归属会话 |
| `role` | ENUM('user','assistant') | 消息发送方 |
| `content` | TEXT | 消息内容 |
| `timestamp` | TIMESTAMPTZ | 发送时间 |

---

#### `materials` 表（教材文件）

| 字段 | 类型 | 说明 |
|------|------|------|
| `file_id` | UUID (PK) | 文件唯一 ID |
| `user_id` | UUID (FK → users) | 归属用户 |
| `file_name` | VARCHAR(256) | 原始文件名 |
| `file_type` | VARCHAR(64) | MIME 类型（如 `application/pdf`） |
| `file_path` | VARCHAR(512) | 服务器本地绝对路径 |
| `subject_type` | ENUM | 学科分类（见下方说明） |
| `vectorized` | BOOLEAN | 是否已完成向量化（默认 False） |
| `uploaded_at` | TIMESTAMPTZ | 上传时间 |

**`subject_type` 枚举值**（共 20 类）：

| 值 | 含义 |
|----|------|
| `cs` | 计算机科学与技术 |
| `electronics` | 电子与电气工程 |
| `materials` | 材料科学与工程 |
| `math` | 数学 |
| `physics` | 物理 |
| `chemistry` | 化学 |
| `biology` | 生物 |
| `geography` | 地理 |
| `philosophy` | 哲学 |
| `history` | 历史 |
| `literature` | 文学 |
| `politics` | 政治 |
| `finance` | 金融 |
| `statistics` | 统计 |
| `ocean` | 海洋科学 |
| `economics` | 经济 |
| `law` | 法律 |
| `management` | 管理 |
| `medicine` | 医学 |
| `policy` | 学校政策与规章制度 |
| `other` | 未能分类 / 通用（**RAG 时必查**） |

> 学科分类由 LLM 自动判断（见 `backend/agent/tools/rag.py: classify_subject`）。

---

#### `audit_logs` 表（OS 操作审计）

| 字段 | 类型 | 说明 |
|------|------|------|
| `log_id` | UUID (PK) | 记录唯一 ID |
| `user_id` | UUID (FK → users) | 操作用户 |
| `session_id` | VARCHAR(128) | 所属会话 |
| `action_type` | VARCHAR(32) | 操作类型：`create/read/update/delete/rename` |
| `target_path` | VARCHAR(1024) | 操作目标的绝对路径 |
| `description` | TEXT | 操作的自然语言描述 |
| `hitl_required` | BOOLEAN | 是否触发了 HITL 审批 |
| `hitl_approved` | BOOLEAN (NULL) | 审批结果（NULL = 无需审批） |
| `executed_at` | TIMESTAMPTZ | 执行时间 |

---

### 5.2 ChromaDB 向量数据库设计

ChromaDB 按学科类型分为 **20 个独立 Collection**：

| Collection 名 | 对应 subject_type | 说明 |
|--------------|-------------------|------|
| `cs` | cs | 计算机类教材 |
| `electronics` | electronics | 电子/电气类教材 |
| `materials` | materials | 材料科学类教材 |
| `math` | math | 数学类教材 |
| `physics` | physics | 物理类教材 |
| `chemistry` | chemistry | 化学类教材 |
| `biology` | biology | 生物类教材 |
| `geography` | geography | 地理类教材 |
| `philosophy` | philosophy | 哲学类教材 |
| `history` | history | 历史类教材 |
| `literature` | literature | 文学类教材 |
| `politics` | politics | 政治类教材 |
| `finance` | finance | 金融类教材 |
| `statistics` | statistics | 统计类教材 |
| `ocean` | ocean | 海洋科学类教材 |
| `economics` | economics | 经济类教材 |
| `law` | law | 法律类教材 |
| `management` | management | 管理类教材 |
| `medicine` | medicine | 医学类教材 |
| `policy` | policy | 学校政策与规章制度 |
| `other` | other | 未分类（**每次 RAG 必查**） |

**每个向量 chunk 的 metadata 格式**：

```json
{
  "file_id": "uuid-string",
  "file_name": "lecture_week5.pdf",
  "chunk_index": 3,
  "subject_type": "cs"
}
```

**RAG 查询剪枝策略**：

```
用户问题
    │
    ├── LLM 能判断学科（如：CS相关）
    │       └── 查询：cs + other（两个 Collection）
    │
    ├── LLM 无法判断（subject_hint = "unknown"）
    │       └── 查询：所有 5 个 Collection
    │
    └── 任何情况：other 集合必查
```

---

## 6. API 接口一览

所有接口均需 `Authorization: Bearer <token>` Header，**除了** `/api/auth/register` 和 `/api/auth/login`。

### 认证接口

| Method | Path | 描述 |
|--------|------|------|
| POST | `/api/auth/register` | 注册新用户 |
| POST | `/api/auth/login` | 登录，返回 JWT token |
| POST | `/api/auth/logout` | 登出（客户端丢弃 token） |

**注册请求体**：
```json
{
  "username": "zhangsan",
  "password": "password123",
  "display_name": "张三",
  "major": "Software Engineering"
}
```

**登录/注册响应体**：
```json
{
  "user_id": "uuid-string",
  "display_name": "张三",
  "major": "Software Engineering",
  "token": "eyJhbGciOiJIUzI1NiJ9..."
}
```

---

### 用户接口

| Method | Path | 描述 |
|--------|------|------|
| GET | `/api/user/profile` | 获取当前用户 profile |
| PUT | `/api/user/profile` | 更新 display_name/major/preferences |
| PUT | `/api/user/credentials` | 更新 CAS 账号/密码 或 LLM API Key |

**更新凭据请求体**（字段可选，只传要更新的）：
```json
{
  "cas_account": "12345678",
  "cas_password": "my_cas_password",
  "llm_api_key": "sk-xxxxxxxxxxxxxxxx"
}
```

---

### 主界面初始化

| Method | Path | 描述 |
|--------|------|------|
| GET | `/api/dashboard/bootstrap` | 一次性拉取主界面所需全部初始数据 |

**响应体**：
```json
{
  "user_profile": {
    "user_id": "...",
    "display_name": "张三",
    "major": "Software Engineering",
    "preferences": {"theme": "dark", "language": "zh"}
  },
  "chat_history": [
    {"message_id": "...", "role": "user", "content": "你好", "timestamp": "..."}
  ],
  "materials": [
    {
      "file_id": "...",
      "file_name": "week5_notes.pdf",
      "file_type": "application/pdf",
      "subject_type": "cs",
      "vectorized": true,
      "uploaded_at": "2026-03-21T18:00:00+08:00"
    }
  ],
  "local_schedule": {
    "events": [],
    "conflicts": []
  }
}
```

---

### Agent 核心接口

| Method | Path | 描述 |
|--------|------|------|
| POST | `/api/agent/run` | Agent 主入口（对话 + HITL 审批） |
| GET | `/api/agent/sessions` | 历史会话列表 |
| DELETE | `/api/agent/sessions/{session_id}` | 删除会话 |

**普通对话请求体**：
```json
{
  "user_id": "uuid-string",
  "session_id": "sess_20260322_a1b2c3",
  "message": "帮我查一下本周 Blackboard 的作业截止时间",
  "attachments": [],
  "hitl_reply": null
}
```

**HITL 审批请求体**（`message` 为空字符串）：
```json
{
  "user_id": "uuid-string",
  "session_id": "sess_20260322_a1b2c3",
  "message": "",
  "attachments": [],
  "hitl_reply": {
    "request_id": "hitl_sess_20260322_a1b2c3_1711123456",
    "approved": true
  }
}
```

**响应体（所有字段必须存在，无数据时为 null 或空列表）**：
```json
{
  "session_id": "sess_20260322_a1b2c3",
  "assistant_message": {
    "role": "assistant",
    "content": "本周有 2 个即将到期的作业...",
    "timestamp": "2026-03-22T20:00:00+08:00"
  },
  "trace": [
    {
      "phase": "Observation",
      "title": "分析用户目标",
      "detail": "用户需要查询 Blackboard DDL",
      "status": "done",
      "timestamp": "2026-03-22T19:59:58+08:00"
    },
    {
      "phase": "Tool Use",
      "title": "fetch_blackboard_deadlines",
      "detail": "调用 Blackboard 爬虫工具",
      "status": "done",
      "timestamp": "2026-03-22T19:59:59+08:00"
    }
  ],
  "route": "scheduler",
  "ui_payload": {
    "schedule": {
      "events": [{"event_id":"...","title":"CS304 作业","time":"Thu 23:59","source":"Blackboard","detail":"..."}],
      "conflicts": []
    },
    "encyclopedia": null
  },
  "hitl_request": null,
  "error": null
}
```

**`route` 枚举值**（后端自动决定，前端根据此值切换 Tab）：

| 值 | 含义 | 前端行为 |
|----|------|---------|
| `chat` | 普通对话 | 留在 Chat Tab |
| `scheduler` | 日程相关 | 自动切到 Schedule Tab |
| `encyclopedia` | 百科查询 | 自动切到 Encyclopedia Tab |
| `os_automation` | 文件操作 | 留在 Chat Tab（操作结果在对话中显示） |

**HITL 拦截响应体**（需要用户审批时，`hitl_request` 非 null）：
```json
{
  "hitl_request": {
    "request_id": "hitl_sess_..._1711123456",
    "action": "删除实验报告文件夹中的 3 个文件",
    "risk": "high",
    "reason": "文件删除操作不可逆，需要用户明确授权",
    "payload": [
      "删除 lab1_report_draft.docx",
      "删除 lab1_data_old.xlsx",
      "删除 lab1_backup.zip"
    ]
  }
}
```

---

### 教材接口

| Method | Path | 描述 |
|--------|------|------|
| GET | `/api/materials` | 获取当前用户教材列表 |
| POST | `/api/materials/upload` | 上传教材（立即触发向量化） |
| DELETE | `/api/materials/{file_id}` | 删除教材（同时清除向量） |

**上传请求**：`multipart/form-data`，字段名 `file`。支持格式：`.pdf` `.pptx` `.ppt` `.md` `.txt`

---

### 日程接口

| Method | Path | 描述 |
|--------|------|------|
| POST | `/api/schedule/refresh` | 手动触发重新爬取日程 |

> 调用前提：用户已在 `/api/user/credentials` 填入 CAS 账号和密码。

---

## 7. 各 Epic 负责模块指南

### Epic 1：Agentic Loop（PM / 架构负责人）

**需要实现的文件**：

| 文件 | 核心任务 |
|------|---------|
| `backend/agent/loop.py` | 初始化 PydanticAI Agent（接入 DeepSeek），实现 `run_agent()` 主函数，收集 Trace |
| `backend/agent/hitl.py` | 实现 `HITLManager.create()`、`resolve()` 方法 |
| `backend/agent/router.py` | 实现 `determine_route()` —— 根据调用的工具名决定返回 `route` |
| `backend/api/agent.py` | 实现路由处理器（调用 `run_agent()`，处理 HITL 回传） |

**核心调用链**：
```
POST /api/agent/run
    → api/agent.py: agent_run()
        → agent/loop.py: run_agent()
            → PydanticAI agent.run()
                → 各工具函数（tools/*.py）
            → agent/router.py: determine_route()
            → 构造 AgentResponse 返回
```

---

### Epic 2：Intelligent GUI（前端负责人）

**需要实现的文件**：

| 文件 | 核心任务 |
|------|---------|
| `frontend/views/home_page.py` | 首页 UI |
| `frontend/views/auth_page.py` | 登录/注册页，成功后 emit `authenticated` signal |
| `frontend/views/dashboard_page.py` | **主界面协调器**，处理 AgentWorker 返回数据，分发给子组件 |
| `frontend/components/chat_widget.py` | 聊天消息列表 + 输入框，发送时 emit `message_submitted` |
| `frontend/components/trace_widget.py` | Thought Trace 面板，接收 `trace` 数据并渲染 |
| `frontend/components/hitl_dialog.py` | HITL 授权弹窗，用户操作后 emit `approved/rejected` |
| `frontend/workers/agent_worker.py` | **实现 `run()` 方法**（QThread 后台调用 API） |

**前端数据流**（以发消息为例）：
```
用户输入 → ChatWidget._on_send()
    → emit message_submitted
    → DashboardPage.send_message()
        → 创建 AgentWorker，worker.start()
        → AgentWorker.run() 在后台线程调用 api_client.agent_run()
        → emit response_ready(response_dict)
    → DashboardPage._on_agent_response()
        → chat_widget.add_message(assistant_message)
        → trace_widget.update_trace(trace)
        → 若 route=="scheduler"：切 Tab + schedule_widget.update_schedule()
        → 若 hitl_request 非 null：_show_hitl_dialog()
```

**重要约定**：
- 所有 HTTP 调用必须在 `AgentWorker`（QThread）里执行，**不得在主线程调用 requests**
- UI 更新必须在主线程，通过 Qt Signal 传递数据
- 所有 API 调用通过 `frontend/api/client.py` 的 `api_client` 单例，不得直接用 `requests`

---

### Epic 3：Multi-Source Scheduler（后端负责人）

**需要实现的文件**：

| 文件 | 核心任务 |
|------|---------|
| `backend/services/schedule_service/` | 实现 `fetch_blackboard()`、`fetch_course_schedule()`、`detect_conflicts()`（对外入口在 `__init__.py`） |
| `backend/agent/tools/scheduler.py` | 将 service 函数封装为 PydanticAI 工具（`@agent.tool` 装饰器） |
| `backend/api/schedule.py` | 实现 `/api/schedule/refresh` 路由 |

**CAS 登录流程参考**：
```python
# CAS 认证标准流程（仅供参考，需根据南科大实际接口调整）
# 1. GET https://cas.sustech.edu.cn/cas/login?service=<blackboard_url>
# 2. 解析 <input name="execution"> 的 value
# 3. POST 提交用户名/密码/execution
# 4. 获取重定向 URL 中的 ticket 参数
# 5. 使用 ticket 访问目标系统
```

---

### Epic 4：Campus Encyclopedia - RAG（后端负责人）

**需要实现的文件**：

| 文件 | 核心任务 |
|------|---------|
| `backend/database/chromadb.py` | 实现 `add_chunks()`、`delete_file_chunks()`、`query_collections()` |
| `backend/services/rag_service.py` | 实现 `resolve_collections()`（学科剪枝）、`format_rag_context()` |
| `backend/agent/tools/rag.py` | 实现 `query_rag()` 和 `classify_subject()` 工具 |

**RAG 工具调用链**：
```
用户："南科大挂科政策是什么？"
    → LLM 决策：调用 classify_subject("南科大挂科政策") → "policy"
    → LLM 调用：query_rag(query="挂科政策", subject_hint="policy")
        → rag_service.resolve_collections("policy") → ["policy", "other"]
        → chromadb.query_collections(query, ["policy", "other"])
        → 返回 top-k chunks
    → LLM 基于 chunks 生成回答，附带 citations
```

---

### Epic 5：Study Copilot（后端负责人）

**需要实现的文件**：

| 文件 | 核心任务 |
|------|---------|
| `backend/utils/document_parser.py` | 实现 `_parse_pdf()`、`_parse_pptx()`、`_parse_text()` |
| `backend/services/material_service.py` | 实现完整上传→解析→分类→切块→向量化流程 |
| `backend/agent/tools/study_copilot.py` | 实现 `generate_summary()`、`generate_quiz()`、`extract_key_concepts()` |

**文件上传向量化流程**：
```
POST /api/materials/upload (multipart)
    → material_service.upload_and_vectorize()
        ① 校验 MIME 类型和文件大小
        ② 保存文件到 data/uploads/{user_id}/{file_id}.ext
        ③ 写入 materials 表（vectorized=False）
        ④ document_parser.parse_document() 提取文本
        ⑤ classify_subject() 判断学科类型（LLM 调用）
        ⑥ _chunk_text() 切分文本
        ⑦ chromadb.add_chunks() 写入向量库
        ⑧ 更新 materials.vectorized = True
    → 返回 MaterialInfo（vectorized=True）
```

---

### Epic 6：OS Automation（后端负责人）

**需要实现的文件**：

| 文件 | 核心任务 |
|------|---------|
| `backend/agent/tools/os_automation.py` | 实现所有文件操作工具，**必须包含路径安全校验** |
| `backend/services/audit_service.py` | 实现操作日志写入 |

**HITL 触发机制（关键）**：

```python
# 每个高危工具的实现模板
@agent.tool
async def file_delete(ctx: RunContext[AgentDeps], path: str) -> str:
    safe = _safe_path(workspace, path)
    if not safe.exists():
        return "ERROR:FILE_NOT_FOUND"

    # 1. 注册挂起状态
    request_id = f"hitl_{ctx.deps.session_id}_{int(time.time())}"
    state = hitl_manager.create(
        request_id=request_id,
        session_id=ctx.deps.session_id,
        action=f"Delete file: {path}",
        risk="high",
    )

    # 2. 抛出异常，由 loop.py 捕获，向前端返回 hitl_request
    raise HITLInterrupt(
        state,
        payload=[f"Permanently delete '{path}'"],
        reason="File deletion is irreversible."
    )

    # 3. 代码到这里表示 HITL 已批准（由 loop.py 在审批后调用 resume_callback 继续）
    #    实际删除逻辑写在 resume_callback 里
```

**安全约束（必须强制执行）**：
1. 所有路径通过 `_safe_path()` 验证，防止路径穿越攻击
2. DELETE/UPDATE/RENAME 必须触发 HITL
3. 每次操作写入 `audit_logs` 表

---

## 8. 关键设计模式与约定

### 8.1 分层原则

```
API 路由层（api/）  ──只做──→  参数校验 + 调用 Service
Service 层（services/）  ──只做──→  业务逻辑 + 数据库操作
Agent 工具层（agent/tools/）  ──只做──→  调用 Service + 格式化返回给 LLM
```

**禁止**：API 路由直接操作数据库；Service 层直接返回 HTTP 响应。

### 8.2 错误返回约定

工具函数内的错误**以字符串形式返回给 LLM**（让 LLM 自行处理），不抛异常：

```python
# 正确方式
@agent.tool
async def fetch_blackboard_deadlines(ctx: RunContext[AgentDeps]) -> str:
    if not ctx.deps.cas_account:
        return "ERROR:CAS_NOT_CONFIGURED"  # LLM 读到后会告知用户去配置
    ...
```

API 路由层的错误通过 `HTTPException` 返回 HTTP 状态码：

```python
# 正确方式
@router.delete("/{file_id}")
async def delete_material(...):
    try:
        await material_service.delete_material(db, user.user_id, file_id)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not your file")
```

### 8.3 敏感信息操作规范

所有涉及 CAS 密码或 LLM API Key 的代码：

```python
# 写入前必须加密
from backend.utils.crypto import encrypt, decrypt

user.cas_password_encrypted = encrypt(plain_password)   # 存库
plain_password = decrypt(user.cas_password_encrypted)   # 用时解密
```

### 8.4 前端 HTTP 调用规范

```python
# 正确：在 QThread worker 中调用
class SomeWorker(QThread):
    result_ready = pyqtSignal(dict)
    def run(self):
        data = api_client.some_method()   # 这里可以阻塞
        self.result_ready.emit(data)

# 错误：直接在主线程/槽函数中调用（会冻结 UI）
def _on_button_click(self):
    data = api_client.some_method()   # ❌ 绝对不要这样写
```

### 8.5 数据库操作规范

```python
# Service 函数接收 AsyncSession，不自己创建
async def some_service_func(db: AsyncSession, ...) -> ...:
    result = await db.execute(select(User).where(...))
    await db.commit()
    return result.scalar()

# API 路由通过 Depends 注入 Session
@router.get(...)
async def some_route(db: AsyncSession = Depends(get_db)):
    return await some_service.func(db, ...)
```

---

## 9. 常见问题

**Q：我是前端成员，需要后端跑起来才能开发吗？**
A：不需要。`frontend/api/client.py` 里的方法当前全部 `raise NotImplementedError`。你可以在每个方法里先 `return` 硬编码的 mock 数据，等后端实现后再换成真实调用。

**Q：ChromaDB 需要单独启动服务吗？**
A：不需要。我们使用 `PersistentClient` 模式，ChromaDB 嵌入在进程内，数据持久化到 `./data/chromadb` 目录。

**Q：数据库表结构改变后怎么同步？**
A：修改 `backend/database/postgres.py` 中的 ORM 模型后，运行：
```bash
alembic revision --autogenerate -m "your description"
alembic upgrade head
```

**Q：如何测试 API 接口？**
A：后端启动后访问 `http://127.0.0.1:8000/docs`，FastAPI 自动生成 Swagger UI，可以直接在浏览器测试所有接口。

**Q：HITL 挂起状态服务重启后会丢失，怎么办？**
A：当前 milestone 设计为内存存储，重启后状态丢失。这意味着如果服务在 HITL 等待期间重启，前端需要重新发起请求。后续 Epic 7 可以考虑将状态持久化到 PostgreSQL。

**Q：DeepSeek API 怎么接入 PydanticAI？**
A：DeepSeek 兼容 OpenAI API 格式。在 `backend/agent/loop.py` 中：
```python
from pydantic_ai.models.openai import OpenAIModel
model = OpenAIModel(
    model_name=settings.DEEPSEEK_MODEL,   # "deepseek-chat"
    base_url=settings.DEEPSEEK_BASE_URL,  # "https://api.deepseek.com"
    api_key=user_llm_api_key,             # 从 AgentDeps 取，每用户独立
)
```
