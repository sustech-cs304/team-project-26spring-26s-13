# Student Productivity Agent

An AI-powered desktop assistant for SUSTech students, integrating schedule management, campus Q&A, study aids, library room booking, batch Blackboard material crawling, email service, and file system automation into a unified chat-first interface.

![Python](https://img.shields.io/badge/Python-3.10-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-green)
![PyQt6](https://img.shields.io/badge/PyQt6-6.7+-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## Table of Contents

- [Key Features](#key-features)
- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Database Setup](#database-setup)
- [Running the System](#running-the-system)
- [Usage Examples](#usage-examples)
- [Screenshots](#screenshots)
- [Project Structure](#project-structure)
- [API Overview](#api-overview)
- [Testing](#testing)
- [CI/CD Pipeline](#cicd-pipeline)
- [Known Issues & Limitations](#known-issues--limitations)
- [References](#references)
- [Team](#team)

---

## Key Features

### 1. Multi-Source Scheduler
Automatically scrapes scheduling data from the SUSTech Academic Calendar and Blackboard deadlines. Detects time conflicts with personal tasks, supports viewing, completing, and deleting tasks via natural language, and suggests an optimized study calendar.

### 2. Batch Blackboard Material Crawler & RAG Ingestion
Authenticates to SUSTech Blackboard via CAS, BFS-crawls all enrolled courses to discover downloadable files, downloads them in parallel with current-semester filtering, then automatically validates, parses, classifies by subject (20+ categories via LLM), chunks, and embeds all materials into a local ChromaDB vector database for instant RAG-powered retrieval.

### 3. Campus Encyclopedia (RAG-based Q&A)
An intelligent QA system answering campus-related queries (degree requirements, dormitory policies, etc.) using Retrieval-Augmented Generation over official SUSTech documents pre-chunked and stored in ChromaDB with subject-based sharding across 21 collections.

### 4. Library Discussion Room Query
Queries available discussion rooms in the SUSTech Library by location, time slot, and capacity, returning real-time availability for planning group study sessions.

### 5. Study Copilot
Processes uploaded or local academic materials (PDFs, PPTs, Markdown notes), extracts key concepts, generates concise study summaries, and creates customized practice quizzes.

### 6. Email Service
Sends emails with Markdown attachments and conversation summaries to users' SUSTech email addresses. Supports attaching original files from the knowledge base with zip compression. Triggered naturally when the user asks to "send an email" or "mail me the summary."

### 7. System-Level OS Automation
Executes file system operations via natural language commands (reading, creating, deleting, batch renaming) within an isolated user workspace. All write operations require Human-in-the-Loop (HITL) approval through a dedicated authorization dialog, with full audit logging.

---

## Architecture Overview

The system follows a **Monolithic Layered Architecture** within a **Client-Server RESTful** framework:

```
┌──────────────────────────────────────────────────────────────┐
│                       PyQt6 Frontend                         │
│  ┌─────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │  Left Panel │  │  Center Panel    │  │  Right Panel   │  │
│  │  Chat History│  │  Chat / Schedule │  │ Thought Trace  │  │
│  │  Materials  │  │  Encyclopedia    │  │    Panel       │  │
│  │  Tasks      │  │  Library Room    │  │                │  │
│  └─────────────┘  └──────────────────┘  └────────────────┘  │
│                          │  HTTP/REST                         │
└──────────────────────────┼───────────────────────────────────┘
                           │
┌──────────────────────────┼───────────────────────────────────┐
│                   FastAPI Backend                             │
│  ┌──────────────────────────────────────────────────────┐    │
│  │                 PydanticAI Agent Loop                 │    │
│  │  Perception → Reasoning → Tool Use → Observation     │    │
│  └──────────────────────────────────────────────────────┘    │
│  ┌──────────┐  ┌───────────────────┐  ┌───────────────┐     │
│  │ DeepSeek │  │    PostgreSQL      │  │   ChromaDB    │     │
│  │  LLM API │  │ 6 tables (users,  │  │ 21 subject    │     │
│  │          │  │ sessions, tasks...)│  │ collections   │     │
│  └──────────┘  └───────────────────┘  └───────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

**Key design decisions:**
- **Security via encapsulation**: The frontend never directly accesses databases; all sensitive credentials (CAS passwords, API keys) are encrypted at rest with Fernet and managed within the backend.
- **Non-blocking UX**: Heavy reasoning and web scraping run on the backend; the PyQt6 frontend uses `QThread` workers to keep the UI responsive.
- **HITL safety mechanism**: All destructive OS operations are intercepted and presented to the user through an authorization dialog before execution.
- **Streaming support**: Agent responses support real-time streaming, allowing the frontend to display partial results and thought traces as they are generated.

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend Framework | FastAPI + Uvicorn | >= 0.111.0 |
| Agent Orchestration | PydanticAI | >= 0.0.13 |
| LLM | DeepSeek (OpenAI-compatible) | deepseek-chat |
| Relational Database | PostgreSQL + SQLAlchemy (async) | >= 2.0.0 |
| Vector Database | ChromaDB (embedded, no separate service) | >= 0.5.0 |
| Authentication | JWT (python-jose) + bcrypt | >= 3.3.0 |
| Encryption | Fernet (cryptography) | >= 42.0.0 |
| Web Scraping | httpx + BeautifulSoup4 + Selenium | >= 0.27.0 |
| Document Parsing | PyMuPDF + python-pptx + python-docx | >= 1.24.0 |
| OCR | PaddleOCR + PaddlePaddle | - |
| Email | SMTP (Gmail) | - |
| Frontend GUI | PyQt6 | >= 6.7.0 |
| Python | CPython | 3.10 |

---

## Getting Started

### Prerequisites

- **Python 3.10**
- **PostgreSQL 15+** (running locally)
- **conda** (recommended) or pip

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/sustech-cs304/team-project-26spring-26s-13.git
   cd team-project-26spring-26s-13
   ```

2. **Create and activate the conda environment:**
   ```bash
   conda env create -f Guideline/environment.yml
   conda activate software-engineering
   ```
   Or with pip:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install dev dependencies** (for testing):
   ```bash
   pip install -r requirements-dev.txt
   ```

### Configuration

Create a `.env` file in the project root:

```env
# PostgreSQL connection
POSTGRES_DSN=postgresql+asyncpg://postgres:yourpassword@localhost:5432/software-engineering

# Fernet encryption key (for CAS passwords / API keys)
FERNET_KEY=your_fernet_key_here

# JWT signing secret
SECRET_KEY=your_jwt_secret_here

# DeepSeek API (optional; users can also configure via GUI)
# Change to your own provider (e.g. https://open.bigmodel.cn/api/paas/v4/ for Zhipu GLM)
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_API_KEY=your_deepseek_api_key

# Email service (Gmail SMTP; requires an App Password)
GMAIL_APP_PASSWORD=your_gmail_app_password
```

Generate a Fernet key:
```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

### Database Setup

1. Create the database in PostgreSQL:
   ```sql
   CREATE DATABASE "software-engineering";
   ```

2. Run the schema SQL (see [Guideline/README.md](Guideline/README.md#44-初始化数据库) for the full DDL script).

> **Note:** Alembic migrations are available but may have async driver compatibility issues. Manual table creation is recommended. Alternatively, the backend can auto-create missing tables on startup via `ensure_tables_exist()`.

---

## Running the System

### Option 1: One-Click Startup (Recommended)

```bash
python run.py
```

This starts both backend and frontend simultaneously. Press `Ctrl+C` to stop both.

### Option 2: Start Separately

Terminal 1 — Backend:
```bash
python -m backend.main
```

Terminal 2 — Frontend:
```bash
python frontend/app.py
```

After startup:
- API server: `http://127.0.0.1:8000`
- Swagger docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

### Other Commands

```bash
python run.py test      # Run the test suite
python run.py format    # Format code with black
python run.py lint      # Lint with flake8
```

---

## Usage Examples

### Chat Mode
Simply type a message in the chat input. The agent will reason about your intent and respond accordingly.

> "(From the academic system) Check what courses I have this semester"

### Schedule Mode
Add, query, delete tasks, and detect scheduling conflicts:

> "I have a Software Engineering exam tomorrow 8:00-10:00, please record this task"
> "Do I have any time conflicts this week?"

### Campus Q&A Mode
Ask about campus policies:

> "What are the degree requirements for CS?"
> "When does Yidan Library close?"

### Library Room Booking
> "Are there any 5-person rooms available on the 3rd floor of Yidan Library on June 1st?"

### Blackboard Material Sync
> "Download all my BB course materials for this semester"

The system will crawl Blackboard, download PDFs and slides, and automatically vectorize them for RAG retrieval.

### Email Service
> "Email me the summary of our conversation"
> "Send the queried information to my email"

The agent will compose a Markdown email and send it to the user's SUSTech email address, with optional attachments from the knowledge base.

### File Automation
> "Create a file tsinghua_admission_letter.txt in workspace and write 'dream on'"
> "Rename all i.pdf files in my workspace to follow the format `lab{i}_report.pdf`"

This triggers an HITL authorization dialog showing the planned operations before execution.

---

## Screenshots

### Landing Page
<!-- ![Landing Page](screenshots/lead.png) -->

### Login & Registration Page
<!-- ![Login Page](screenshots/login.png) -->

### Main Dashboard
<!-- ![Main Dashboard](screenshots/dashboard.png) -->

### Schedule Result Card
<!-- ![Schedule Result](screenshots/schedule.png) -->

### Campus Q&A Result Card
<!-- ![Campus Q&A](screenshots/encyclopedia.png) -->

### Library Room Query
<!-- ![Library Room](screenshots/library.png) -->

### HITL Authorization Dialog
<!-- ![HITL Dialog](screenshots/hitl.png) -->

### Settings Dialog
<!-- ![Settings](screenshots/settings.png) -->

### Thought Trace Panel
<!-- ![Thought Trace](screenshots/trace.png) -->

---

## Project Structure

```
team-project-26spring-26s-13/
├── backend/                         # FastAPI backend
│   ├── main.py                      # App entry, CORS, route registration
│   ├── config.py                    # Global settings (from .env)
│   ├── database/
│   │   ├── postgres.py              # SQLAlchemy async engine + ORM (6 tables)
│   │   └── chromadb.py              # ChromaDB client (21 collections)
│   ├── schemas/                     # Pydantic request/response models
│   │   ├── agent.py                 # AgentRequest / AgentResponse
│   │   ├── auth.py                  # Register / Login schemas
│   │   ├── dashboard.py             # Bootstrap response
│   │   ├── material.py              # Material file info
│   │   └── user.py                  # User profile schemas
│   ├── api/                         # HTTP route handlers
│   │   ├── deps.py                  # JWT auth dependency
│   │   ├── agent.py                 # POST /api/agent/run + streaming
│   │   ├── auth.py / user.py        # Auth & user endpoints
│   │   ├── materials.py             # File upload/sync/CRUD + BB sync jobs
│   │   ├── schedule.py              # Schedule refresh
│   │   └── dashboard.py             # Bootstrap data
│   ├── agent/                       # PydanticAI agent logic
│   │   ├── core.py                  # Agent singleton + AgentDeps
│   │   ├── loop.py                  # Agent main loop
│   │   ├── hitl.py                  # HITL state management
│   │   ├── router.py                # Tool → frontend route inference
│   │   ├── tool_policy.py           # Tool usage policy
│   │   ├── prompt.py                # System prompt template
│   │   ├── validators/              # Response quality validators
│   │   └── tools/                   # Agent tools
│   │       ├── base.py              # Base tool utilities
│   │       ├── scheduler.py         # Blackboard/academic schedule
│   │       ├── rag.py               # RAG retrieval + subject classification
│   │       ├── study_copilot.py     # Summaries & quizzes
│   │       ├── os_automation.py     # File ops with HITL
│   │       ├── library_room.py      # Library discussion room query
│   │       ├── email.py             # Email sending tool
│   │       ├── personal_tasks.py    # Personal task management
│   │       └── time_utils.py        # Time parsing utilities
│   ├── services/                    # Business logic layer
│   │   ├── auth_service.py          # Register/Login/JWT
│   │   ├── user_service.py          # User profile CRUD
│   │   ├── material_service.py      # Upload + vectorize + BB sync
│   │   ├── rag_service.py           # Subject pruning + context formatting
│   │   ├── audit_service.py         # OS operation audit logging
│   │   ├── dashboard_service.py     # Bootstrap data assembly
│   │   ├── task_service.py          # Personal task CRUD
│   │   ├── library_room_service/    # Library room availability
│   │   │   ├── auth.py              # Library CAS auth
│   │   │   ├── fetch.py             # Room availability fetching
│   │   │   └── models.py            # Room data models
│   │   └── schedule_service/        # Schedule crawling (modular)
│   │       ├── cas_auth.py          # Unified CAS authentication
│   │       ├── bb_auth.py           # Blackboard-specific auth
│   │       ├── bb_materials.py      # BB material discovery & download
│   │       ├── bb_deadlines.py      # BB deadline scraping
│   │       ├── bb_common.py         # Shared BB utilities
│   │       ├── fetch_tis.py         # Academic system schedule scraping
│   │       ├── academic_calendar_*.py # Academic calendar fetch/parse/extract
│   │       ├── conflicts.py         # Conflict detection algorithm
│   │       ├── constants.py         # Course time slot constants
│   │       ├── effective_schedule.py # Effective schedule computation
│   │       ├── models.py / enums.py # Data models & enums
│   │       └── refresh.py           # Refresh orchestration
│   └── utils/
│       ├── crypto.py                # Fernet encrypt/decrypt
│       ├── document_parser.py       # PDF/PPT/MD/DOCX text extraction
│       ├── email_sender.py          # Gmail SMTP email sender
│       ├── semantic_chunker.py      # Semantic text chunking for RAG
│       └── OCR/
│           └── paddle_ocr.py        # PaddleOCR image text extraction
│
├── frontend/                        # PyQt6 desktop client
│   ├── app.py                       # Standalone prototype (with mock mode)
│   ├── main.py                      # Modular entry
│   ├── config.py                    # API_BASE_URL config
│   ├── i18n.py                      # EN/CN bilingual text
│   ├── styles.py                    # Global QSS styles
│   ├── api/
│   │   ├── client.py                # HTTP client wrapper
│   │   └── api_client.py            # Enhanced API client
│   ├── views/
│   │   ├── auth_page.py             # Login / Registration page
│   │   └── dashboard_page.py        # Main dashboard coordinator
│   ├── components/
│   │   ├── chat_widget.py           # Chat message list + input
│   │   ├── trace_widget.py          # Thought Trace panel
│   │   ├── schedule_widget.py       # Schedule display
│   │   ├── encyclopedia_widget.py   # Campus Q&A results
│   │   ├── library_widget.py        # Library room results
│   │   ├── materials_widget.py      # Material upload/delete list
│   │   └── hitl_dialog.py           # HITL authorization dialog
│   └── workers/
│       └── agent_worker.py          # QThread for async API calls
│
├── tests/                           # pytest test suite (19 files, 182 cases)
├── alembic/                         # Database migrations (3 versions)
├── scripts/
│   └── generate_metrics.py          # LOC/complexity/dependency metrics
├── reports/                         # Generated reports (coverage, metrics)
├── run.py                           # One-click startup script
├── Dockerfile                       # Docker image definition
├── Jenkinsfile                      # Jenkins CI/CD pipeline
├── .github/workflows/ci.yml         # GitHub Actions CI/CD pipeline
├── proposal-26s-13.md               # Requirements analysis
├── design-26s-13.md                 # Architecture & UI design
└── Guideline/                       # Project docs & references
```

---

## API Overview

All endpoints require `Authorization: Bearer <token>` except `/api/auth/register` and `/api/auth/login`.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Register a new user |
| POST | `/api/auth/login` | Login, returns JWT token |
| POST | `/api/auth/logout` | Logout |
| GET | `/api/user/profile` | Get user profile |
| PUT | `/api/user/profile` | Update display name, major, preferences |
| PUT | `/api/user/credentials` | Update CAS account/password or LLM API key |
| GET | `/api/dashboard/bootstrap` | Fetch initial dashboard data |
| **POST** | **`/api/agent/run`** | **Core agent entry (chat + HITL approval)** |
| POST | `/api/agent/run/stream` | Agent streaming response |
| GET | `/api/agent/sessions` | List chat sessions |
| GET | `/api/agent/sessions/{id}` | Get session detail |
| DELETE | `/api/agent/sessions/{id}` | Delete a session |
| GET | `/api/materials` | List uploaded materials |
| POST | `/api/materials/upload` | Upload material (auto-vectorize) |
| POST | `/api/materials/sync-blackboard` | Sync Blackboard materials |
| POST | `/api/materials/sync-blackboard/jobs` | Start async BB sync job |
| GET | `/api/materials/sync-blackboard/jobs/{id}` | Poll BB sync job status |
| POST | `/api/materials/sync-blackboard/jobs/{id}/cancel` | Cancel BB sync job |
| DELETE | `/api/materials/{file_id}` | Delete a material |
| POST | `/api/schedule/refresh` | Trigger schedule refresh |

> Full API documentation available at `http://127.0.0.1:8000/docs` when the backend is running.

---

## Testing

The test suite uses **pytest + pytest-asyncio** with SQLite in place of PostgreSQL. No external services are needed.

```bash
# Run all tests
python -m pytest tests/

# With coverage report
python -m pytest tests/ --cov=backend --cov-report=term-missing

# Run a specific test file
python -m pytest tests/test_auth.py

# Verbose output
python -m pytest tests/ -v
```

The suite includes **182 test cases** across **19 test files** covering API routes, business logic, and agent tools. All LLM and network calls are mocked.

**Test file breakdown:**

| Test File | Coverage |
|-----------|----------|
| `test_main.py` | Health check, OpenAPI docs |
| `test_auth.py` | Registration, login, logout |
| `test_user.py` | User profile CRUD |
| `test_user_credentials.py` | CAS/API key credential updates |
| `test_materials.py` | Material upload/list/delete |
| `test_schedule.py` | Schedule refresh |
| `test_dashboard.py` | Dashboard bootstrap |
| `test_agent_sessions.py` | Session CRUD + agent run contract |
| `test_agent_response_enrichment.py` | Agent response enrichment |
| `test_crypto.py` | Fernet encrypt/decrypt |
| `test_conflicts.py` | Schedule conflict detection |
| `test_document_parser.py` | PDF/PPT/MD parsing |
| `test_os_automation.py` | OS automation tool + HITL |
| `test_hitl_execute.py` | HITL execution flow |
| `test_study_copilot_utils.py` | Study copilot utilities |
| `test_personal_tasks.py` | Personal task CRUD |
| `test_email.py` | Email sending |
| `test_library_room_service.py` | Library room query |
| `test_tool_policy.py` | Tool usage policy |

---

## CI/CD Pipeline

The project uses a **dual CI/CD pipeline** with both **GitHub Actions** and **Jenkins**, ensuring every push to `main`/`master` triggers an automated build-test-package-deploy workflow.

### Pipeline Steps

| Step | Tool | Description |
|------|------|-------------|
| 1. Checkout | Git | Clone repository source code |
| 2. Install Dependencies | pip | Install `requirements.txt` + `requirements-dev.txt` + `lizard` |
| 3. Format Check | Black | Verify code formatting (`black --check .`) |
| 4. Lint | Flake8 | Static analysis (`flake8 .`) |
| 5. Test | pytest + pytest-cov | Run 182 test cases with coverage (XML + HTML reports) |
| 6. Metrics | `scripts/generate_metrics.py`, lizard | Generate LOC, complexity, dependency metrics |
| 7. Docker Build | Docker | Build image from [`Dockerfile`](Dockerfile) (`python:3.10-slim`) |
| 8. Docker Push | Docker Hub | Push `kabukimonosakura/student-productivity-agent:latest` + commit SHA tag |

### GitHub Actions

- **Config:** [`.github/workflows/ci.yml`](.github/workflows/ci.yml)
- **Trigger:** Push / PR to `main`/`master` + manual `workflow_dispatch`
- **Runner:** `ubuntu-latest` with PostgreSQL 15 service container
- **Features:** Coverage upload to Codecov, test/metrics reports as artifacts, Docker image build & push

<!-- ![GitHub Actions](screenshots/github-actions.png) -->
*Screenshot to be added.*

### Jenkins

- **Config:** [`Jenkinsfile`](Jenkinsfile)
- **Environment:** Local Windows with conda `software-engineering`
- **Features:** Declarative pipeline, Docker Hub credential store, build artifacts archiving

<!-- ![Jenkins](screenshots/jenkins.png) -->
*Screenshot to be added.*

### Running CI Locally

```bash
black --check .
flake8 .
python -m pytest tests/ --cov=backend --cov-report=term-missing
python scripts/generate_metrics.py
docker build -t student-productivity-agent .
```

---

## Known Issues & Limitations

- **Alembic async compatibility**: Database migrations via `alembic upgrade head` may not work reliably with the asyncpg driver. Manual table creation is recommended.
- **LLM non-determinism**: Agent responses may vary between runs due to the non-deterministic nature of LLM outputs.
- **Blackboard scraping fragility**: The web crawler depends on SUSTech Blackboard's HTML structure, which may change between semesters.
- **Windows-only OS Automation**: The file automation feature is designed for Windows and has not been tested on macOS/Linux.
- **Email SMTP dependency**: The email service requires a configured SMTP server (defaults to Gmail with app-specific passwords).

---

## References

| Document | Description |
|----------|-------------|
| [Guideline/README.md](Guideline/README.md) | Detailed development guide with setup, API contracts, and test instructions |
| [proposal-26s-13.md](proposal-26s-13.md) | Requirements analysis document |
| [design-26s-13.md](design-26s-13.md) | Architecture design and UI design |
| [final-report-26s-13.md](final-report-26s-13.md) | Team report with metrics and CI/CD description |
| [Guideline/docs/Frontend Relevant/backend-interface-contract-zh.md](Guideline/docs/Frontend%20Relevant/backend-interface-contract-zh.md) | Backend API contract (Chinese) |
| [Guideline/docs/Frontend Relevant/frontend-api-connection-zh.md](Guideline/docs/Frontend%20Relevant/frontend-api-connection-zh.md) | Frontend API connection guide |
| `http://127.0.0.1:8000/docs` | Interactive Swagger API docs (when backend is running) |

---

## Team

> **Team 26s-13 · SUSTech Software Engineering Spring 2026**

<!-- Add team members here -->
