# Student Productivity Agent

> **Team 26s-13 · 南方科技大学 CS304 软件工程 · 2026 春季**

面向南科大学生的 AI 智能体桌面助手，集成日程管理、校园百科、学习辅助、图书馆讨论间查询、Blackboard 课件批量爬取与文件自动化操作，以统一的对话式界面呈现。

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

## 核心功能

### 1. 多源日程管理 (Multi-Source Scheduler)
自动爬取南科大教务日历与 Blackboard DDL，检测与个人待办的时间冲突，动态生成优化的学习日程。

### 2. Blackboard 课件批量爬取与 RAG 入库 (Batch BB Material Crawler & RAG Ingestion)
通过 CAS 认证登录南科大 Blackboard，BFS 遍历所有已选课程内容页面发现可下载文件，并行下载并自动过滤当前学期课件。每个文件经过类型校验（PDF/PPT/PPTX/Markdown）→ 文本解析 → LLM 学科分类（20 类）→ 文本分块 → ChromaDB 向量化，立即可供 RAG 检索使用。

### 3. 校园百科 (Campus Encyclopedia)
基于 RAG 的智能问答系统，可回答校园相关政策问题（如学位要求、宿舍规定等）。系统将官方文档（如南科大学生手册）分块存入 ChromaDB 的 21 个学科集合中，查询时通过 LLM 判断学科后精准检索对应集合。

### 4. 图书馆讨论间查询 (Library Discussion Room Query)
根据地点、时间段和人数要求查询南科大图书馆讨论间的实时空闲情况，返回可用房间列表，方便学生规划小组学习。

### 5. 学习助手 (Study Copilot)
处理用户上传或本地的学术资料（PPT、PDF、Markdown 笔记等），自动提取核心概念、生成学习摘要并创建自定义练习题。

### 6. 操作系统文件自动化 (System-Level OS Automation)
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
│  │          │  │ sessions, msgs...) │  │ 向量集合      │     │
│  └──────────┘  └───────────────────┘  └───────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

**核心设计决策：**

- **安全封装**：前端不直接访问数据库，所有敏感凭据（CAS 密码、API Key）使用 Fernet 加密存储，仅在后端 Service 层解密使用。
- **非阻塞体验**：耗时推理和网络爬取在后台执行；PyQt6 前端通过 `QThread` Worker 调用后端 API，确保 UI 始终响应。
- **HITL 安全机制**：所有高危文件操作被拦截并呈现给用户审批，通过专门的授权弹窗确认后才执行。

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
| 网络爬虫 | httpx + BeautifulSoup4 | >= 0.27.0 |
| 文档解析 | PyMuPDF + python-pptx | >= 1.24.0 |
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

在项目根目录创建 `.env` 文件（**不要提交到 git**）：

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

> **注意：** Alembic 迁移因异步驱动兼容性问题可能无法正常工作，建议手动建表。

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

> "我这学期有哪些课？"

### 日程模式
询问截止日期或时间冲突：

> "这周有什么截止日期？"
> "下周一我有时间冲突吗？"

### 校园问答模式
询问校园政策相关问题：

> "CS 专业的学位要求是什么？"
> "宿舍管理规定有哪些？"

### 图书馆讨论间查询
> "5月24日一丹图书馆有5人间吗？"

### Blackboard 课件同步
> "帮我下载这学期所有 BB 课件"

系统会自动爬取 Blackboard、下载 PDF 和课件文件，并自动向量化入库供后续 RAG 检索。

### 文件自动化
> "把我工作空间里的所有文件重命名为 `lab{i}_report.pdf` 格式"

此操作会触发 HITL 授权弹窗，展示计划执行的操作详情，用户确认后才执行。

---

## 截图展示

<!-- TODO: 添加截图 -->

### 主界面 (Main Dashboard)

<!-- ![主界面](screenshots/dashboard.png) -->
*待添加截图。*

### 日程结果卡片 (Schedule Result)

<!-- ![日程结果](screenshots/schedule.png) -->
*待添加截图。*

### 校园问答结果卡片 (Campus Q&A)

<!-- ![校园问答](screenshots/encyclopedia.png) -->
*待添加截图。*

### HITL 授权弹窗 (HITL Dialog)

<!-- ![HITL 弹窗](screenshots/hitl.png) -->
*待添加截图。*

### 设置对话框 (Settings)

<!-- ![设置](screenshots/settings.png) -->
*待添加截图。*

### 推理追踪面板 (Thought Trace)

<!-- ![推理追踪](screenshots/trace.png) -->
*待添加截图。*

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
│   ├── api/                         # HTTP 路由层
│   │   ├── deps.py                  # JWT 鉴权依赖
│   │   ├── auth.py / user.py        # 认证 & 用户端点
│   │   ├── agent.py                 # POST /api/agent/run（核心入口）
│   │   ├── materials.py             # 文件上传/同步/CRUD
│   │   ├── schedule.py              # 日程刷新
│   │   └── dashboard.py             # Bootstrap 初始化数据
│   ├── agent/                       # PydanticAI Agent 逻辑
│   │   ├── core.py                  # Agent 单例 + AgentDeps 定义
│   │   ├── loop.py                  # Agent 主循环
│   │   ├── hitl.py                  # HITL 挂起状态管理
│   │   ├── prompt.py                # System Prompt 模板
│   │   └── tools/                   # Agent 工具
│   │       ├── scheduler.py         # Blackboard / 教务日程工具
│   │       ├── rag.py               # RAG 检索 + 学科分类
│   │       ├── study_copilot.py     # 摘要 & 练习题生成
│   │       ├── os_automation.py     # 文件操作（含 HITL 审批）
│   │       └── library_room.py      # 图书馆讨论间查询
│   ├── services/                    # 业务逻辑层
│   │   ├── material_service.py      # 上传 + 向量化 + BB 同步
│   │   ├── rag_service.py           # 学科剪枝 + 上下文格式化
│   │   ├── schedule_service/        # 日程爬取（模块化拆包）
│   │   │   ├── fetch_bb.py          # Blackboard CAS 认证 + 爬取
│   │   │   ├── bb_materials.py      # BB 课件发现与下载
│   │   │   ├── fetch_tis.py         # 教务系统课表爬取
│   │   │   └── conflicts.py         # 冲突检测算法
│   │   └── ...
│   └── utils/
│       ├── crypto.py                # Fernet 加解密
│       └── document_parser.py       # PDF/PPT/MD 文本提取
│
├── frontend/                        # PyQt6 桌面客户端
│   ├── app.py                       # 单文件原型（含 Mock 模式）
│   ├── main.py                      # 模块化入口
│   ├── api/client.py                # HTTP 客户端封装
│   ├── views/                       # 页面级视图
│   ├── components/                  # 可复用 UI 组件
│   └── workers/agent_worker.py      # QThread 异步 API 调用
│
├── tests/                           # pytest 测试套件（98 个用例）
├── alembic/                         # 数据库迁移文件
├── run.py                           # 一键启动脚本
├── .github/workflows/ci.yml         # CI/CD 流水线
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

全套 **98 个测试用例**覆盖后端 API 路由、业务逻辑与 Agent 工具层。所有 LLM 和网络调用均通过 `unittest.mock` 拦截。

---

## CI/CD 流水线

项目使用 **GitHub Actions** 进行持续集成，配置文件位于 [`.github/workflows/ci.yml`](.github/workflows/ci.yml)，每次向 `main` 分支 push 或发起 PR 时自动触发。

### 流水线步骤

| 步骤 | 工具 | 说明 |
|------|------|------|
| 1. 环境准备 | Python 3.10 + PostgreSQL 15 服务 | 搭建运行环境 |
| 2. 安装依赖 | pip | 安装 `requirements.txt` + `requirements-dev.txt` |
| 3. 格式检查 | Black | 验证代码格式（`black --check .`） |
| 4. 静态分析 | Flake8 | Lint 检查（`flake8 .`） |
| 5. 运行测试 | pytest | 执行全部测试并生成覆盖率报告 |
| 6. 覆盖率上报 | Codecov | 上传 XML 覆盖率报告 |

### 本地模拟 CI

```bash
black --check .
flake8 .
python -m pytest tests/ --cov=backend --cov-report=term-missing
```

---

## 已知问题与限制

- **Alembic 异步兼容性**：`alembic upgrade head` 因 asyncpg 驱动兼容问题可能无法正常建表，建议手动执行 SQL 建表。
- **LLM 输出不确定性**：Agent 回复可能因 LLM 的非确定性而在不同运行间产生差异。
- **Blackboard 爬虫脆弱性**：爬虫依赖南科大 Blackboard 的 HTML 结构，学期间可能发生变化。
- **OS 自动化仅支持 Windows**：文件自动化功能针对 Windows 设计，未在 macOS/Linux 上测试。
- **DeepSeek API 限流**：高频使用可能触发 API 限流，用户可在设置对话框中配置自己的 API Key。
- **无 Docker 部署**：系统目前直接在宿主机运行，未提供容器化部署方案。

---

## 参考文档

| 文档 | 说明 |
|------|------|
| [Guideline/README.md](Guideline/README.md) | 详细开发指南（环境搭建、接口契约、测试说明） |
| [proposal-26s-13.md](proposal-26s-13.md) | 项目需求分析 |
| [design-26s-13.md](design-26s-13.md) | 架构设计与 UI 设计 |
| [Guideline/docs/Frontend Relevant/backend-interface-contract-zh.md](Guideline/docs/Frontend%20Relevant/backend-interface-contract-zh.md) | 后端接口契约 |
| [Guideline/docs/Frontend Relevant/frontend-api-connection-zh.md](Guideline/docs/Frontend%20Relevant/frontend-api-connection-zh.md) | 前端 API 对接说明 |
| `http://127.0.0.1:8000/docs` | FastAPI Swagger 交互式文档（后端运行后可访问） |

---

## 团队

Team 26s-13 — 南方科技大学 CS304 软件工程，2026 春季。
