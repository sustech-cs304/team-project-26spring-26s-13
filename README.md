# Student Productivity Agent

An AI-powered desktop assistant for SUSTech students, integrating schedule management, campus Q&A, study aids, library room booking, batch Blackboard material crawling, and file system automation into a unified chat-first interface.

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
Automatically scrapes scheduling data from the SUSTech Academic Calendar and Blackboard deadlines. Detects time conflicts with personal tasks and suggests an optimized study calendar.

### 2. Batch Blackboard Material Crawler & RAG Ingestion
Authenticates to SUSTech Blackboard via CAS, BFS-crawls all enrolled courses to discover downloadable files, downloads them in parallel with current-semester filtering, then automatically validates, parses, classifies by subject (20 categories via LLM), chunks, and embeds all materials into a local ChromaDB vector database for instant RAG-powered retrieval.

### 3. Campus Encyclopedia (RAG-based Q&A)
An intelligent QA system answering campus-related queries (degree requirements, dormitory policies, etc.) using Retrieval-Augmented Generation over official SUSTech documents stored in ChromaDB with subject-based sharding across 21 collections.

### 4. Library Discussion Room Query
Queries available discussion rooms in the SUSTech Library by location, time slot, and capacity, returning real-time availability for planning group study sessions.

### 5. Study Copilot
Processes uploaded or local academic materials (PDFs, PPTs, Markdown notes), extracts key concepts, generates concise study summaries, and creates customized practice quizzes.

### 6. System-Level OS Automation
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
│  │          │  │ sessions, msgs...) │  │ collections   │     │
│  └──────────┘  └───────────────────┘  └───────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

**Key design decisions:**
- **Security via encapsulation**: The frontend never directly accesses databases; all sensitive credentials (CAS passwords, API keys) are encrypted at rest with Fernet and managed within the backend.
- **Non-blocking UX**: Heavy reasoning and web scraping run on the backend; the PyQt6 frontend uses `QThread` workers to keep the UI responsive.
- **HITL safety mechanism**: All destructive OS operations are intercepted and presented to the user through an authorization dialog before execution.

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
| Web Scraping | httpx + BeautifulSoup4 | >= 0.27.0 |
| Document Parsing | PyMuPDF + python-pptx | >= 1.24.0 |
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

Create a `.env` file in the project root (**do not commit this file**):

```env
# PostgreSQL connection
POSTGRES_DSN=postgresql+asyncpg://postgres:yourpassword@localhost:5432/software-engineering

# Fernet encryption key (for CAS passwords / API keys)
FERNET_KEY=your_fernet_key_here

# JWT signing secret
SECRET_KEY=your_jwt_secret_here

# DeepSeek API (optional; users can also configure via GUI)
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_API_KEY=your_deepseek_api_key
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

> **Note:** Alembic migrations are available but may have async driver compatibility issues. Manual table creation is recommended.

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

> "What courses do I have this semester?"

### Schedule Mode
Ask about deadlines or scheduling conflicts:

> "What deadlines are coming up this week?"
> "Do I have any time conflicts next Monday?"

### Campus Q&A Mode
Ask about campus policies:

> "What are the degree requirements for CS?"
> "What is the dormitory policy?"

### Library Room Booking
> "Are there any 5-person discussion rooms available on May 24th at Yidan Library?"

### Blackboard Material Sync
> "Download all my BB course materials for this semester"

The system will crawl Blackboard, download PDFs and slides, and automatically vectorize them for RAG retrieval.

### File Automation
> "Rename all files in my workspace to follow the format `lab{i}_report.pdf`"

This triggers an HITL authorization dialog showing the planned operations before execution.

---

## Screenshots

<!-- TODO: Add screenshots below -->

### Main Dashboard

<!-- ![Main Dashboard](screenshots/dashboard.png) -->
*Screenshots to be added.*

### Schedule Result Card

<!-- ![Schedule Result](screenshots/schedule.png) -->
*Screenshots to be added.*

### Campus Q&A Result Card

<!-- ![Campus Q&A](screenshots/encyclopedia.png) -->
*Screenshots to be added.*

### HITL Authorization Dialog

<!-- ![HITL Dialog](screenshots/hitl.png) -->
*Screenshots to be added.*

### Settings Dialog

<!-- ![Settings](screenshots/settings.png) -->
*Screenshots to be added.*

### Thought Trace Panel

<!-- ![Thought Trace](screenshots/trace.png) -->
*Screenshots to be added.*

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
│   ├── api/                         # HTTP route handlers
│   │   ├── deps.py                  # JWT auth dependency
│   │   ├── auth.py / user.py        # Auth & user endpoints
│   │   ├── agent.py                 # POST /api/agent/run (core entry)
│   │   ├── materials.py             # File upload/sync/CRUD
│   │   ├── schedule.py              # Schedule refresh
│   │   └── dashboard.py             # Bootstrap data
│   ├── agent/                       # PydanticAI agent logic
│   │   ├── core.py                  # Agent singleton + deps
│   │   ├── loop.py                  # Agent main loop
│   │   ├── hitl.py                  # HITL state management
│   │   ├── prompt.py                # System prompt template
│   │   └── tools/                   # Agent tools
│   │       ├── scheduler.py         # Blackboard/academic schedule
│   │       ├── rag.py               # RAG retrieval + subject classification
│   │       ├── study_copilot.py     # Summaries & quizzes
│   │       ├── os_automation.py     # File ops with HITL
│   │       └── library_room.py      # Library room query
│   ├── services/                    # Business logic layer
│   │   ├── material_service.py      # Upload + vectorize + BB sync
│   │   ├── rag_service.py           # Subject pruning + context
│   │   ├── schedule_service/        # Schedule crawling (modular)
│   │   │   ├── fetch_bb.py          # Blackboard CAS auth + crawl
│   │   │   ├── bb_materials.py      # BB material discovery
│   │   │   ├── fetch_tis.py         # Academic system scraping
│   │   │   └── conflicts.py         # Conflict detection algorithm
│   │   └── ...
│   └── utils/
│       ├── crypto.py                # Fernet encrypt/decrypt
│       └── document_parser.py       # PDF/PPT/MD text extraction
│
├── frontend/                        # PyQt6 desktop client
│   ├── app.py                       # Standalone prototype (with mock mode)
│   ├── main.py                      # Modular entry
│   ├── api/client.py                # HTTP client wrapper
│   ├── views/                       # Page-level views
│   ├── components/                  # Reusable UI widgets
│   └── workers/agent_worker.py      # QThread for async API calls
│
├── tests/                           # pytest test suite (141 test cases)
├── alembic/                         # Database migration files
├── run.py                           # One-click startup script
├── .github/workflows/ci.yml         # CI/CD pipeline
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

The suite includes **141 test cases** covering API routes, business logic, and agent tools. All LLM and network calls are mocked.

---

## CI/CD Pipeline

The project uses a **dual CI/CD pipeline** with both **GitHub Actions** and **Jenkins**, ensuring every push to `main`/`master` triggers an automated build-test-package-deploy workflow.

- **GitHub Actions:** [`.github/workflows/ci.yml`](.github/workflows/ci.yml) — runs on `ubuntu-latest` with PostgreSQL 15 service container
- **Jenkins:** [`Jenkinsfile`](Jenkinsfile) — runs on local Windows with conda environment

### Pipeline Steps

| Step | Tool | Description |
|------|------|-------------|
| 1. Checkout | Git | Clone repository source code |
| 2. Install Dependencies | pip | Install `requirements.txt` + `requirements-dev.txt` + `lizard` |
| 3. Format Check | Black | Verify code formatting (`black --check .`) |
| 4. Lint | Flake8 | Static analysis (`flake8 .`) |
| 5. Test | pytest + pytest-cov | Run 141 test cases with coverage (XML + HTML reports) |
| 6. Coverage Upload | Codecov | Upload coverage XML (GitHub Actions) |
| 7. Metrics | `scripts/generate_metrics.py`, lizard | Generate LOC, complexity, dependency metrics |
| 8. Docker Build | Docker | Build image from [`Dockerfile`](Dockerfile) (`python:3.10-slim`) |
| 9. Docker Push | Docker Hub | Push `kabukimonosakura/student-productivity-agent:latest` + commit SHA tag |

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

---

## References

| Document | Description |
|----------|-------------|
| [Guideline/README.md](Guideline/README.md) | Detailed development guide with setup, API contracts, and test instructions |
| [proposal-26s-13.md](proposal-26s-13.md) | Requirements analysis document |
| [design-26s-13.md](design-26s-13.md) | Architecture design and UI design |
| [Guideline/docs/Frontend Relevant/backend-interface-contract-zh.md](Guideline/docs/Frontend%20Relevant/backend-interface-contract-zh.md) | Backend API contract (Chinese) |
| [Guideline/docs/Frontend Relevant/frontend-api-connection-zh.md](Guideline/docs/Frontend%20Relevant/frontend-api-connection-zh.md) | Frontend API connection guide |
| `http://127.0.0.1:8000/docs` | Interactive Swagger API docs (when backend is running) |
