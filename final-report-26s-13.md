# Final Report — Team 26s-13

> **Student Productivity Agent**
> SUSTech Software Engineering Spring 2026

---

## Part I. Metrics (2 points)

We use a custom metrics script ([`scripts/generate_metrics.py`](https://github.com/sustech-cs304/team-project-26spring-26s-13/blob/main/scripts/generate_metrics.py)) together with **lizard** (cyclomatic complexity), **pytest** (test collection), and manual dependency analysis to compute the following project metrics.

### 1.1 Lines of Code

| Metric | Value |
|--------|-------|
| Total Lines of Code | **30,445** |
| Python LOC | **30,393** |
| Total Source Files | **139** |
| Python Files | **138** |

**LOC by Directory:**

| Directory | LOC | Description |
|-----------|-----|-------------|
| `backend/` | 18,071 | FastAPI backend: API routes, agent loop, services, tools |
| `frontend/` | 8,301 | PyQt6 desktop client: views, components, workers |
| `tests/` | 2,711 | pytest test suite (19 test files, 182 test cases) |
| `scripts/` | 917 | Build & metrics scripts |
| `alembic/` | 307 | Database migration files (3 versions) |
| `root` | 138 | Top-level scripts (`run.py`, etc.) |

> **Tool:** Lines counted by `scripts/generate_metrics.py` using file-level traversal, including `.py`, `.js`, `.ts`, `.html`, `.css`, `.sql`, `.yml` files. Excludes `.git`, `__pycache__`, `data`, `reports`, virtual environments.

### 1.2 Cyclomatic Complexity

| Metric | Value |
|--------|-------|
| Total Functions Analyzed | **548** |
| Total Cyclomatic Complexity | **4,768** |
| Average Complexity per Function | **8.7** |

**Top 5 Most Complex Functions:**

| Function | File | CC |
|----------|------|----|
| `_fetch_cms_course_file_material` | `backend/services/schedule_service/bb_materials.py` | 114 |
| `_cas_login_for_tis` | `backend/services/schedule_service/cas_auth.py` | 113 |
| `_tis_extract_meetings` | `backend/services/schedule_service/fetch_tis.py` | 76 |
| `_cas_login_for_blackboard` | `backend/services/schedule_service/cas_auth.py` | 62 |
| `fetch_blackboard_course_materials` | `backend/services/schedule_service/bb_materials.py` | 59 |

> **Tool:** Cyclomatic complexity computed by **lizard** (via `python -m lizard backend/`). The most complex functions involve multi-step CAS authentication flows and web scraping logic with many conditional branches for error handling and HTML parsing.

### 1.3 Number of Dependencies

| Metric | Value |
|--------|-------|
| Direct Dependencies | **38** |

**Direct Dependency Breakdown:**

| Category | Dependencies |
|----------|-------------|
| Backend Framework | fastapi, uvicorn[standard], pydantic, pydantic-settings, pydantic-ai |
| Database | sqlalchemy, asyncpg, alembic, chromadb |
| Document Parsing | pymupdf, python-docx, python-pptx, paddleocr, paddlepaddle, numpy, pillow |
| Web Scraping | httpx, aiohttp, beautifulsoup4, selenium |
| Security | cryptography, passlib[bcrypt], bcrypt, python-jose[cryptography] |
| Frontend | pyqt6, requests |
| HTTP Mocks (testing) | responses, aioresponses |
| Testing & Quality | pytest, pytest-asyncio, pytest-cov, pytest-mock, black, flake8, lizard |
| Embeddings | sentence-transformers |
| Other | python-multipart |

> **Tool:** Dependencies counted by `scripts/generate_metrics.py` using `pip list --format=freeze` to read all installed packages, supplemented with requirements file parsing for direct dependency classification.

### 1.4 Number of Source Files

| Category | Count |
|----------|-------|
| Backend Python Files | ~92 |
| Frontend Python Files | ~23 |
| Test Files | 19 |
| Scripts | ~5 |
| Configuration / CI | ~5 |
| **Total Source Files** | **139** |

### 1.5 Metrics Script & Generated Report

- **Script:** [`scripts/generate_metrics.py`](https://github.com/sustech-cs304/team-project-26spring-26s-13/blob/main/scripts/generate_metrics.py)
- **JSON Output:** `reports/metrics.json`
- **HTML Report:** `reports/metrics.html` (viewable in any browser)

<!-- TODO: Add screenshot of metrics.html -->
![Metrics HTML Report](screenshots/metrics-report.png)
*Screenshot: Open `reports/metrics.html` in your browser to view the full metrics dashboard.*

---

## Part II. CI/CD Pipeline Description (2 points)

Our project implements a **dual CI/CD pipeline** using both **GitHub Actions** and **Jenkins**, ensuring that every push to `main` / `master` triggers an automated build-test-package-deploy workflow.

### 2.1 Pipeline Overview

```
┌─────────────┐    ┌──────────────┐    ┌────────────┐    ┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌────────────┐
│  Checkout    │───>│  Install     │───>│   Lint     │───>│    Test     │───>│   Metrics    │───>│   Docker    │───>│   Push     │
│  Source Code │    │  Deps        │    │  (Black +  │    │  (pytest +  │    │   Report     │    │   Build     │    │  Docker    │
│              │    │  (pip)       │    │   Flake8)  │    │   Coverage) │    │  Generation  │    │   Image     │    │   Hub      │
└─────────────┘    └──────────────┘    └────────────┘    └─────────────┘    └──────────────┘    └─────────────┘    └────────────┘
```

### 2.2 Pipeline Steps & Tools

| Step | Tool(s) | Description |
|------|---------|-------------|
| **1. Checkout** | Git | Clone the repository source code |
| **2. Install Dependencies** | pip | Install `requirements.txt` and `requirements-dev.txt` + `lizard` |
| **3. Lint** | Black (formatter), Flake8 (linter) | Format check (`black --check .`) and static analysis (`flake8 .`) |
| **4. Test** | pytest, pytest-cov, pytest-asyncio | Run 182 test cases with coverage. Generates XML/HTML coverage reports and JUnit XML |
| **5. Metrics** | `scripts/generate_metrics.py`, lizard | Generate LOC, cyclomatic complexity, dependency count, and test count reports |
| **6. Build Docker Image** | Docker | Build a Docker image using the [`Dockerfile`](https://github.com/sustech-cs304/team-project-26spring-26s-13/blob/main/Dockerfile) (based on `python:3.10-slim`) |
| **7. Push to Docker Hub** | Docker Hub | Push image with `latest` tag and commit SHA tag |

### 2.3 GitHub Actions Configuration

**Config file:** [`.github/workflows/ci.yml`](https://github.com/sustech-cs304/team-project-26spring-26s-13/blob/main/.github/workflows/ci.yml)

**Trigger:** Runs on push / pull request to `main` / `master`, plus manual `workflow_dispatch`.

**Environment:** `ubuntu-latest` runner with Python 3.10 and PostgreSQL 15 service container.

**Key features:**
- PostgreSQL service container for integration test support
- pip caching for faster dependency installation
- Coverage report uploaded to **Codecov**
- Test reports and metrics reports uploaded as **GitHub Actions Artifacts** (30-day retention)
- Docker image built and pushed to Docker Hub on `main`/`master` only
- Manual trigger supported via `workflow_dispatch`

<!-- TODO: Add screenshot of GitHub Actions successful run -->
![GitHub Actions Successful Run](screenshots/github-actions-success.png)
*Screenshot: Go to your GitHub repo → Actions tab → click the latest successful workflow run. Show the green checkmark and all steps expanded.*

### 2.4 Jenkins Configuration

**Config file:** [`Jenkinsfile`](https://github.com/sustech-cs304/team-project-26spring-26s-13/blob/main/Jenkinsfile)

**Environment:** Runs on a local Windows machine with Cygwin/Git Bash `sh`, using the conda environment `software-engineering` (Python 3.10).

**Key features:**
- Declarative pipeline with 7 stages
- Uses local conda environment Python (not system Python)
- Reports archived as Jenkins build artifacts
- Docker Hub credentials managed via Jenkins credential store (`Docker-Hub`)
- Docker image tagged with both `latest` and `$BUILD_NUMBER`

<!-- TODO: Add screenshot of Jenkins successful build -->
![Jenkins Successful Build](screenshots/jenkins-success.png)
*Screenshot: Go to your Jenkins dashboard → click the latest successful build. Show all stages green.*

### 2.5 Artifacts & Reports Generated

| Artifact | Format | Description |
|----------|--------|-------------|
| `reports/coverage.xml` | XML | Cobertura-format coverage report (for Codecov) |
| `reports/coverage-html/` | HTML | Detailed HTML coverage report (open `index.html`) |
| `reports/junit.xml` | XML | JUnit-format test results |
| `reports/flake8.log` | Text | Flake8 linting output |
| `reports/black.log` (Jenkins only) | Text | Black format check output |
| `reports/test-output.log` (Jenkins only) | Text | Full pytest console output |
| `reports/metrics.json` | JSON | Machine-readable metrics data |
| `reports/metrics.html` | HTML | Human-readable metrics dashboard |

### 2.6 Docker Image

- **Image:** `kabukimonosakura/student-productivity-agent`
- **Tags:** `latest` + commit SHA (GitHub Actions) / `BUILD_NUMBER` (Jenkins)
- **Base image:** `python:3.10-slim`
- **Exposed port:** 8000
- **Dockerfile:** [`Dockerfile`](https://github.com/sustech-cs304/team-project-26spring-26s-13/blob/main/Dockerfile)

<!-- TODO: Add screenshot of Docker Hub repository -->
![Docker Hub](screenshots/docker-hub.png)
*Screenshot: Go to https://hub.docker.com/r/kabukimonosakura/student-productivity-agent → show the Tags tab with `latest` and other tags.*

---

## Part III. Project Features Summary

The Student Productivity Agent provides the following **8 distinct and meaningful features**:

### Feature 1: Multi-Source Scheduler
Automatically scrapes scheduling data from the SUSTech Academic Calendar and Blackboard deadlines, detects time conflicts with personal tasks, and suggests optimized study calendars.

### Feature 2: Batch Blackboard Material Crawler & RAG Ingestion
CAS-authenticated BFS crawling of all enrolled Blackboard courses, parallel downloading with current-semester filtering, followed by automatic LLM-based subject classification, semantic chunking, and ChromaDB vector embedding.

### Feature 3: Campus Encyclopedia (RAG-based Q&A)
An intelligent QA system answering campus-related queries using Retrieval-Augmented Generation over official SUSTech documents stored in ChromaDB with subject-based sharding across 21 collections.

### Feature 4: Library Discussion Room Query
Queries available discussion rooms in the SUSTech Library by location, time slot, and capacity, returning real-time availability for planning group study sessions.

### Feature 5: Study Copilot
Processes uploaded or local academic materials (PDFs, PPTs, Markdown notes), extracts key concepts, generates concise study summaries, and creates customized practice quizzes.

### Feature 6: Email Service
Sends emails with Markdown attachments and conversation summaries to users' SUSTech email addresses. Supports attaching original files from the knowledge base with zip compression.

### Feature 7: Personal Task Management
The Agent extracts task information from conversations and stores it in PostgreSQL. Tasks are used for schedule conflict detection and can be managed through natural language commands.

### Feature 8: System-Level OS Automation
Executes file system operations via natural language commands within an isolated user workspace. All write operations require Human-in-the-Loop (HITL) approval through a dedicated authorization dialog, with full audit logging.

### Non-functional Highlights

- **Security:** All sensitive credentials (CAS passwords, API keys) are encrypted at rest with Fernet. The frontend never directly accesses the database.
- **Non-blocking UX:** Heavy reasoning and web scraping run on the backend; PyQt6 frontend uses `QThread` workers to keep the UI responsive.
- **HITL Safety:** Destructive OS operations are intercepted and require explicit user approval before execution.
- **Streaming:** Agent responses support real-time streaming for progressive display.
- **Internationalization:** UI supports both English and Chinese.

---

## Appendix: How to Reproduce

### Run the pipeline locally

```bash
# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt
pip install lizard

# Lint
black --check .
flake8 .

# Test with coverage
python -m pytest tests/ --cov=backend --cov-report=html:reports/coverage-html --junitxml=reports/junit.xml -v

# Generate metrics
python scripts/generate_metrics.py

# Build Docker image
docker build -t student-productivity-agent .
```

### View the reports

1. **Coverage HTML:** Open `reports/coverage-html/index.html` in a browser
2. **Metrics HTML:** Open `reports/metrics.html` in a browser
3. **GitHub Actions Artifacts:** Go to repo → Actions → click a run → download Artifacts
4. **Jenkins Artifacts:** Go to build page → Build Artifacts → download `reports/`
