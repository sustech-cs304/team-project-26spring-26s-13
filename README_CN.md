# Student Productivity Agent

面向南科大学生的 AI 智能体桌面助手，集成日程管理、校园百科、学习辅助、图书馆讨论间查询、邮件服务、Blackboard 课件批量爬取与文件自动化操作，以统一的对话式界面呈现。

![Python](https://img.shields.io/badge/Python-3.10-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-green)
![PyQt6](https://img.shields.io/badge/PyQt6-6.7+-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 目录

- [核心功能](#核心功能)
- [架构概览](#架构概览)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
  - [前置要求](#前置要求)
  - [安装](#安装)
  - [配置](#配置)
  - [数据库初始化](#数据库初始化)
- [运行系统](#运行系统)
- [使用示例](#使用示例)
- [截图展示](#截图展示)
- [项目结构](#项目结构)
- [API 接口概览](#api-接口概览)
- [测试](#测试)
- [CI/CD 流水线](#cicd-流水线)
- [已知问题与限制](#已知问题与限制)
- [参考文档](#参考文档)
- [团队](#团队)

---

## 核心功能(Features)

### 1. 多源日程管理 (Multi-Source Scheduler)
自动爬取南科大教务日历与 Blackboard DDL，检测与个人待办的时间冲突，支持通过自然语言进行查看、完成、删除等操作，动态生成学习日程。

### 2. Blackboard 课件批量爬取与 RAG 入库 (Batch BB Material Crawler & RAG Ingestion)
通过 CAS 认证登录南科大 Blackboard，BFS 遍历所有已选课程内容页面发现可下载文件，并行下载并自动过滤当前学期课件。每个文件经过类型校验（PDF/PPT/PPTX/Markdown/DOCX）→ 文本解析 → LLM 学科分类（20+ 类）→ 语义分块 → ChromaDB 向量化，立即可供 RAG 检索使用。

### 3. 校园百科 (Campus Encyclopedia)
基于 RAG 的智能问答系统，可回答校园相关政策问题（如学位要求、宿舍规定等）。系统将官方文档（如南科大学生手册）提前分块存入 ChromaDB 的 21 个学科集合中，查询时通过 LLM 判断学科后精准检索对应集合。

### 4. 图书馆讨论间查询 (Library Discussion Room Query)
根据地点、时间段和人数要求查询南科大图书馆讨论间的实时空闲情况，返回可用房间列表，方便学生规划小组学习。

### 5. 学习助手 (Study Copilot)
处理用户上传或本地的学术资料（PPT、PDF、Markdown 笔记等），自动提取核心概念、生成学习摘要并创建自定义练习题。

### 6. 邮件服务 (Email Service)
支持将对话摘要或学习资料以 Markdown 附件形式发送至用户的南科大邮箱。可附带知识库中的原始资料文件（zip 压缩打包），当用户说"发邮件""mail me"时自动触发。

### 7. 操作系统文件自动化 (System-Level OS Automation)
通过自然语言指令执行文件操作（读取、创建、删除、批量重命名等），所有写操作必须在独立的用户工作空间内进行，且需要经过 HITL（Human-in-the-Loop）授权弹窗审批后方可执行，所有操作均记录审计日志。

---

## 架构概览

系统采用 **Client-Server RESTful** 框架下的 **单体分层架构**：

```
┌──────────────────────────────────────────────────────────────┐
│                       PyQt6 前端                              │
│  ┌─────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │   左侧面板   │  │     中央面板      │  │    右侧面板     │  │
│  │  对话历史     │  │  聊天 / 日程     │  │  推理追踪面板   │  │
│  │  教材列表     │  │  校园百科        │  │                │  │
│  │  事务列表     │  │  图书馆讨论间    │  │                │  │
│  └─────────────┘  └──────────────────┘  └────────────────┘  │
│                          │  HTTP/REST                         │
└──────────────────────────┼───────────────────────────────────┘
                           │
┌──────────────────────────┼───────────────────────────────────┐
│                   FastAPI 后端                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │              PydanticAI Agent 推理循环                 │    │
│  │  感知 → 推理 → 工具调用 → 观察                        │    │
│  └──────────────────────────────────────────────────────┘    │
│  ┌──────────┐  ┌───────────────────┐  ┌───────────────┐     │
│  │ DeepSeek │  │    PostgreSQL      │  │   ChromaDB    │     │
│  │  LLM API │  │ 6 张表 (users,    │  │ 21 个学科     │     │
│  │          │  │ sessions, tasks...)│  │ 向量集合      │     │
│  └──────────┘  └───────────────────┘  └───────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

**核心设计决策：**

- **安全封装**：前端不直接访问数据库，所有敏感凭据（CAS 密码、API Key）使用 Fernet 加密存储，仅在后端 Service 层解密使用。
- **非阻塞体验**：耗时推理和网络爬取在后台执行；PyQt6 前端通过 `QThread` Worker 调用后端 API，确保 UI 始终响应。
- **HITL 安全机制**：所有高危文件操作被拦截并呈现给用户审批，通过专门的授权弹窗确认后才执行。
- **流式响应**：Agent 支持实时流式响应，前端可边接收边展示部分结果和推理追踪信息。

---

## 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 后端框架 | FastAPI + Uvicorn | >= 0.111.0 |
| Agent 编排 | PydanticAI | >= 0.0.13 |
| 大语言模型 | DeepSeek（OpenAI 兼容接口） | deepseek-chat |
| 关系数据库 | PostgreSQL + SQLAlchemy (async) | >= 2.0.0 |
| 向量数据库 | ChromaDB（进程内，无需独立服务） | >= 0.5.0 |
| 认证 | JWT (python-jose) + bcrypt | >= 3.3.0 |
| 加密 | Fernet (cryptography) | >= 42.0.0 |
| 网络爬虫 | httpx + BeautifulSoup4 + Selenium | >= 0.27.0 |
| 文档解析 | PyMuPDF + python-pptx + python-docx | >= 1.24.0 |
| OCR | PaddleOCR + PaddlePaddle | - |
| 邮件 | SMTP (Gmail) | - |
| 前端 GUI | PyQt6 | >= 6.7.0 |
| Python | CPython | 3.10 |

---

## 快速开始

### 前置要求

- **Python 3.10**
- **PostgreSQL 15+**（本地运行）
- **conda**（推荐）或 pip

### 安装

1. **克隆仓库：**

   ```bash
   git clone https://github.com/sustech-cs304/team-project-26spring-26s-13.git
   cd team-project-26spring-26s-13
   ```

2. **创建并激活 conda 环境：**

   ```bash
   conda env create -f Guideline/environment.yml
   conda activate software-engineering
   ```

   或使用 pip：

   ```bash
   pip install -r requirements.txt
   ```

3. **安装开发依赖**（用于测试）：

   ```bash
   pip install -r requirements-dev.txt
   ```

### 配置

在项目根目录创建 `.env` 文件：

```env
# PostgreSQL 连接字符串
POSTGRES_DSN=postgresql+asyncpg://postgres:yourpassword@localhost:5432/software-engineering

# Fernet 加密密钥（用于 CAS 密码 / API Key 加密存储）
FERNET_KEY=your_fernet_key_here

# JWT 签名密钥
SECRET_KEY=your_jwt_secret_here

# DeepSeek API（可选，用户也可在 GUI 设置中填写）
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_API_KEY=your_deepseek_api_key

# 邮件服务（可选，用于发送邮件）
SPA_SMTP_HOST=smtp.gmail.com
SPA_SMTP_PORT=587
SPA_SMTP_USER=your_email@gmail.com
SPA_SMTP_PASSWORD=your_app_password
```

生成 Fernet Key：

```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

### 数据库初始化

1. 在 PostgreSQL 中创建数据库：

   ```sql
   CREATE DATABASE "software-engineering";
   ```

2. 在 `software-engineering` 数据库中执行建表 SQL（完整 DDL 脚本见 [Guideline/README.md](Guideline/README.md#44-初始化数据库)）。

> **注意：** Alembic 迁移因异步驱动兼容性问题可能无法正常工作，建议手动建表。后端也支持通过 `ensure_tables_exist()` 在启动时自动创建缺失的表。

---

## 运行系统

### 方式一：一键启动（推荐）

```bash
python run.py
```

脚本会同时启动后端和前端，按 `Ctrl+C` 可同时关闭两个进程。

### 方式二：分终端启动

终端 1 — 启动后端：

```bash
python -m backend.main
```

终端 2 — 启动前端：

```bash
python frontend/app.py
```

启动后：
- API 服务：`http://127.0.0.1:8000`
- Swagger 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`

### 其他命令

```bash
python run.py test      # 运行测试套件
python run.py format    # 使用 black 格式化代码
python run.py lint      # 使用 flake8 检查代码
```

---

## 使用示例

### 普通对话模式
在聊天输入框中直接输入消息，Agent 会分析意图并调用合适的工具回答。

> "(在教务系统上)查阅我这学期有哪些课？"

### 日程模式
增删改查事务信息，识别事务冲突：

> "我明天8：00到10：00考软件工程，请记录事务"
> "这周我有事务时间冲突吗？"

### 校园问答模式
询问校园政策相关问题：

> "CS 专业的毕业要求是什么？"
> "一丹闭馆时间是什么时候？"

### 图书馆讨论间查询
> "6月1日一丹图书馆三楼有5人间吗？"

### Blackboard 课件同步
> "帮我下载这学期所有 BB 课件"

系统会自动爬取 Blackboard、下载 PDF 和课件文件，并自动向量化入库供后续 RAG 检索。

### 邮件服务
> "把我们的对话总结发到我邮箱"
> "把查询到的信息发邮件给我"

Agent 会自动撰写 Markdown 邮件并发送至用户的南科大邮箱，可选附带知识库中的原始文件。

### 文件自动化
> "在workplace创建文件清华录取通知书.txt并写入做梦去吧"
> "把我工作空间里的所有i.pdf文件重命名为 `lab{i}_report.pdf` 格式"

此操作会触发 HITL 授权弹窗，展示计划执行的操作详情，用户确认后才执行。

---

## 截图展示

### 引导页面
<!-- ![登录注册](screenshots/lead.png) -->

### 登录注册页面
<!-- ![登录注册](screenshots/login.png) -->

### 主界面 (Main Dashboard)
<!-- ![主界面](screenshots/dashboard.png) -->

### 日程结果卡片 (Schedule Result)
<!-- ![日程结果](screenshots/schedule.png) -->

### 校园问答结果卡片 (Campus Q&A)
<!-- ![校园问答](screenshots/encyclopedia.png) -->

### 图书馆讨论间查询 (Library Room)
<!-- ![图书馆讨论间](screenshots/library.png) -->

### HITL 授权弹窗 (HITL Dialog)
<!-- ![HITL 弹窗](screenshots/hitl.png) -->

### 设置对话框 (Settings)
<!-- ![设置](screenshots/settings.png) -->

### 推理追踪面板 (Thought Trace)
<!-- ![推理追踪](screenshots/trace.png) -->

### 邮件发送确认 (Email Confirmation)
<!-- ![邮件](screenshots/email.png) -->

---

## 项目结构

```
team-project-26spring-26s-13/
├── backend/                         # FastAPI 后端
│   ├── main.py                      # 应用入口，CORS 配置，路由注册
│   ├── config.py                    # 全局配置（读取 .env）
│   ├── database/
│   │   ├── postgres.py              # SQLAlchemy 异步引擎 + ORM（6 张表）
│   │   └── chromadb.py              # ChromaDB 客户端（21 个 Collection）
│   ├── schemas/                     # Pydantic 请求/响应模型
│   │   ├── agent.py                 # AgentRequest / AgentResponse
│   │   ├── auth.py                  # 注册/登录
│   │   ├── dashboard.py             # Bootstrap 响应
│   │   ├── material.py              # 教材文件信息
│   │   └── user.py                  # 用户 Profile
│   ├── api/                         # HTTP 路由层
│   │   ├── deps.py                  # JWT 鉴权依赖
│   │   ├── agent.py                 # POST /api/agent/run + 流式响应
│   │   ├── auth.py / user.py        # 认证 & 用户端点
│   │   ├── materials.py             # 文件上传/同步/CRUD + BB 同步任务
│   │   ├── schedule.py              # 日程刷新
│   │   └── dashboard.py             # Bootstrap 初始化数据
│   ├── agent/                       # PydanticAI Agent 逻辑
│   │   ├── core.py                  # Agent 单例 + AgentDeps
│   │   ├── loop.py                  # Agent 主循环
│   │   ├── hitl.py                  # HITL 挂起状态管理
│   │   ├── router.py                # 工具 → 前端路由推断
│   │   ├── tool_policy.py           # 工具使用策略
│   │   ├── prompt.py                # System Prompt 模板
│   │   ├── validators/              # 响应质量校验器
│   │   └── tools/                   # Agent 工具
│   │       ├── base.py              # 基础工具类
│   │       ├── scheduler.py         # Blackboard / 教务日程工具
│   │       ├── rag.py               # RAG 检索 + 学科分类
│   │       ├── study_copilot.py     # 摘要 & 练习题生成
│   │       ├── os_automation.py     # 文件操作（含 HITL 审批）
│   │       ├── library_room.py      # 图书馆讨论间查询
│   │       ├── email.py             # 邮件发送工具
│   │       ├── personal_tasks.py    # 个人事务管理
│   │       └── time_utils.py        # 时间解析工具
│   ├── services/                    # 业务逻辑层
│   │   ├── auth_service.py          # 注册/登录/JWT
│   │   ├── user_service.py          # 用户 Profile CRUD
│   │   ├── material_service.py      # 上传 + 向量化 + BB 同步
│   │   ├── rag_service.py           # 学科剪枝 + 上下文格式化
│   │   ├── audit_service.py         # OS 操作审计日志
│   │   ├── dashboard_service.py     # Bootstrap 数据组装
│   │   ├── task_service.py          # 个人事务 CRUD
│   │   ├── library_room_service/    # 图书馆讨论间查询
│   │   │   ├── auth.py              # 图书馆 CAS 认证
│   │   │   ├── fetch.py             # 房间空闲查询
│   │   │   └── models.py            # 房间数据模型
│   │   └── schedule_service/        # 日程爬取（模块化拆包）
│   │       ├── cas_auth.py          # 统一 CAS 认证
│   │       ├── bb_auth.py           # Blackboard 专用认证
│   │       ├── bb_materials.py      # BB 课件发现与下载
│   │       ├── bb_deadlines.py      # BB DDL 爬取
│   │       ├── bb_common.py         # BB 共用工具
│   │       ├── fetch_tis.py         # 教务系统课表爬取
│   │       ├── academic_calendar_*.py # 教务日历爬取/解析/提取
│   │       ├── conflicts.py         # 冲突检测算法
│   │       ├── constants.py         # 课程时间常量
│   │       ├── effective_schedule.py # 有效日程计算
│   │       ├── models.py / enums.py # 数据模型 & 枚举
│   │       └── refresh.py           # 刷新编排
│   └── utils/
│       ├── crypto.py                # Fernet 加解密
│       ├── document_parser.py       # PDF/PPT/MD/DOCX 文本提取
│       ├── email_sender.py          # Gmail SMTP 邮件发送
│       ├── semantic_chunker.py      # 语义分块（用于 RAG）
│       └── OCR/
│           └── paddle_ocr.py        # PaddleOCR 图片文字提取
│
├── frontend/                        # PyQt6 桌面客户端
│   ├── app.py                       # 单文件原型（含 Mock 模式）
│   ├── main.py                      # 模块化入口
│   ├── config.py                    # API_BASE_URL 配置
│   ├── i18n.py                      # 中英双语
│   ├── styles.py                    # 全局 QSS 样式
│   ├── api/
│   │   ├── client.py                # HTTP 客户端封装
│   │   └── api_client.py            # 增强版 API 客户端
│   ├── views/
│   │   ├── auth_page.py             # 登录/注册页
│   │   └── dashboard_page.py        # 主界面协调器
│   ├── components/
│   │   ├── chat_widget.py           # 聊天消息列表 + 输入框
│   │   ├── trace_widget.py          # 推理追踪面板
│   │   ├── schedule_widget.py       # 日程展示
│   │   ├── encyclopedia_widget.py   # 校园百科结果
│   │   ├── library_widget.py        # 图书馆讨论间结果
│   │   ├── materials_widget.py      # 教材列表（上传/删除）
│   │   └── hitl_dialog.py           # HITL 授权弹窗
│   └── workers/
│       └── agent_worker.py          # QThread 异步 API 调用
│
├── tests/                           # pytest 测试套件（19 个文件，182 个用例）
├── alembic/                         # 数据库迁移（3 个版本）
├── scripts/
│   └── generate_metrics.py          # LOC/圈复杂度/依赖度量生成
├── reports/                         # 生成的报告（覆盖率、度量）
├── run.py                           # 一键启动脚本
├── Dockerfile                       # Docker 镜像定义
├── Jenkinsfile                      # Jenkins CI/CD 流水线
├── .github/workflows/ci.yml         # GitHub Actions CI/CD 流水线
├── proposal-26s-13.md               # 需求分析文档
├── design-26s-13.md                 # 架构设计 & UI 设计
└── Guideline/                       # 项目文档与规范
```

---

## API 接口概览

除 `/api/auth/register` 和 `/api/auth/login` 外，所有接口均需 `Authorization: Bearer <token>` 请求头。

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/auth/register` | 注册新用户 |
| POST | `/api/auth/login` | 登录，返回 JWT token |
| POST | `/api/auth/logout` | 登出 |
| GET | `/api/user/profile` | 获取用户 Profile |
| PUT | `/api/user/profile` | 更新显示名、专业、偏好设置 |
| PUT | `/api/user/credentials` | 更新 CAS 账号密码 / LLM API Key |
| GET | `/api/dashboard/bootstrap` | 一次性拉取主界面初始化数据 |
| **POST** | **`/api/agent/run`** | **Agent 核心入口（对话 + HITL 审批）** |
| POST | `/api/agent/run/stream` | Agent 流式响应入口 |
| GET | `/api/agent/sessions` | 获取会话列表 |
| GET | `/api/agent/sessions/{id}` | 获取会话详情 |
| DELETE | `/api/agent/sessions/{id}` | 删除会话 |
| GET | `/api/materials` | 获取教材列表 |
| POST | `/api/materials/upload` | 上传教材（自动向量化） |
| POST | `/api/materials/sync-blackboard` | 同步 Blackboard 课件 |
| POST | `/api/materials/sync-blackboard/jobs` | 启动异步 BB 同步任务 |
| GET | `/api/materials/sync-blackboard/jobs/{id}` | 查询 BB 同步任务状态 |
| POST | `/api/materials/sync-blackboard/jobs/{id}/cancel` | 取消 BB 同步任务 |
| DELETE | `/api/materials/{file_id}` | 删除教材 |
| POST | `/api/schedule/refresh` | 触发日程刷新 |

> 完整接口文档：后端运行后访问 `http://127.0.0.1:8000/docs` 查看 Swagger UI。

---

## 测试

测试套件使用 **pytest + pytest-asyncio**，以 SQLite 替代 PostgreSQL，无需启动任何外部服务。

```bash
# 运行全部测试
python -m pytest tests/

# 带覆盖率报告
python -m pytest tests/ --cov=backend --cov-report=term-missing

# 运行指定测试文件
python -m pytest tests/test_auth.py

# 详细输出
python -m pytest tests/ -v
```

全套 **182 个测试用例**，分布在 **19 个测试文件**中，覆盖后端 API 路由、业务逻辑与 Agent 工具层。所有 LLM 和网络调用均通过 `unittest.mock` 拦截。

**测试文件分布：**

| 测试文件 | 覆盖范围 |
|----------|----------|
| `test_main.py` | 健康检查、OpenAPI 文档 |
| `test_auth.py` | 注册、登录、登出 |
| `test_user.py` | 用户 Profile CRUD |
| `test_user_credentials.py` | CAS/API Key 凭据更新 |
| `test_materials.py` | 教材上传/列表/删除 |
| `test_schedule.py` | 日程刷新 |
| `test_dashboard.py` | Dashboard 初始化 |
| `test_agent_sessions.py` | 会话 CRUD + Agent Run 契约 |
| `test_agent_response_enrichment.py` | Agent 响应增强 |
| `test_crypto.py` | Fernet 加解密 |
| `test_conflicts.py` | 日程冲突检测 |
| `test_document_parser.py` | PDF/PPT/MD 解析 |
| `test_os_automation.py` | OS 自动化工具 + HITL |
| `test_hitl_execute.py` | HITL 执行流程 |
| `test_study_copilot_utils.py` | 学习助手工具 |
| `test_personal_tasks.py` | 个人事务 CRUD |
| `test_email.py` | 邮件发送 |
| `test_library_room_service.py` | 图书馆讨论间查询 |
| `test_tool_policy.py` | 工具使用策略 |

---

## CI/CD 流水线

项目使用 **GitHub Actions + Jenkins 双流水线** 进行持续集成与持续部署，确保每次向 `main`/`master` 分支 push 时自动触发构建-测试-打包-部署流程。

### 流水线步骤

| 步骤 | 工具 | 说明 |
|------|------|------|
| 1. 代码检出 | Git | 克隆仓库源代码 |
| 2. 安装依赖 | pip | 安装 `requirements.txt` + `requirements-dev.txt` + `lizard` |
| 3. 格式检查 | Black | 验证代码格式（`black --check .`） |
| 4. 静态分析 | Flake8 | Lint 检查（`flake8 .`） |
| 5. 运行测试 | pytest + pytest-cov | 执行 182 个测试用例，生成 XML/HTML 覆盖率报告 |
| 6. 度量报告 | `scripts/generate_metrics.py`, lizard | 生成 LOC、圈复杂度、依赖数等度量 |
| 7. Docker 构建 | Docker | 基于 [`Dockerfile`](Dockerfile) 构建镜像（`python:3.10-slim`） |
| 8. Docker 推送 | Docker Hub | 推送 `kabukimonosakura/student-productivity-agent:latest` + commit SHA 标签 |

### GitHub Actions

- **配置文件：** [`.github/workflows/ci.yml`](.github/workflows/ci.yml)
- **触发条件：** 向 `main`/`master` 分支 push / PR + 手动 `workflow_dispatch`
- **运行环境：** `ubuntu-latest`，含 PostgreSQL 15 服务容器
- **特性：** 覆盖率上报 Codecov，测试/度量报告作为 Artifacts 上传，Docker 镜像构建并推送

<!-- ![GitHub Actions](screenshots/github-actions.png) -->
*待添加截图。*

### Jenkins and Docker

- **配置文件：** [`Jenkinsfile`](Jenkinsfile) 与 [`Dockerfile`](Dockerfile)
- **运行环境：** 本地 Windows + conda `software-engineering` 环境
- **特性：** 声明式流水线，Docker Hub 凭据管理，构建产物归档

<!-- ![Jenkins](screenshots/jenkins.png) -->
*待添加截图。*

### 本地模拟 CI

```bash
black --check .
flake8 .
python -m pytest tests/ --cov=backend --cov-report=term-missing
python scripts/generate_metrics.py
docker build -t student-productivity-agent .
```

---

## 已知问题与限制

- **Alembic 异步兼容性**：`alembic upgrade head` 因 asyncpg 驱动兼容问题可能无法正常建表，建议手动执行 SQL 建表。
- **LLM 输出不确定性**：Agent 回复可能因 LLM 的非确定性而在不同运行间产生差异。
- **Blackboard 爬虫脆弱性**：爬虫依赖南科大 Blackboard 的 HTML 结构，学期间可能发生变化。
- **OS 自动化仅支持 Windows**：文件自动化功能针对 Windows 设计，未在 macOS/Linux 上测试。

---

## 参考文档

| 文档 | 说明 |
|------|------|
| [Guideline/README.md](Guideline/README.md) | 详细开发指南（环境搭建、接口契约、测试说明） |
| [proposal-26s-13.md](proposal-26s-13.md) | 项目需求分析 |
| [design-26s-13.md](design-26s-13.md) | 架构设计与 UI 设计 |
| [final-report-26s-13.md](final-report-26s-13.md) | 团队报告（度量 + CI/CD 描述） |
| [Guideline/docs/Frontend Relevant/backend-interface-contract-zh.md](Guideline/docs/Frontend%20Relevant/backend-interface-contract-zh.md) | 后端接口契约 |
| [Guideline/docs/Frontend Relevant/frontend-api-connection-zh.md](Guideline/docs/Frontend%20Relevant/frontend-api-connection-zh.md) | 前端 API 对接说明 |
| `http://127.0.0.1:8000/docs` | FastAPI Swagger 交互式文档（后端运行后可访问） |

---

## 团队

> **Team 26s-13 · SUSTech OS 2026 Spring**

罗文韬 潘法昇 赵勋 汤深尧 晏梓豪