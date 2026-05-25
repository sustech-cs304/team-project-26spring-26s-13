"""
scripts/generate_metrics.py
Generate project metrics and HTML documentation report.

Usage:
    python scripts/generate_metrics.py

Output:
    reports/metrics.json        — Machine-readable metrics
    reports/metrics.html        — Human-readable HTML report
"""

import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def count_loc_and_files():
    """Count lines of code and source files."""
    total_loc = 0
    total_files = 0
    py_loc = 0
    py_files = 0
    by_dir = {}

    skip_prefixes = (
        ".git",
        ".pytest_cache",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "env",
        "data",
        "reports",
        ".mypy_cache",
    )
    for root, _dirs, files in os.walk(str(PROJECT_ROOT)):
        # Skip hidden, virtual env, cache dirs
        rel = os.path.relpath(root, str(PROJECT_ROOT))
        parts = rel.replace("\\", "/").split("/")
        if any(p.startswith(sp) or p == sp for p in parts for sp in skip_prefixes):
            continue

        for f in files:
            if not f.endswith(
                (".py", ".js", ".ts", ".html", ".css", ".sql", ".yml", ".yaml")
            ):
                continue
            fpath = os.path.join(root, f)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                    loc = sum(1 for _ in fh)
            except Exception:
                continue
            total_loc += loc
            total_files += 1
            if f.endswith(".py"):
                py_loc += loc
                py_files += 1
            # Track by top-level dir
            top = parts[0] if parts and parts[0] != "." else "root"
            by_dir[top] = by_dir.get(top, 0) + loc

    return {
        "total_loc": total_loc,
        "total_files": total_files,
        "python_loc": py_loc,
        "python_files": py_files,
        "loc_by_directory": by_dir,
    }


def count_dependencies():
    """Count project dependencies from installed packages and requirements files."""
    # Primary: read actual installed packages via pip
    installed = set()
    try:
        output = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=freeze"],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="ignore",
        )
        for line in output.stdout.strip().split("\n"):
            if "==" in line:
                pkg = line.split("==")[0].strip()
                if pkg and not pkg.startswith("-"):
                    installed.add(pkg.lower())
    except Exception:
        pass

    # Supplemental: parse requirements files for declared names
    declared = set()
    for req_file in ("requirements.txt", "requirements-dev.txt"):
        fpath = PROJECT_ROOT / req_file
        if not fpath.exists():
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    pkg = (
                        line.split(">=")[0]
                        .split("==")[0]
                        .split("<")[0]
                        .split(";")[0]
                        .strip()
                    )
                    if pkg:
                        declared.add(pkg.lower())

    return {
        "total_dependencies": len(declared),
        "total_installed": len(installed),
        "dependencies": sorted(declared),
        "installed_packages": sorted(installed),
    }


def compute_cyclomatic_complexity():
    """Compute cyclomatic complexity using lizard (if available), else flake8 radon."""
    result = {"average": 0.0, "total_functions": 0, "total_complexity": 0, "worst": []}
    try:
        output = subprocess.run(
            [sys.executable, "-m", "lizard", str(BACKEND_DIR)],
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            errors="ignore",
            cwd=str(PROJECT_ROOT),
        )
        if output.stdout.strip():
            lines = output.stdout.strip().split("\n")
            total_cc = 0
            total_fn = 0
            worst = []
            for line in lines:
                parts = line.split()
                if len(parts) < 6:
                    continue
                try:
                    cc_val = int(parts[1])
                except (ValueError, IndexError):
                    continue
                fn_info = parts[5] if len(parts) > 5 else ""
                total_cc += cc_val
                total_fn += 1
                worst.append({"name": fn_info, "cc": cc_val})
            worst.sort(key=lambda x: x["cc"], reverse=True)
            result["total_functions"] = total_fn
            result["total_complexity"] = total_cc
            result["average"] = round(total_cc / max(total_fn, 1), 2)
            result["worst"] = worst[:10]
            data = json.loads(output.stdout)
            funcs = data if isinstance(data, list) else []
            total_cc = 0
            worst = []
            for fn in funcs:
                cc = fn.get("cyclomatic_complexity", 1)
                total_cc += cc
                worst.append(
                    {
                        "name": fn.get("name", ""),
                        "file": fn.get("filename", ""),
                        "cc": cc,
                    }
                )
            worst.sort(key=lambda x: x["cc"], reverse=True)
            result["total_functions"] = len(funcs)
            result["total_complexity"] = total_cc
            result["average"] = round(total_cc / max(len(funcs), 1), 2)
            result["worst"] = worst[:10]
    except Exception as e:
        result["error"] = str(e)
    return result


def count_test_cases():
    """Count test cases using pytest --collect-only."""
    result = {"total": 0, "by_file": {}}
    try:
        output = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            errors="ignore",
            cwd=str(PROJECT_ROOT),
        )
        last_line = (
            (output.stdout or "").strip().split("\n")[-1] if output.stdout else ""
        )
        import re

        m = re.search(r"(\d+)\s+tests?\s+collected", last_line)
        if m:
            result["total"] = int(m.group(1))
    except Exception:
        pass
    return result


def parse_junit_xml():
    """Parse reports/junit.xml for test results."""
    result = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "time": 0.0,
        "by_file": {},
    }
    junit_path = REPORTS_DIR / "junit.xml"
    if not junit_path.exists():
        return result
    try:
        tree = ET.parse(str(junit_path))
        root = tree.getroot()
        for suite in root.iter("testsuite"):
            result["total"] += int(suite.get("tests", "0"))
            result["errors"] += int(suite.get("errors", "0"))
            result["failed"] += int(suite.get("failures", "0"))
            result["skipped"] += int(suite.get("skipped", "0"))
            result["time"] += float(suite.get("time", "0"))
            for tc in suite.iter("testcase"):
                cn = tc.get("classname", "")
                name = tc.get("name", "")
                t = float(tc.get("time", "0"))
                status = "passed"
                child = list(tc)
                for c in child:
                    if c.tag == "failure":
                        status = "failed"
                    elif c.tag == "error":
                        status = "error"
                    elif c.tag == "skipped":
                        status = "skipped"
                # Group by file name from classname
                file_name = cn.replace("tests.", "tests/")
                if file_name not in result["by_file"]:
                    result["by_file"][file_name] = {
                        "total": 0,
                        "passed": 0,
                        "failed": 0,
                        "errors": 0,
                        "skipped": 0,
                        "time": 0.0,
                        "cases": [],
                    }
                result["by_file"][file_name]["total"] += 1
                result["by_file"][file_name][status] += 1
                result["by_file"][file_name]["time"] += t
                result["by_file"][file_name]["cases"].append(
                    {"name": name, "status": status, "time": round(t, 3)}
                )
        result["passed"] = (
            result["total"] - result["failed"] - result["errors"] - result["skipped"]
        )
    except Exception:
        pass
    return result


def parse_coverage_xml():
    """Parse reports/coverage.xml for coverage data."""
    result = {
        "line_rate": 0.0,
        "lines_valid": 0,
        "lines_covered": 0,
        "packages": [],
    }
    cov_path = REPORTS_DIR / "coverage.xml"
    if not cov_path.exists():
        return result
    try:
        tree = ET.parse(str(cov_path))
        root = tree.getroot()
        result["line_rate"] = float(root.get("line-rate", "0"))
        result["lines_valid"] = int(root.get("lines-valid", "0"))
        result["lines_covered"] = int(root.get("lines-covered", "0"))
        for pkg in root.iter("package"):
            name = pkg.get("name", "")
            rate = float(pkg.get("line-rate", "0"))
            classes = []
            for cls in pkg.iter("class"):
                cls_name = cls.get("name", "")
                cls_rate = float(cls.get("line-rate", "0"))
                if cls_name.endswith(".py"):
                    classes.append({"name": cls_name, "rate": cls_rate})
            classes.sort(key=lambda x: x["rate"])
            result["packages"].append(
                {"name": name, "rate": rate, "classes": classes}
            )
    except Exception:
        pass
    return result


def _clean_fn_name(raw):
    """Clean lizard output into readable function name + file."""
    if "@" in raw:
        parts = raw.split("@")
        name = parts[0]
        loc_info = parts[1] if len(parts) > 1 else ""
        line_range = loc_info.split("-")[0] if "-" in loc_info else ""
        return name, line_range
    return raw, ""


def _cc_color(cc):
    if cc <= 10:
        return "#27ae60"
    if cc <= 20:
        return "#f39c12"
    return "#e74c3c"


def generate_html_report(metrics, junit, coverage):
    """Generate a professional staging-site HTML report."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    loc = metrics["loc"]
    cc = metrics["complexity"]
    deps = metrics["deps"]
    tests = metrics["tests"]

    cov_pct = f"{coverage['line_rate'] * 100:.1f}"
    cov_color = _cc_color(100 - int(coverage["line_rate"] * 100))

    # LOC bar chart data
    loc_dirs = sorted(loc["loc_by_directory"].items(), key=lambda x: -x[1])
    max_loc = max(v for _, v in loc_dirs) if loc_dirs else 1

    loc_bars = ""
    for d, v in loc_dirs:
        pct = int(v / max_loc * 100)
        loc_bars += f"""
        <div class="bar-row">
          <span class="bar-label">{d}</span>
          <div class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></div>
          <span class="bar-value">{v:,}</span>
        </div>"""

    # Complexity top functions
    worst_rows = ""
    for fn in cc.get("worst", []):
        name, line = _clean_fn_name(fn["name"])
        file_hint = ""
        if "file" in fn and fn["file"]:
            file_hint = fn["file"]
        col = _cc_color(fn["cc"])
        bar_w = min(int(fn["cc"] / 113 * 100), 100)
        worst_rows += f"""
        <tr>
          <td><code class="fn-name">{name}</code>
            {f'<br><span class="fn-file">{file_hint}</span>' if file_hint else ''}
            {f'<span class="fn-line">:{line}</span>' if line else ''}</td>
          <td class="cc-cell"><span class="cc-badge" style="background:{col}">{fn["cc"]}</span></td>
          <td><div class="mini-bar-track"><div class="mini-bar-fill" style="width:{bar_w}%;background:{col}"></div></div></td>
        </tr>"""

    # Dependency categories
    dep_categories = {
        "Backend": [
            "fastapi",
            "uvicorn[standard]",
            "pydantic",
            "pydantic-settings",
            "pydantic-ai",
        ],
        "Database": ["sqlalchemy", "asyncpg", "alembic", "chromadb"],
        "Doc Parsing": [
            "pymupdf",
            "python-docx",
            "python-pptx",
            "paddleocr",
            "paddlepaddle",
            "numpy",
            "pillow",
        ],
        "Web Scraping": ["httpx", "aiohttp", "beautifulsoup4", "selenium"],
        "Security": [
            "cryptography",
            "passlib[bcrypt]",
            "bcrypt",
            "python-jose[cryptography]",
        ],
        "Frontend": ["pyqt6", "requests"],
        "Testing & QA": [
            "pytest",
            "pytest-asyncio",
            "pytest-cov",
            "pytest-mock",
            "black",
            "flake8",
            "lizard",
        ],
        "Other": ["python-multipart", "aioresponses", "responses", "aiosqlite"],
    }
    dep_grid = ""
    colors = [
        "#3498db",
        "#2ecc71",
        "#9b59b6",
        "#e67e22",
        "#1abc9c",
        "#e74c3c",
        "#f1c40f",
        "#95a5a6",
    ]
    for i, (cat, pkgs) in enumerate(dep_categories.items()):
        col = colors[i % len(colors)]
        badges = " ".join(f'<span class="dep-tag" style="border-color:{col}">{p}</span>' for p in pkgs)
        dep_grid += f"""
        <div class="dep-card" style="border-top:3px solid {col}">
          <div class="dep-card-title">{cat}</div>
          <div class="dep-card-count">{len(pkgs)}</div>
          <div class="dep-card-list">{badges}</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Project Metrics — Student Productivity Agent</title>
<style>
:root {{
  --primary: #2563eb;
  --primary-light: #dbeafe;
  --success: #16a34a;
  --warning: #d97706;
  --danger: #dc2626;
  --gray-50: #f9fafb;
  --gray-100: #f3f4f6;
  --gray-200: #e5e7eb;
  --gray-300: #d1d5db;
  --gray-500: #6b7280;
  --gray-700: #374151;
  --gray-900: #111827;
  --radius: 8px;
  --shadow: 0 1px 3px rgba(0,0,0,.1), 0 1px 2px rgba(0,0,0,.06);
  --shadow-md: 0 4px 6px rgba(0,0,0,.07), 0 2px 4px rgba(0,0,0,.06);
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
       background:var(--gray-50); color:var(--gray-900); line-height:1.6; }}

/* ── Header ── */
.header {{ background:linear-gradient(135deg,#1e40af,#3b82f6); color:#fff; padding:2rem 0; }}
.header-inner {{ max-width:1100px; margin:0 auto; padding:0 2rem; }}
.header h1 {{ font-size:1.5rem; font-weight:700; }}
.header .subtitle {{ opacity:.85; font-size:.9rem; margin-top:.25rem; }}
.header .meta {{ display:flex; gap:1.5rem; margin-top:.75rem; font-size:.8rem; opacity:.7; }}

/* ── Nav Tabs ── */
.nav {{ background:#fff; border-bottom:1px solid var(--gray-200); position:sticky; top:0; z-index:100; box-shadow:var(--shadow); }}
.nav-inner {{ max-width:1100px; margin:0 auto; padding:0 2rem; display:flex; gap:0; }}
.nav-tab {{ padding:.75rem 1.25rem; font-size:.9rem; font-weight:500; color:var(--gray-500);
            cursor:pointer; border-bottom:2px solid transparent; transition:all .2s; user-select:none; }}
.nav-tab:hover {{ color:var(--primary); }}
.nav-tab.active {{ color:var(--primary); border-bottom-color:var(--primary); }}

/* ── Content ── */
.content {{ max-width:1100px; margin:0 auto; padding:2rem; }}
.section {{ display:none; }}
.section.active {{ display:block; }}

/* ── Dashboard Cards ── */
.dashboard {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:1.25rem; margin-bottom:2rem; }}
.card {{ background:#fff; border-radius:var(--radius); padding:1.5rem; box-shadow:var(--shadow); transition:box-shadow .2s; }}
.card:hover {{ box-shadow:var(--shadow-md); }}
.card-icon {{ font-size:1.75rem; margin-bottom:.5rem; }}
.card-value {{ font-size:2rem; font-weight:700; color:var(--primary); }}
.card-label {{ font-size:.85rem; color:var(--gray-500); margin-top:.25rem; }}

/* ── Panels ── */
.panel {{ background:#fff; border-radius:var(--radius); box-shadow:var(--shadow); margin-bottom:1.5rem; overflow:hidden; }}
.panel-header {{ padding:1rem 1.5rem; border-bottom:1px solid var(--gray-200); font-weight:600; font-size:1rem; display:flex; align-items:center; justify-content:space-between; }}
.panel-body {{ padding:1.5rem; }}

/* ── Tables ── */
table {{ width:100%; border-collapse:collapse; }}
th,td {{ text-align:left; padding:.65rem 1rem; }}
th {{ background:var(--gray-50); font-weight:600; font-size:.8rem; text-transform:uppercase;
      letter-spacing:.05em; color:var(--gray-500); border-bottom:2px solid var(--gray-200); }}
td {{ border-bottom:1px solid var(--gray-100); font-size:.9rem; }}
tr:hover td {{ background:var(--gray-50); }}

/* ── Bar Charts ── */
.bar-row {{ display:flex; align-items:center; margin-bottom:.6rem; }}
.bar-label {{ width:100px; font-size:.85rem; font-weight:500; color:var(--gray-700); flex-shrink:0; }}
.bar-track {{ flex:1; height:24px; background:var(--gray-100); border-radius:4px; overflow:hidden; margin:0 .75rem; }}
.bar-fill {{ height:100%; background:linear-gradient(90deg,var(--primary),#60a5fa); border-radius:4px; transition:width .6s ease; }}
.bar-value {{ width:70px; text-align:right; font-size:.85rem; font-weight:600; color:var(--gray-700); }}

/* ── Complexity ── */
.cc-cell {{ white-space:nowrap; }}
.cc-badge {{ display:inline-block; padding:.15rem .6rem; border-radius:12px; color:#fff; font-weight:700; font-size:.8rem; min-width:36px; text-align:center; }}
.mini-bar-track {{ width:100%; max-width:200px; height:8px; background:var(--gray-100); border-radius:4px; overflow:hidden; }}
.mini-bar-fill {{ height:100%; border-radius:4px; }}
.fn-name {{ font-size:.85rem; color:var(--primary); }}
.fn-file {{ font-size:.75rem; color:var(--gray-500); }}
.fn-line {{ font-size:.75rem; color:var(--gray-500); }}

/* ── Dependencies ── */
.dep-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:1rem; }}
.dep-card {{ background:var(--gray-50); border-radius:var(--radius); padding:1rem 1.25rem; }}
.dep-card-title {{ font-weight:600; font-size:.9rem; color:var(--gray-700); }}
.dep-card-count {{ font-size:1.5rem; font-weight:700; color:var(--primary); margin:.25rem 0; }}
.dep-card-list {{ display:flex; flex-wrap:wrap; gap:.35rem; }}
.dep-tag {{ display:inline-block; font-size:.7rem; padding:.15rem .5rem; border-radius:4px;
            border:1px solid var(--gray-300); background:#fff; color:var(--gray-700); }}

/* ── Summary row ── */
.summary-row {{ display:flex; gap:2rem; flex-wrap:wrap; }}
.summary-item {{ text-align:center; }}
.summary-item .num {{ font-size:2.5rem; font-weight:800; color:var(--primary); }}
.summary-item .lbl {{ font-size:.8rem; color:var(--gray-500); text-transform:uppercase; letter-spacing:.05em; }}

/* ── Footer ── */
.footer {{ text-align:center; padding:2rem; font-size:.8rem; color:var(--gray-500); border-top:1px solid var(--gray-200); margin-top:2rem; }}

@media(max-width:768px) {{
  .dashboard {{ grid-template-columns:1fr 1fr; }}
  .dep-grid {{ grid-template-columns:1fr; }}
  .bar-label {{ width:70px; }}
}}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <div class="header-inner">
    <h1>Student Productivity Agent &mdash; Metrics Report</h1>
    <div class="subtitle">Team 26s-13 &bull; SUSTech CS304 Software Engineering</div>
    <div class="meta">
      <span>Generated: {ts}</span>
      <span>Python 3.10 &bull; FastAPI + PydanticAI</span>
    </div>
  </div>
</div>

<!-- Nav -->
<div class="nav">
  <div class="nav-inner">
    <div class="nav-tab active" data-tab="overview">Overview</div>
    <div class="nav-tab" data-tab="loc">Lines of Code</div>
    <div class="nav-tab" data-tab="complexity">Complexity</div>
    <div class="nav-tab" data-tab="deps">Dependencies</div>
    <div class="nav-tab" data-tab="tests">Test Report</div>
    <div class="nav-tab" data-tab="coverage">Coverage</div>
  </div>
</div>

<!-- Content -->
<div class="content">

<!-- ════ Overview ════ -->
<div class="section active" id="tab-overview">
  <div class="dashboard">
    <div class="card">
      <div class="card-icon">&#128196;</div>
      <div class="card-value">{loc['total_loc']:,}</div>
      <div class="card-label">Lines of Code</div>
    </div>
    <div class="card">
      <div class="card-icon">&#128193;</div>
      <div class="card-value">{loc['total_files']}</div>
      <div class="card-label">Source Files</div>
    </div>
    <div class="card">
      <div class="card-icon">&#128200;</div>
      <div class="card-value">{cc['average']}</div>
      <div class="card-label">Avg Cyclomatic Complexity</div>
    </div>
    <div class="card">
      <div class="card-icon">&#128230;</div>
      <div class="card-value">{deps['total_dependencies']}</div>
      <div class="card-label">Direct Dependencies</div>
    </div>
    <div class="card">
      <div class="card-icon">&#9989;</div>
      <div class="card-value">{tests['total']}</div>
      <div class="card-label">Test Cases</div>
    </div>
    <div class="card">
      <div class="card-icon">&#9881;</div>
      <div class="card-value">{cc['total_functions']}</div>
      <div class="card-label">Functions Analyzed</div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header">LOC Distribution</div>
    <div class="panel-body">
      {loc_bars}
    </div>
  </div>
</div>

<!-- ════ LOC ════ -->
<div class="section" id="tab-loc">
  <div class="panel">
    <div class="panel-header">Summary</div>
    <div class="panel-body">
      <table>
        <tr><th>Metric</th><th>Value</th></tr>
        <tr><td>Total Lines of Code</td><td><strong>{loc['total_loc']:,}</strong></td></tr>
        <tr><td>Python LOC</td><td>{loc['python_loc']:,}</td></tr>
        <tr><td>Total Source Files</td><td>{loc['total_files']}</td></tr>
        <tr><td>Python Files</td><td>{loc['python_files']}</td></tr>
        <tr><td>Non-Python Files</td><td>{loc['total_files'] - loc['python_files']}</td></tr>
      </table>
    </div>
  </div>
  <div class="panel">
    <div class="panel-header">Breakdown by Directory</div>
    <div class="panel-body">
      {loc_bars}
    </div>
  </div>
</div>

<!-- ════ Complexity ════ -->
<div class="section" id="tab-complexity">
  <div class="dashboard">
    <div class="card">
      <div class="card-value">{cc['total_functions']}</div>
      <div class="card-label">Functions Analyzed</div>
    </div>
    <div class="card">
      <div class="card-value">{cc['total_complexity']:,}</div>
      <div class="card-label">Total Complexity</div>
    </div>
    <div class="card">
      <div class="card-value">{cc['average']}</div>
      <div class="card-label">Average CC</div>
    </div>
  </div>
  <div class="panel">
    <div class="panel-header">Top 10 Most Complex Functions</div>
    <div class="panel-body">
      <table>
        <tr><th>Function</th><th>CC</th><th>Relative</th></tr>
        {worst_rows}
      </table>
    </div>
  </div>
</div>

<!-- ════ Dependencies ════ -->
<div class="section" id="tab-deps">
  <div class="summary-row" style="margin-bottom:1.5rem">
    <div class="summary-item"><div class="num">{deps['total_dependencies']}</div><div class="lbl">Direct Dependencies</div></div>
    <div class="summary-item"><div class="num">{deps['total_installed']}</div><div class="lbl">Installed Packages (incl. transitive)</div></div>
  </div>
  <div class="panel">
    <div class="panel-header">By Category</div>
    <div class="panel-body">
      <div class="dep-grid">
        {dep_grid}
      </div>
    </div>
  </div>
  <div class="panel">
    <div class="panel-header">Full Dependency List</div>
    <div class="panel-body" style="columns:2">
      {"".join(f'<span class="dep-tag" style="margin-bottom:.3rem;display:inline-block">{d}</span> ' for d in deps['dependencies'])}
    </div>
  </div>
</div>

<!-- ════ Test Report ════ -->
<div class="section" id="tab-tests">
  <div class="dashboard">
    <div class="card">
      <div class="card-icon">&#9989;</div>
      <div class="card-value">{junit['total']}</div>
      <div class="card-label">Total Tests</div>
    </div>
    <div class="card">
      <div class="card-icon">&#128994;</div>
      <div class="card-value" style="color:var(--success)">{junit['passed']}</div>
      <div class="card-label">Passed</div>
    </div>
    <div class="card">
      <div class="card-icon">&#128308;</div>
      <div class="card-value" style="color:var(--danger)">{junit['failed']}</div>
      <div class="card-label">Failed</div>
    </div>
    <div class="card">
      <div class="card-icon">&#9203;</div>
      <div class="card-value">{junit['time']:.1f}s</div>
      <div class="card-label">Duration</div>
    </div>
  </div>
  <div class="panel">
    <div class="panel-header">Results by Test File</div>
    <div class="panel-body">
      <table>
        <tr><th>Test File</th><th>Total</th><th>Passed</th><th>Failed</th><th>Time</th><th>Status</th></tr>
""" + "".join(f"""
        <tr>
          <td><code>{f.replace('tests/', '')}</code></td>
          <td>{d['total']}</td>
          <td style="color:var(--success);font-weight:600">{d['passed']}</td>
          <td style="color:var(--danger);font-weight:600">{d['failed'] + d['errors']}</td>
          <td>{d['time']:.2f}s</td>
          <td>{'<span class="cc-badge" style="background:var(--success)">PASS</span>' if d['failed'] + d['errors'] == 0 else '<span class="cc-badge" style="background:var(--danger)">FAIL</span>'}</td>
        </tr>""" for f, d in sorted(junit.get("by_file", {}).items())) + """
      </table>
    </div>
  </div>
  <div class="panel">
    <div class="panel-header">All Test Cases <span style="font-weight:400;font-size:.8rem;color:var(--gray-500)">""" + f"{junit['total']} total" + """</span></div>
    <div class="panel-body" style="max-height:500px;overflow-y:auto">
      <table>
        <tr><th style="width:50px">#</th><th>Test</th><th style="width:80px">Time</th><th style="width:70px">Status</th></tr>
""" + "".join(
        f"""        <tr><td>{i+1}</td><td><code class="fn-name">{c['name']}</code><br><span class="fn-file">{f.replace('tests/', '')}</span></td><td>{c['time']:.3f}s</td><td>{'<span style="color:var(--success)">&#10003;</span>' if c['status'] == 'passed' else '<span style="color:var(--danger)">&#10007;</span>'}</td></tr>\n"""
        for i, (f, d) in enumerate(sorted(junit.get("by_file", {}).items()))
        for c in d.get("cases", [])
    ) + f"""      </table>
    </div>
  </div>
</div>

<!-- ════ Coverage ════ -->
<div class="section" id="tab-coverage">
  <div class="dashboard">
    <div class="card">
      <div class="card-icon">&#128202;</div>
      <div class="card-value">{cov_pct}%</div>
      <div class="card-label">Line Coverage</div>
    </div>
    <div class="card">
      <div class="card-icon">&#128196;</div>
      <div class="card-value">{coverage['lines_covered']:,}</div>
      <div class="card-label">Lines Covered</div>
    </div>
    <div class="card">
      <div class="card-icon">&#128209;</div>
      <div class="card-value">{coverage['lines_valid']:,}</div>
      <div class="card-label">Total Lines</div>
    </div>
  </div>
  <div class="panel">
    <div class="panel-header">Coverage Gauge</div>
    <div class="panel-body" style="text-align:center;padding:2rem">
      <div style="position:relative;width:180px;height:180px;margin:0 auto">
        <svg viewBox="0 0 36 36" style="width:100%;height:100%;transform:rotate(-90deg)">
          <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none" stroke="var(--gray-200)" stroke-width="3"/>
          <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none" stroke="{cov_color}" stroke-width="3"
                stroke-dasharray="{cov_pct}, 100" stroke-linecap="round"/>
        </svg>
        <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:2rem;font-weight:800;color:{cov_color}">{cov_pct}%</div>
      </div>
      <p style="margin-top:1rem;color:var(--gray-500)">{coverage['lines_covered']:,} / {coverage['lines_valid']:,} lines covered</p>
    </div>
  </div>
  <div class="panel">
    <div class="panel-header">Coverage by Package</div>
    <div class="panel-body">
      <table>
        <tr><th>Package</th><th style="width:80px">Rate</th><th>Bar</th></tr>
""" + "".join(
        f"""        <tr>
          <td><code>{p['name'] or '.'}</code></td>
          <td style="font-weight:600;color:{_cc_color(100-int(p['rate']*100))}">{p['rate']*100:.1f}%</td>
          <td><div class="mini-bar-track" style="max-width:300px"><div class="mini-bar-fill" style="width:{p['rate']*100:.1f}%;background:{_cc_color(100-int(p['rate']*100))}"></div></div></td>
        </tr>\n"""
        for p in coverage.get("packages", [])
    ) + """      </table>
    </div>
  </div>
  <div class="panel">
    <div class="panel-header">Coverage by Module (top 30 lowest)</div>
    <div class="panel-body" style="max-height:500px;overflow-y:auto">
      <table>
        <tr><th>Module</th><th style="width:80px">Rate</th><th>Bar</th></tr>
""" + "".join(
        f"""        <tr>
          <td><code class="fn-name">{c['name']}</code></td>
          <td style="font-weight:600;color:{_cc_color(100-int(c['rate']*100))}">{c['rate']*100:.1f}%</td>
          <td><div class="mini-bar-track" style="max-width:250px"><div class="mini-bar-fill" style="width:{max(c['rate']*100,1):.1f}%;background:{_cc_color(100-int(c['rate']*100))}"></div></div></td>
        </tr>\n"""
        for c in sorted(
            [c for p in coverage.get("packages", []) for c in p.get("classes", [])],
            key=lambda x: x["rate"],
        )[:30]
    ) + f"""      </table>
    </div>
  </div>
</div>

</div><!-- /.content -->

<!-- Footer -->
<div class="footer">
  Generated by <code>scripts/generate_metrics.py</code> &bull; {ts}
</div>

<!-- Tab Switching -->
<script>
document.querySelectorAll('.nav-tab').forEach(function(tab) {{
  tab.addEventListener('click', function() {{
    document.querySelectorAll('.nav-tab').forEach(function(t) {{ t.classList.remove('active'); }});
    document.querySelectorAll('.section').forEach(function(s) {{ s.classList.remove('active'); }});
    tab.classList.add('active');
    document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
  }});
}});
</script>
</body>
</html>"""
    return html


def main():
    REPORTS_DIR.mkdir(exist_ok=True)

    print("Computing LOC and file count...")
    loc = count_loc_and_files()

    print("Computing dependencies...")
    deps = count_dependencies()

    print("Computing cyclomatic complexity...")
    cc = compute_cyclomatic_complexity()

    print("Counting test cases...")
    tests = count_test_cases()

    print("Parsing test results...")
    junit = parse_junit_xml()

    print("Parsing coverage data...")
    coverage = parse_coverage_xml()

    metrics = {
        "timestamp": datetime.now().isoformat(),
        "loc": loc,
        "complexity": cc,
        "deps": deps,
        "tests": tests,
    }

    # Write JSON
    json_path = REPORTS_DIR / "metrics.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    print(f"Metrics JSON written to {json_path}")

    # Generate HTML report
    html = generate_html_report(metrics, junit, coverage)

    html_path = REPORTS_DIR / "metrics.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML report written to {html_path}")

    # Write staging site
    staging_dir = REPORTS_DIR / "staging"
    staging_dir.mkdir(exist_ok=True)
    staging_path = staging_dir / "index.html"
    with open(staging_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Staging site written to {staging_path}")

    # Summary
    print("\n=== Summary ===")
    print(f"  LOC:          {loc['total_loc']:,} ({loc['python_loc']:,} Python)")
    print(f"  Source Files: {loc['total_files']} ({loc['python_files']} Python)")
    print(f"  Avg CC:       {cc['average']}")
    print(f"  Dependencies: {deps['total_dependencies']}")
    print(f"  Test Cases:   {tests['total']}")
    if junit["total"] > 0:
        print(
            f"  Tests:        {junit['passed']} passed / {junit['failed']} failed / {junit['total']} total"
        )
        print(f"  Duration:     {junit['time']:.1f}s")
    if coverage["lines_valid"] > 0:
        print(f"  Coverage:     {coverage['line_rate']*100:.1f}% ({coverage['lines_covered']}/{coverage['lines_valid']} lines)")


if __name__ == "__main__":
    main()
