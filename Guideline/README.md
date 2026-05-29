[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/py413vYq)

# Student Productivity Agent

> **Team 26s-13 · SUSTech Software Engineering Spring 2026**

一个面向南科大学生的 AI 智能体桌面应用，集成日程管理、校园百科、学习辅助与文件自动化四大能力。

---

## 目录

1. [项目概览](#1-项目概览)
2. [整体架构](#2-整体架构)
3. [目录结构](#3-目录结构)
4. [快速开始](#4-快速开始)
5. [运行说明](#5-运行说明)
6. [API 接口速览](#6-api-接口速览)
7. [数据库概览](#7-数据库概览)
8. [开发规范](#8-开发规范)
9. [测试指南](#9-测试指南)
10. [参考文档](#10-参考文档)

---

## 1. 项目概览

| Epic | 功能模块 | 状态 |
|------|----------|------|
| Epic 1 | **Agentic Loop** — PydanticAI 推理循环，驱动所有工具调用 | 框架已搭建，核心循环待实现 |
| Epic 2 | **Intelligent GUI** — PyQt6 三列布局（侧边栏 / 聊天 / Thought Trace）+ HITL 弹窗 | 主体完成，API 连接待完善 |
| Epic 3 | **Multi-Source Scheduler** — Blackboard DDL 爬取 + 教务课表 + 冲突检测 | 爬虫核心已完成 |
| Epic 4 | **Campus Encyclopedia (RAG)** — 向量检索校园政策问答 | 数据库与服务已搭建 |
| Epic 5 | **Study Copilot** — 教材上传、摘要生成、练习题 | 文件解析管道已搭建 |
| Epic 6 | **OS Automation** — 自然语言驱动的文件系统操作（含 HITL 安全审批） | 工具框架已搭建 |
| Epic 7 | **Client-Server Architecture** — FastAPI ↔ PyQt6 REST 全链路 | 路由与 Schema 完成 |

**技术栈**

| 层 | 技术 | 版本 |
|----|------|------|
| 后端框架 | FastAPI + Uvicorn | ≥ 0.111.0 |
| Agent 编排 | PydanticAI | ≥ 0.0.13 |
| LLM | DeepSeek（OpenAI 兼容接口） | deepseek-chat |
| 关系数据库 | PostgreSQL + SQLAlchemy (async) | ≥ 2.0.0 |
| 向量数据库 | ChromaDB（进程内，无需独立服务） | ≥ 0.5.0 |
| 认证 | JWT (python-jose) + bcrypt | ≥ 3.3.0 |
| 加密 | Fernet (cryptography) | ≥ 42.0.0 |
| 网络爬虫 | httpx + BeautifulSoup4 + Selenium | ≥ 0.27.0 |
| 文档解析 | PyMuPDF + python-pptx | ≥ 1.24.0 |
| 前端 GUI | PyQt6 | ≥ 6.7.0 |
| Python | CPython | 3.10 |

---

## 2. 整体架构

```
┌──────────────────────────────────────────────────────────────┐
│                       PyQt6 Frontend                         │
│                                                              │
│  ┌─────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │  Left Panel │  │  Center Panel    │  │  Right Panel   │  │
│  │             │  │                  │  │                │  │
│  │ 对话历史     │  │ Chat / Schedule  │  │ Thought Trace  │  │
│  │ 教材列表     │  │ Encyclopedia     │  │   Panel        │  │
│  │ 用户信息     │  │ (Tab 切换)       │  │                │  │
│  └─────────────┘  └──────────────────┘  └────────────────┘  │
│                          │  HTTP/REST (requests)              │
└──────────────────────────┼───────────────────────────────────┘
                           │
                    REST API (JSON)
                    localhost:8000
                           │
┌──────────────────────────┼───────────────────────────────────┐
│                   FastAPI Backend                             │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    API Routers                        │   │
│  │  /auth  /user  /agent/*  /materials  /dashboard       │   │
│  │  /schedule                                            │   │
│  └────────────────────────┬─────────────────────────────┘   │
│                            │                                  │
│  ┌────────────────────────▼─────────────────────────────┐   │
│  │             PydanticAI Agent Loop                     │   │
│  │                                                       │   │
│  │  Perception → Reasoning → Tool Use → Observation     │   │
│  │                                                       │   │
│  │  Tools: scheduler | rag | os_automation | copilot    │   │
│  └────────────────────────┬─────────────────────────────┘   │
│                            │                                  │
│  ┌──────────┐  ┌──────────▼──────────┐  ┌───────────────┐  │
│  │ DeepSeek │  │    PostgreSQL        │  │   ChromaDB    │  │
│  │  LLM API │  │ users / sessions /  │  │ (21 学科向量  │  │
│  │          │  │ materials / audit   │  │   Collection) │  │
│  └──────────┘  └─────────────────────┘  └───────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

**数据流**

1. 用户在 PyQt6 发消息 → `ChatWidget` emit signal → `DashboardPage.send_message()`
2. `AgentWorker`（QThread）调用 `POST /api/agent/run`，不阻塞 UI
3. FastAPI 路由验证 JWT → 调用 `run_agent()`
4. PydanticAI Agent 分析消息 → 选择工具 → 执行工具 → 收集 Trace
5. `AgentResponse` 返回前端 → 分发给聊天区、Trace 面板、Schedule/Encyclopedia 标签
6. 若遇到高危操作 → 工具抛出 `HITLInterrupt` → 返回 `hitl_request` → 前端弹出授权窗口

---

## 3. 目录结构

```
team-project-26spring-26s-13/
│
├── README-Given by Teacher.md       # 教师提供的原始前端说明
├── proposal-26s-13.md               # 项目需求分析文档
├── requirements.txt                 # pip 依赖（前后端全部）
├── alembic.ini                      # Alembic 迁移配置
├── .env                             # 本地环境变量（不提交 git）
│
├── backend/                         # FastAPI 后端
│   ├── main.py                      # 应用入口，注册路由，配置 CORS
│   ├── config.py                    # 全局配置（读取 .env）
│   │
│   ├── database/
│   │   ├── postgres.py              # SQLAlchemy 异步引擎 + ORM 模型（5 张表）
│   │   └── chromadb.py              # ChromaDB 客户端 + CRUD（21 个 Collection）
│   │
│   ├── schemas/                     # Pydantic 请求/响应模型
│   │   ├── agent.py                 # AgentRequest / AgentResponse（核心 schema）
│   │   ├── auth.py                  # 注册/登录
│   │   ├── dashboard.py             # Bootstrap 响应
│   │   ├── material.py              # 教材文件信息
│   │   └── user.py                  # 用户 profile
│   │
│   ├── api/                         # HTTP 路由（仅参数校验 + 调用 service）
│   │   ├── deps.py                  # JWT 鉴权 dependency（get_current_user）
│   │   ├── auth.py                  # POST /api/auth/*
│   │   ├── user.py                  # GET/PUT /api/user/*
│   │   ├── agent.py                 # POST /api/agent/run（核心入口）
│   │   ├── materials.py             # GET/POST/DELETE /api/materials/*
│   │   ├── dashboard.py             # GET /api/dashboard/bootstrap
│   │   └── schedule.py              # POST /api/schedule/refresh
│   │
│   ├── agent/                       # PydanticAI Agent 逻辑
│   │   ├── core.py                  # Agent 单例 + AgentDeps 定义（循环导入隔离）
│   │   ├── loop.py                  # Agent 主循环（run_agent 实现）
│   │   ├── hitl.py                  # HITL 挂起状态管理（内存 HITLManager）
│   │   ├── router.py                # 工具调用 → 前端 route 推断
│   │   ├── prompt.py                # System prompt 模板
│   │   └── tools/
│   │       ├── scheduler.py         # Epic 3：Blackboard/教务爬取工具
│   │       ├── rag.py               # Epic 4：RAG 检索工具
│   │       ├── study_copilot.py     # Epic 5：摘要/练习题生成工具
│   │       └── os_automation.py     # Epic 6：文件系统工具（含 HITL）
│   │
│   ├── services/                    # 业务逻辑层
│   │   ├── auth_service.py          # 注册/登录/JWT 签发（已实现）
│   │   ├── user_service.py          # 用户 profile 更新
│   │   ├── material_service.py      # 文件上传 + 向量化流程
│   │   ├── rag_service.py           # RAG 学科剪枝 + 上下文格式化
│   │   ├── dashboard_service.py     # Bootstrap 数据组装
│   │   ├── audit_service.py         # OS 操作审计日志
│   │   └── schedule_service/        # 日程爬取与冲突检测（拆包）
│   │       ├── fetch_bb.py          # Blackboard CAS 登录 + DDL 爬取（~834 行）
│   │       ├── fetch_tis.py         # 教务系统课表爬取（~558 行）
│   │       ├── conflicts.py         # 冲突检测算法
│   │       ├── constants.py         # 课程时间常量映射
│   │       ├── personal.py          # 个人日程管理
│   │       └── refresh.py           # 刷新入口
│   │
│   └── utils/
│       ├── crypto.py                # Fernet 加解密（CAS 密码 / API Key）
│       └── document_parser.py       # PDF / PPT / MD 文本提取
│
├── frontend/                        # PyQt6 客户端
│   ├── app.py                       # 完整单文件原型（Teacher 版前端）
│   ├── main.py                      # 模块化入口（健康检查 → HomePage）
│   ├── config.py                    # API_BASE_URL 配置
│   ├── i18n.py                      # 中英双语文本
│   ├── mock_data.py                 # 本地 Mock 数据
│   ├── styles.py                    # 全局 QSS 样式
│   │
│   ├── api/
│   │   └── client.py                # HTTP 客户端（所有 API 调用封装）
│   │
│   ├── views/
│   │   ├── auth_page.py             # 登录/注册页
│   │   └── dashboard_page.py        # 主界面协调器
│   │
│   ├── components/
│   │   ├── chat_widget.py           # 聊天消息列表 + 输入框
│   │   ├── trace_widget.py          # Thought Trace 面板
│   │   ├── schedule_widget.py       # 日程展示
│   │   ├── encyclopedia_widget.py   # 百科结果展示
│   │   ├── materials_widget.py      # 教材列表（上传/删除）
│   │   └── hitl_dialog.py           # 高危操作授权弹窗
│   │
│   └── workers/
│       └── agent_worker.py          # QThread：后台调用 /api/agent/run
│
├── alembic/                         # 数据库迁移文件（仅供参考，见注意事项）
│   ├── env.py
│   └── versions/
│       └── d8ff1092fce2_init.py     # 初始建表迁移
│
└── Guideline/                       # 项目文档与规范（开发参考）
    ├── README.md                    # 详细框架说明（本文件）
    ├── environment.yml              # conda 环境配置
    ├── 整体架构图.jpg
    ├── Task Trace.txt               # 任务完成情况追踪
    ├── Github Information/
    │   └── Student Productivity Agent Project View.tsv
    └── docs/Frontend Relevant/
        ├── backend-interface-contract.md
        ├── backend-interface-contract-zh.md
        ├── backend-readme-zh.md
        └── frontend-api-connection-zh.md
```

---

## 4. 快速开始

### 4.1 克隆仓库

```bash
git clone https://github.com/sustech-cs304/team-project-26spring-26s-13.git
cd team-project-26spring-26s-13
```

### 4.2 创建 conda 虚拟环境

```bash
# 一键安装所有依赖（推荐）
conda env create -f Guideline/environment.yml

# 激活环境
conda activate software-engineering
```

> 或者使用 pip：
> ```bash
> pip install -r requirements.txt
> ```

### 4.3 配置环境变量

在项目根目录创建 `.env` 文件（**不要提交到 git**）：

```env
# PostgreSQL 连接字符串（数据库名 software-engineering）
POSTGRES_DSN=postgresql+asyncpg://postgres:yourpassword@localhost:5432/software-engineering

# Fernet 加密密钥（用于 CAS 密码 / API Key 加密存储）
FERNET_KEY=your_fernet_key_here

# JWT 签名密钥
SECRET_KEY=your_jwt_secret_here

# DeepSeek API（可选，用户也可在 GUI 中填写）
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

生成 Fernet Key：
```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

### 4.4 初始化数据库

> ⚠️ **注意**：`alembic upgrade head` 因异步驱动兼容问题无法自动建表，请使用以下方式手动建表。

**第一步**：在 PostgreSQL 中创建数据库（DataGrip 或 psql）：
```sql
CREATE DATABASE "software-engineering";
```

**第二步**：在 `software-engineering` 数据库中执行以下 SQL 建表：

```sql
  -- ==========================================                                                                                                     
  -- 1. 删除已存在的表（CASCADE 处理外键依赖）
  -- ==========================================                                                                                                       DROP TABLE IF EXISTS audit_logs CASCADE;
  DROP TABLE IF EXISTS materials CASCADE;                                                                                                           
  DROP TABLE IF EXISTS chat_messages CASCADE;
  DROP TABLE IF EXISTS chat_sessions CASCADE;
  DROP TABLE IF EXISTS personal_tasks CASCADE;
  DROP TABLE IF EXISTS users CASCADE;
  DROP TABLE IF EXISTS alembic_version CASCADE;

  -- ==========================================
  -- 2. 重新创建表（按依赖顺序：先父表，后子表）
  -- ==========================================

  CREATE TABLE IF NOT EXISTS alembic_version (
      version_num VARCHAR(32) NOT NULL PRIMARY KEY
  );

  CREATE TABLE IF NOT EXISTS users (
      user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      username VARCHAR(64) NOT NULL UNIQUE,
      password_hash VARCHAR(256) NOT NULL,
      display_name VARCHAR(128) NOT NULL,
      major VARCHAR(128) NOT NULL,
      cas_account VARCHAR(128),
      cas_password_encrypted BYTEA,
      llm_api_key_encrypted BYTEA,
      working_dir VARCHAR(512),
      preferences JSONB NOT NULL DEFAULT '{}',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  );

  CREATE TABLE IF NOT EXISTS chat_sessions (
      session_id VARCHAR(128) PRIMARY KEY,
      user_id UUID NOT NULL REFERENCES users(user_id),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
  );

  CREATE TABLE IF NOT EXISTS chat_messages (
      message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      session_id VARCHAR(128) NOT NULL REFERENCES chat_sessions(session_id),
      role VARCHAR(16) NOT NULL CHECK (role IN ('user', 'assistant')),
      content TEXT NOT NULL,
      timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
  );

  CREATE TABLE IF NOT EXISTS materials (
      file_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id UUID NOT NULL REFERENCES users(user_id),
      file_name VARCHAR(256) NOT NULL,
      file_type VARCHAR(128) NOT NULL,
      file_path VARCHAR(512) NOT NULL,
      subject_type VARCHAR(32) NOT NULL DEFAULT 'other',
      file_hash VARCHAR(64),
      vectorized BOOLEAN NOT NULL DEFAULT FALSE,
      is_public BOOLEAN NOT NULL DEFAULT FALSE,
      uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
  );

  CREATE TABLE IF NOT EXISTS personal_tasks (
      task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id UUID NOT NULL REFERENCES users(user_id),
      title VARCHAR(256) NOT NULL,
      description TEXT,
      start_time TIMESTAMPTZ NOT NULL,
      end_time TIMESTAMPTZ,
      location VARCHAR(256),
      is_done BOOLEAN NOT NULL DEFAULT FALSE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  );

  CREATE TABLE IF NOT EXISTS audit_logs (
      log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id UUID NOT NULL REFERENCES users(user_id),
      session_id VARCHAR(128) NOT NULL,
      action_type VARCHAR(32) NOT NULL,
      target_path VARCHAR(1024) NOT NULL,
      description TEXT NOT NULL,
      hitl_required BOOLEAN NOT NULL DEFAULT FALSE,
      hitl_approved BOOLEAN,
      executed_at TIMESTAMPTZ NOT NULL DEFAULT now()
  );

  -- ==========================================
  -- 3. 标记 Alembic 已到最新版本
  -- ==========================================
  INSERT INTO alembic_version (version_num) VALUES ('28298627bda6')
  ON CONFLICT DO NOTHING;

```

---

## 5. 运行说明

### 5.1 启动后端服务

```bash
python -m backend.main
```

后端启动后：
- API 服务：`http://127.0.0.1:8000`
- Swagger 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`

### 5.2 启动前端

**方式一：单文件原型前端**（内置 Mock 模式，无需后端）

```bash
# 本地 Mock 模式（默认，无需后端）
python frontend/app.py

# 连接本地后端（Windows）
$env:SPA_API_BASE_URL = "http://127.0.0.1:8000"
python frontend/app.py
```

**方式二：模块化前端**（依赖后端运行）

```bash
python -m frontend.main
```

### 5.3 一键启动（推荐）

项目根目录提供 `run.py` 自动化脚本，可同时启动前后端，无需开两个终端：

```bash
python run.py          # 同时启动后端 + 前端（默认）
python run.py test     # 运行测试套件
python run.py format   # 用 black 格式化代码
python run.py lint     # 用 flake8 检查代码
```

脚本会先启动后端并等待 2 秒，再拉起前端（自动注入 `SPA_API_BASE_URL`），按 `Ctrl+C` 可同时关闭两个进程。

### 5.4 完整开发环境启动顺序

```
1. 启动 PostgreSQL 服务
2. 确认数据库表已建好（见 4.4）
3. python run.py        # 一键启动前后端（或分终端手动启动）
```

---

## 6. API 接口速览

所有接口均需 `Authorization: Bearer <token>` Header，**除了** `/api/auth/register` 和 `/api/auth/login`。

| Method | Path | 描述 |
|--------|------|------|
| POST | `/api/auth/register` | 注册新用户 |
| POST | `/api/auth/login` | 登录，返回 JWT token |
| POST | `/api/auth/logout` | 登出 |
| GET | `/api/user/profile` | 获取用户 profile |
| PUT | `/api/user/profile` | 更新 display_name / major / preferences |
| PUT | `/api/user/credentials` | 更新 CAS 账号密码 / LLM API Key |
| GET | `/api/dashboard/bootstrap` | 一次性拉取主界面初始数据 |
| **POST** | **`/api/agent/run`** | **Agent 核心入口（对话 + HITL 审批）** |
| GET | `/api/agent/sessions` | 历史会话列表 |
| DELETE | `/api/agent/sessions/{id}` | 删除会话 |
| GET | `/api/materials` | 获取教材列表 |
| POST | `/api/materials/upload` | 上传教材（触发自动向量化） |
| DELETE | `/api/materials/{file_id}` | 删除教材 |
| POST | `/api/schedule/refresh` | 手动刷新日程（触发 Blackboard 爬取） |

**Agent 核心响应结构**：

```json
{
  "session_id": "sess_20260413_a1b2c3",
  "assistant_message": { "role": "assistant", "content": "...", "timestamp": "..." },
  "trace": [
    { "phase": "Observation", "title": "分析用户目标", "status": "done", "timestamp": "..." },
    { "phase": "Tool Use",    "title": "fetch_blackboard_deadlines", "status": "done", "timestamp": "..." }
  ],
  "route": "scheduler",
  "ui_payload": { "schedule": { "events": [...], "conflicts": [] }, "encyclopedia": null },
  "hitl_request": null,
  "error": null
}
```

`route` 枚举：`chat` | `scheduler` | `encyclopedia` | `os_automation`

> 详细接口文档见 [`Guideline/docs/Frontend Relevant/backend-interface-contract-zh.md`](Guideline/docs/Frontend%20Relevant/backend-interface-contract-zh.md)

---

## 7. 数据库概览

### PostgreSQL（5 张表）

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `users` | 用户账号与配置 | `user_id`, `username`, `cas_password_encrypted`, `llm_api_key_encrypted` |
| `chat_sessions` | 对话会话 | `session_id`, `user_id`, `updated_at` |
| `chat_messages` | 对话消息 | `message_id`, `session_id`, `role`, `content` |
| `materials` | 上传教材 | `file_id`, `subject_type`, `vectorized`, `file_path` |
| `audit_logs` | OS 操作审计 | `action_type`, `target_path`, `hitl_required`, `hitl_approved` |

> **安全约定**：`cas_password_encrypted` 和 `llm_api_key_encrypted` 必须通过 `backend/utils/crypto.py` 的 `encrypt()`/`decrypt()` 读写，禁止明文存储。

### ChromaDB（21 个 Collection）

按学科分集合：`cs` / `electronics` / `materials` / `math` / `physics` / `chemistry` / `biology` / `geography` / `philosophy` / `history` / `literature` / `politics` / `finance` / `statistics` / `ocean` / `economics` / `law` / `management` / `medicine` / `policy` / `other`

RAG 查询策略：LLM 判断学科 → 查对应集合 + `other`（`other` 集合每次必查）

---

## 8. 开发规范

### 分层原则

```
API 路由层（api/）        → 只做参数校验 + 调用 Service
Service 层（services/）  → 业务逻辑 + 数据库操作
Agent 工具层（tools/）   → 调用 Service + 格式化返回给 LLM
```

### 前端线程规范

```python
# 正确：所有 HTTP 调用必须在 QThread 中执行
class AgentWorker(QThread):
    response_ready = pyqtSignal(dict)
    def run(self):
        data = api_client.agent_run(request)   # 可阻塞
        self.response_ready.emit(data)

# 错误：直接在主线程/槽函数中调用（会冻结 UI）
def _on_button_click(self):
    data = api_client.agent_run(request)   # ❌ 禁止
```

### 错误返回约定

- **工具函数内**：以字符串 `"ERROR:XXX"` 返回给 LLM，让 LLM 自行处理，不抛异常
- **API 路由层**：通过 `HTTPException` 返回 HTTP 状态码

### HITL 高危操作流程

DELETE / RENAME 等高危操作 → 工具抛出 `HITLInterrupt` → `run_agent()` 捕获 → 返回 `hitl_request` → 前端弹出授权窗 → 用户审批后再次调用 `POST /api/agent/run` 携带 `hitl_reply`

---

## 9. 测试指南

### 9.1 概览

测试套件使用 **pytest + pytest-asyncio**，以 SQLite（`test.db`）替代 PostgreSQL，无需启动任何外部服务即可在本地或 CI 中运行。全套 90 个测试用例覆盖后端 API 路由、业务逻辑与工具层。

| 测试文件 | 覆盖范围 | 测试数 |
|---|---|---|
| `tests/test_main.py` | 健康检查、OpenAPI 文档可访问性 | 3 |
| `tests/test_auth.py` | 注册、登录、登出（含边界校验） | 8 |
| `tests/test_user.py` | 获取/更新用户 Profile | 6 |
| `tests/test_user_credentials.py` | 更新 CAS 账号/密码、LLM API Key | 8 |
| `tests/test_materials.py` | 教材列表/上传/删除（向量化已 mock） | 7 |
| `tests/test_schedule.py` | 日程刷新（爬虫已 mock） | 4 |
| `tests/test_dashboard.py` | Dashboard bootstrap 初始化数据 | 6 |
| `tests/test_agent_sessions.py` | 会话列表/详情/删除 + `/agent/run` HTTP 契约 | 12 |
| `tests/test_crypto.py` | `encrypt`/`decrypt` 纯单元测试 | 8 |
| `tests/test_conflicts.py` | 冲突检测算法纯单元测试 | 28 |

---

### 9.2 依赖安装

测试专用依赖定义在 `requirements-dev.txt`，在项目 conda 环境中一次性安装：

```bash
# 激活环境
conda activate software-engineering

# 安装测试依赖
pip install -r requirements-dev.txt
```

`requirements-dev.txt` 包含：

```
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-cov>=5.0.0
httpx>=0.27.0
aiosqlite>=0.19.0
pytest-mock>=3.14.0
flake8>=7.0.0
black>=24.0.0
```

---

### 9.3 运行测试

在项目根目录下执行（需先激活 conda 环境）：

```bash
# 运行全部测试（必须用 python -m pytest，否则 backend 模块找不到）
python -m pytest tests/

# 带覆盖率报告
python -m pytest tests/ --cov=backend --cov-report=term-missing

# 生成 XML 覆盖率报告（CI 用）
python -m pytest tests/ --cov=backend --cov-report=xml

# 只运行某个文件
python -m pytest tests/test_auth.py

# 只运行某个测试函数
python -m pytest tests/test_auth.py::test_register_success

# 失败立刻停止（调试用）
python -m pytest tests/ -x

# 详细输出
python -m pytest tests/ -v
```

> **注意**：测试运行后会在项目根目录生成 `test.db`（SQLite 测试数据库），已加入 `.gitignore`，不应提交。

---

### 9.4 conftest 设计说明

`tests/conftest.py` 是整个测试套件的基础，解决了几个关键兼容性问题：

#### 环境变量预注入

```python
# conftest.py 顶部 — 必须在所有 backend 模块导入前执行
os.environ.setdefault("POSTGRES_DSN", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("SECRET_KEY",   "test-secret-key-for-pytest")
os.environ.setdefault("FERNET_KEY",   "dmFsaWRiYXNlNjRlbmNvZGVkZmVybmV0a2V5MDAwMDA=")
```

这使得 `backend/config.py` 的 `Settings` 读取到测试值，而不会尝试连接真实的 PostgreSQL。

#### SQLite 类型兼容补丁

ORM 模型使用 PostgreSQL 专用类型（`JSONB`、`UUID`），SQLite 不认识，需在导入 backend 前打补丁：

```python
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# DDL 补丁：建表时将 JSONB/UUID 映射为 SQLite 支持的类型
SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"
SQLiteTypeCompiler.visit_UUID  = lambda self, type_, **kw: "VARCHAR(36)"

# 运行时补丁：UUID bind/result processor 支持字符串形式的 UUID
# （JWT decode 后 user_id 是 str，需能直接传给 db.get(User, user_id)）
from sqlalchemy.sql import sqltypes as _sa_sqltypes
_sa_sqltypes.Uuid.bind_processor   = _patched_uuid_bind
_sa_sqltypes.Uuid.result_processor = _patched_uuid_result
```

#### 数据库隔离

每个测试函数执行前建表、执行后删表，保证测试间完全隔离：

```python
@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
```

#### 内置 Fixtures

| Fixture | 类型 | 说明 |
|---|---|---|
| `async_client` | `AsyncClient` | 绑定到 FastAPI app 的异步 HTTP 客户端 |
| `registered_user` | `dict` | 已注册的测试用户，返回 `AuthResponse` dict（含 `token`, `user_id`） |
| `auth_headers` | `dict` | 含有效 JWT 的 `Authorization` 请求头 |
| `setup_database` | autouse | 每个测试函数前建表/后删表，自动注入 |

---

### 9.5 编写新测试

#### 基本模板

```python
# tests/test_my_feature.py
from httpx import AsyncClient

# 需要认证的接口
async def test_something_authenticated(async_client: AsyncClient, auth_headers: dict):
    resp = await async_client.get("/api/some/endpoint", headers=auth_headers)
    assert resp.status_code == 200
    assert "expected_field" in resp.json()

# 不需要认证的接口
async def test_something_public(async_client: AsyncClient):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
```

#### Mock 外部依赖

涉及 LLM 调用、文件系统、网络爬虫的测试，必须 mock 对应的 service 函数：

```python
from unittest.mock import AsyncMock, patch

async def test_upload_material(async_client: AsyncClient, auth_headers: dict):
    with patch(
        "backend.services.material_service.upload_and_vectorize",
        new_callable=AsyncMock,
        return_value={"file_id": "...", "file_name": "test.pdf", ...},
    ):
        resp = await async_client.post("/api/materials/upload", ...)
    assert resp.status_code == 201
```

#### 直接操作测试数据库

如需在测试中预置数据（不通过 HTTP），使用 `TestSessionLocal`：

```python
from tests.conftest import TestSessionLocal
from backend.database.postgres import ChatSession
import uuid, datetime

@pytest_asyncio.fixture
async def seeded_session(registered_user):
    async with TestSessionLocal() as db:
        sess = ChatSession(
            session_id="sess_test_001",
            user_id=uuid.UUID(registered_user["user_id"]),  # 注意：必须传 uuid.UUID 对象
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow(),
        )
        db.add(sess)
        await db.commit()
    return "sess_test_001"
```

> ⚠️ 预置数据时 `user_id` 必须传 `uuid.UUID` 对象而非字符串，否则 SQLAlchemy 的 bind processor 会报错。

#### 无需数据库的纯单元测试

对于 `backend/services/schedule_service/conflicts.py` 这类纯函数，直接导入测试，无需任何 fixture：

```python
from backend.services.schedule_service.conflicts import detect_conflicts
from backend.services.schedule_service.constants import Deadline, CourseOccurrence
from datetime import datetime

def test_no_conflicts():
    result = detect_conflicts([], [])
    assert result.events == []
    assert result.conflicts == []
```

#### 认证状态码说明

FastAPI 0.135+ 对缺少 Bearer token 的请求返回 **401**（而非旧版的 403）。编写未认证测试时请使用：

```python
assert resp.status_code in (401, 403)  # 兼容不同 FastAPI 版本
```

---

### 9.6 CI 自动化（GitHub Actions）

CI 配置位于 `.github/workflows/ci.yml`，每次向 `main` 分支 push 或发起 PR 时自动触发，执行以下步骤：

```
1. 检出代码
2. 设置 Python 3.10
3. pip install -r requirements.txt -r requirements-dev.txt
4. black --check .          # 格式检查
5. flake8 .                 # Lint 检查
6. python -m pytest tests/ --cov=backend --cov-report=xml
7. 上传覆盖率报告到 Codecov
```

> **注意**：CI 中测试同样使用 SQLite，无需配置真实数据库。所有网络/LLM 调用均通过 `unittest.mock` 在测试层面拦截。

如需在本地模拟 CI 完整流程：

```bash
black --check .
flake8 .
python -m pytest tests/ --cov=backend --cov-report=term-missing
```

---

## 10. 参考文档

| 文档 | 说明 |
|------|------|
| [`Guideline/README.md`](Guideline/README.md) | **开发必读**：详细框架说明、Epic 负责矩阵、设计约定（中文） |
| [`Guideline/Task Trace.txt`](Guideline/Task%20Trace.txt) | 已完成与待完成任务追踪 |
| [`Guideline/environment.yml`](Guideline/environment.yml) | conda 环境配置 |
| [`Guideline/docs/Frontend Relevant/backend-interface-contract-zh.md`](Guideline/docs/Frontend%20Relevant/backend-interface-contract-zh.md) | 后端接口契约（中文） |
| [`Guideline/docs/Frontend Relevant/backend-interface-contract.md`](Guideline/docs/Frontend%20Relevant/backend-interface-contract.md) | Backend Interface Contract (English) |
| [`Guideline/docs/Frontend Relevant/frontend-api-connection-zh.md`](Guideline/docs/Frontend%20Relevant/frontend-api-connection-zh.md) | 前端 API 对接说明 |
| [`proposal-26s-13.md`](proposal-26s-13.md) | 项目需求分析 |
| `http://127.0.0.1:8000/docs` | FastAPI Swagger UI（后端运行后可访问） |
