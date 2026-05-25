# Final Report — Team 26s-13

> **Student Productivity Agent**

---

## Part I. Metrics (2 points)

We use a custom metrics script (`scripts/generate_metrics.py`) together with **lizard** (cyclomatic complexity), **pytest** (test collection), and manual dependency analysis to compute the following project metrics.

### 1.1 Lines of Code

| Metric | Value |
|--------|-------|
| Total Lines of Code | **25,628** |
| Python LOC | **25,576** |
| Total Source Files | **129** |
| Python Files | **128** |

**LOC by Directory:**

| Directory | LOC | Description |
|-----------|-----|-------------|
| `backend/` | 15,084 | FastAPI backend: API routes, agent loop, services, tools |
| `frontend/` | 7,842 | PyQt6 desktop client: views, components, workers |
| `tests/` | 1,951 | pytest test suite (15 test files, 141 test cases) |
| `scripts/` | 354 | Build & metrics scripts |
| `alembic/` | 259 | Database migration files |
| `root` | 138 | Top-level scripts (`run.py`, etc.) |

> **Tool:** Lines counted by `scripts/generate_metrics.py` using file-level traversal, including `.py`, `.js`, `.ts`, `.html`, `.css`, `.sql`, `.yml` files. Excludes `.git`, `__pycache__`, `data`, `reports`, virtual environments.

### 1.2 Cyclomatic Complexity

| Metric | Value |
|--------|-------|
| Total Functions Analyzed | **469** |
| Total Cyclomatic Complexity | **4,067** |
| Average Complexity per Function | **8.67** |

**Top 5 Most Complex Functions:**

| Function | File | CC |
|----------|------|----|
| `_cas_login_for_tis` | `backend/services/schedule_service/cas_auth.py` | 113 |
| `_fetch_cms_course_file_material` | `backend/services/schedule_service/bb_materials.py` | 101 |
| `_tis_extract_meetings` | `backend/services/schedule_service/fetch_tis.py` | 76 |
| `_cas_login_for_blackboard` | `backend/services/schedule_service/cas_auth.py` | 62 |
| `detect_schedule_conflicts` | `backend/agent/tools/scheduler.py` | 54 |

> **Tool:** Cyclomatic complexity computed by **lizard** (via `python -m lizard backend/`). The most complex functions involve multi-step CAS authentication flows and web scraping logic with many conditional branches for error handling and HTML parsing.

### 1.3 Number of Dependencies

| Metric | Value |
|--------|-------|
| Direct Dependencies (from `generate_metrics.py`) | **37** |

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
| Other | python-multipart |

> **Tool:** Dependencies counted by `scripts/generate_metrics.py` using `pip list --format=freeze` to read all installed packages, supplemented with requirements file parsing for direct dependency classification.

### 1.4 Metrics Script & Generated Report

- **Script:** [`scripts/generate_metrics.py`](https://github.com/sustech-cs304/team-project-26spring-26s-13/blob/main/scripts/generate_metrics.py)
- **JSON Output:** `reports/metrics.json`
- **HTML Report:** `reports/metrics.html` (viewable in any browser)

<!-- TODO: Insert screenshot of metrics.html opened in browser后续全量实现后补充完整 -->
![Metrics HTML Report](screenshots/metrics-report.png)
*Screenshot: Open `reports/metrics.html` in your browser to view the full metrics dashboard.*

---

## Part II. CI/CD Pipeline Description

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
| **4. Test** | pytest, pytest-cov, pytest-asyncio | Run 141 test cases with coverage. Generates XML/HTML coverage reports and JUnit XML |
| **5. Metrics** | `scripts/generate_metrics.py`, lizard | Generate LOC, cyclomatic complexity, dependency count, and test count reports |
| **6. Build Docker Image** | Docker | Build a Docker image using the `Dockerfile` (based on `python:3.10-slim`) |
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

<!-- TODO: Insert screenshot of GitHub Actions successful run -->
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

<!-- TODO: Insert screenshot of Jenkins successful build -->
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

<!-- TODO: Insert screenshot of Docker Hub repository showing the pushed images -->
![Docker Hub](screenshots/docker-hub.png)
*Screenshot: Go to https://hub.docker.com/r/kabukimonosakura/student-productivity-agent → show the Tags tab with `latest` and other tags.*

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