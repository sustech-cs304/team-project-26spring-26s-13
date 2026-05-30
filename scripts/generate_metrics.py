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
    """Count lines of code and source files, with per-file breakdown."""
    total_loc = 0
    total_files = 0
    py_loc = 0
    py_files = 0
    by_dir = {}
    file_details = []

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
            top = parts[0] if parts and parts[0] != "." else "root"
            by_dir[top] = by_dir.get(top, 0) + loc
            file_details.append({"path": rel.replace("\\", "/") + "/" + f, "loc": loc})

    file_details.sort(key=lambda x: x["loc"], reverse=True)

    return {
        "total_loc": total_loc,
        "total_files": total_files,
        "python_loc": py_loc,
        "python_files": py_files,
        "loc_by_directory": by_dir,
        "top_files": file_details[:50],
    }


def count_dependencies():
    """Count project dependencies from installed packages and requirements files."""
    installed = {}
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
                pkg, ver = line.split("==", 1)
                pkg = pkg.strip()
                if pkg and not pkg.startswith("-"):
                    installed[pkg.lower()] = ver.strip()
    except Exception:
        pass

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
        "installed_packages": sorted(installed.keys()),
        "installed_with_versions": {k: installed[k] for k in sorted(installed.keys())},
    }


def compute_cyclomatic_complexity():
    """Compute cyclomatic complexity using lizard text output."""
    result = {
        "average": 0.0,
        "total_functions": 0,
        "total_complexity": 0,
        "worst": [],
        "distribution": {},
        "by_file": {},
        "all_functions": [],
    }
    try:
        output = subprocess.run(
            [sys.executable, "-m", "lizard", str(BACKEND_DIR), "-V"],
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            errors="ignore",
            cwd=str(PROJECT_ROOT),
        )
        if not output.stdout.strip():
            return result

        total_cc = 0
        all_functions = []
        by_file = {}

        # lizard -V verbose output format:
        #   NLOC  CCN  TokenCount  ParamCount  Length  function_name@line-range@file_path
        for line in output.stdout.strip().split("\n"):
            if line.startswith("=") or line.startswith("-") or "NLOC" in line:
                continue
            parts = line.split()
            if len(parts) < 6:
                continue
            try:
                nloc = int(parts[0])
                cc_val = int(parts[1])
                token_count = int(parts[2])
                param_count = int(parts[3])
                length = int(parts[4])
            except (ValueError, IndexError):
                continue

            # Everything after length is the function identifier
            fn_info_raw = " ".join(parts[5:])

            # Parse: function_name@start_line-end_line@file_path
            name = fn_info_raw
            start_line = 0
            short_file = ""

            if "@" in fn_info_raw:
                segments = fn_info_raw.split("@")
                name = segments[0]
                if len(segments) >= 2:
                    line_range = segments[1].split("-")
                    try:
                        start_line = int(line_range[0])
                    except ValueError:
                        pass
                if len(segments) >= 3:
                    raw_path = segments[2]
                    try:
                        short_file = os.path.relpath(
                            raw_path, str(PROJECT_ROOT)
                        ).replace("\\", "/")
                    except ValueError:
                        short_file = raw_path.replace("\\", "/")

            total_cc += cc_val
            func_info = {
                "name": name,
                "file": short_file,
                "line": start_line,
                "cc": cc_val,
                "nloc": nloc,
                "token_count": token_count,
                "params": param_count,
            }
            all_functions.append(func_info)

            if short_file and short_file not in by_file:
                by_file[short_file] = {
                    "functions": 0,
                    "total_cc": 0,
                    "max_cc": 0,
                    "total_nloc": 0,
                    "function_list": [],
                }
            if short_file:
                by_file[short_file]["functions"] += 1
                by_file[short_file]["total_cc"] += cc_val
                by_file[short_file]["max_cc"] = max(
                    by_file[short_file]["max_cc"], cc_val
                )
                by_file[short_file]["total_nloc"] += nloc
                by_file[short_file]["function_list"].append(func_info)

        # CC distribution buckets
        buckets = {
            "1-5 Simple": 0,
            "6-10 Moderate": 0,
            "11-20 Complex": 0,
            "21-50 High": 0,
            "51+ Critical": 0,
        }
        for f in all_functions:
            c = f["cc"]
            if c <= 5:
                buckets["1-5 Simple"] += 1
            elif c <= 10:
                buckets["6-10 Moderate"] += 1
            elif c <= 20:
                buckets["11-20 Complex"] += 1
            elif c <= 50:
                buckets["21-50 High"] += 1
            else:
                buckets["51+ Critical"] += 1

        all_functions.sort(key=lambda x: x["cc"], reverse=True)

        result["total_functions"] = len(all_functions)
        result["total_complexity"] = total_cc
        result["average"] = round(total_cc / max(len(all_functions), 1), 2)
        result["worst"] = all_functions[:30]
        result["distribution"] = buckets
        result["by_file"] = by_file
        result["all_functions"] = all_functions
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
            result["packages"].append({"name": name, "rate": rate, "classes": classes})
    except Exception:
        pass
    return result


def _cc_color(cc):
    if cc <= 10:
        return "#27ae60"
    if cc <= 20:
        return "#f39c12"
    return "#e74c3c"


def _cc_level_color(level):
    return {
        "1-5 Simple": "#27ae60",
        "6-10 Moderate": "#2ecc71",
        "11-20 Complex": "#f39c12",
        "21-50 High": "#e67e22",
        "51+ Critical": "#e74c3c",
    }.get(level, "#95a5a6")


def _rate_color(pct):
    if pct >= 80:
        return "#27ae60"
    if pct >= 60:
        return "#2ecc71"
    if pct >= 40:
        return "#f39c12"
    return "#e74c3c"


CSS = """
:root {
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
}
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
       background:var(--gray-50); color:var(--gray-900); line-height:1.6; }

.header { background:linear-gradient(135deg,#1e3a5f,#2563eb,#3b82f6); color:#fff; padding:2.5rem 0; position:relative; overflow:hidden; }
.header::before { content:''; position:absolute; top:0; left:0; right:0; bottom:0; background:url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.05'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E"); }
.header-inner { max-width:1200px; margin:0 auto; padding:0 2rem; position:relative; z-index:1; }
.header h1 { font-size:1.75rem; font-weight:700; letter-spacing:-0.02em; }
.header .subtitle { opacity:.9; font-size:1rem; margin-top:.3rem; }
.header .meta { display:flex; gap:2rem; margin-top:.75rem; font-size:.85rem; opacity:.75; }

.nav { background:#fff; border-bottom:1px solid var(--gray-200); position:sticky; top:0; z-index:100; box-shadow:var(--shadow); }
.nav-inner { max-width:1200px; margin:0 auto; padding:0 2rem; display:flex; gap:0; }
.nav-tab { padding:.75rem 1.25rem; font-size:.9rem; font-weight:500; color:var(--gray-500);
            cursor:pointer; border-bottom:2px solid transparent; transition:all .2s; user-select:none; }
.nav-tab:hover { color:var(--primary); background:var(--gray-50); }
.nav-tab.active { color:var(--primary); border-bottom-color:var(--primary); font-weight:600; }

.content { max-width:1200px; margin:0 auto; padding:2rem; }
.section { display:none; }
.section.active { display:block; }

.dashboard { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:1rem; margin-bottom:2rem; }
.card { background:#fff; border-radius:var(--radius); padding:1.25rem; box-shadow:var(--shadow); transition:all .25s; border-left:3px solid var(--primary); }
.card:hover { box-shadow:var(--shadow-md); transform:translateY(-2px); }
.card-icon { font-size:1.5rem; margin-bottom:.35rem; }
.card-value { font-size:1.75rem; font-weight:700; color:var(--primary); }
.card-label { font-size:.8rem; color:var(--gray-500); margin-top:.15rem; }

.panel { background:#fff; border-radius:var(--radius); box-shadow:var(--shadow); margin-bottom:1.5rem; overflow:hidden; }
.panel-header { padding:1rem 1.5rem; border-bottom:1px solid var(--gray-200); font-weight:600; font-size:1rem; display:flex; align-items:center; justify-content:space-between; background:var(--gray-50); }
.panel-body { padding:1.5rem; }

table { width:100%; border-collapse:collapse; }
th,td { text-align:left; padding:.6rem .75rem; }
th { background:var(--gray-50); font-weight:600; font-size:.75rem; text-transform:uppercase;
      letter-spacing:.05em; color:var(--gray-500); border-bottom:2px solid var(--gray-200); position:sticky; top:0; }
td { border-bottom:1px solid var(--gray-100); font-size:.85rem; }
tr:hover td { background:var(--primary-light); }

.bar-row { display:flex; align-items:center; margin-bottom:.5rem; }
.bar-label { width:140px; font-size:.8rem; font-weight:500; color:var(--gray-700); flex-shrink:0; }
.bar-track { flex:1; height:22px; background:var(--gray-100); border-radius:4px; overflow:hidden; margin:0 .75rem; }
.bar-fill { height:100%; border-radius:4px; transition:width .8s ease; }
.bar-value { width:70px; text-align:right; font-size:.8rem; font-weight:600; color:var(--gray-700); }

.cc-badge { display:inline-block; padding:.1rem .5rem; border-radius:12px; color:#fff; font-weight:700; font-size:.75rem; min-width:32px; text-align:center; }
.mini-bar-track { width:100%; height:8px; background:var(--gray-100); border-radius:4px; overflow:hidden; }
.mini-bar-fill { height:100%; border-radius:4px; transition:width .6s ease; }
.fn-name { font-size:.82rem; color:var(--primary); word-break:break-all; }
.fn-file { font-size:.72rem; color:var(--gray-500); }

.dep-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:1rem; }
.dep-card { background:var(--gray-50); border-radius:var(--radius); padding:1rem 1.25rem; }
.dep-card-title { font-weight:600; font-size:.85rem; color:var(--gray-700); }
.dep-card-count { font-size:1.4rem; font-weight:700; color:var(--primary); margin:.2rem 0; }
.dep-card-list { display:flex; flex-wrap:wrap; gap:.3rem; }
.dep-tag { display:inline-block; font-size:.68rem; padding:.1rem .45rem; border-radius:4px;
            border:1px solid var(--gray-300); background:#fff; color:var(--gray-700); }

.summary-row { display:flex; gap:2rem; flex-wrap:wrap; }
.summary-item { text-align:center; }
.summary-item .num { font-size:2.2rem; font-weight:800; color:var(--primary); }
.summary-item .lbl { font-size:.75rem; color:var(--gray-500); text-transform:uppercase; letter-spacing:.05em; }

.search-box { width:100%; padding:.5rem .75rem; border:1px solid var(--gray-300); border-radius:var(--radius);
              font-size:.85rem; margin-bottom:1rem; outline:none; transition:border .2s; }
.search-box:focus { border-color:var(--primary); box-shadow:0 0 0 3px var(--primary-light); }

.scroll-table { max-height:500px; overflow-y:auto; }

.footer { text-align:center; padding:2rem; font-size:.8rem; color:var(--gray-500); border-top:1px solid var(--gray-200); margin-top:2rem; }

.dual-col { display:grid; grid-template-columns:1fr 1fr; gap:1.5rem; }

@media(max-width:768px) {
  .dashboard { grid-template-columns:1fr 1fr; }
  .dep-grid { grid-template-columns:1fr; }
  .bar-label { width:80px; }
  .dual-col { grid-template-columns:1fr; }
}
"""


def generate_html_report(metrics, junit, coverage):
    """Generate a professional HTML report with comprehensive detail."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    loc = metrics["loc"]
    cc = metrics["complexity"]
    deps = metrics["deps"]
    tests = metrics["tests"]

    cov_pct = f"{coverage['line_rate'] * 100:.1f}"
    cov_color = _rate_color(float(cov_pct))

    # ── LOC bars ──
    loc_dirs = sorted(loc["loc_by_directory"].items(), key=lambda x: -x[1])
    max_loc = max(v for _, v in loc_dirs) if loc_dirs else 1
    loc_bars = ""
    for d, v in loc_dirs:
        pct = int(v / max_loc * 100)
        loc_bars += f"""
        <div class="bar-row">
          <span class="bar-label">{d}</span>
          <div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:linear-gradient(90deg,var(--primary),#60a5fa)"></div></div>
          <span class="bar-value">{v:,}</span>
        </div>"""

    # ── Top files table ──
    top_files_rows = ""
    for i, f in enumerate(loc.get("top_files", [])[:30]):
        top_files_rows += f"""
        <tr>
          <td>{i+1}</td>
          <td><code class="fn-name">{f['path']}</code></td>
          <td style="font-weight:600">{f['loc']:,}</td>
          <td><div class="mini-bar-track" style="max-width:200px"><div class="mini-bar-fill" style="width:{int(f['loc']/max_loc*100)}%;background:var(--primary)"></div></div></td>
        </tr>"""

    # ── CC distribution bars ──
    dist = cc.get("distribution", {})
    max_dist = max(dist.values()) if dist else 1
    dist_bars = ""
    for level in [
        "1-5 Simple",
        "6-10 Moderate",
        "11-20 Complex",
        "21-50 High",
        "51+ Critical",
    ]:
        count = dist.get(level, 0)
        if max_dist == 0:
            pct = 0
        else:
            pct = int(count / max_dist * 100)
        col = _cc_level_color(level)
        dist_bars += f"""
        <div class="bar-row">
          <span class="bar-label">{level}</span>
          <div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:{col}"></div></div>
          <span class="bar-value" style="font-weight:700">{count}</span>
        </div>"""

    # ── Per-file CC summary ──
    by_file_cc = cc.get("by_file", {})
    cc_file_rows = ""
    for fpath, info in sorted(by_file_cc.items(), key=lambda x: -x[1]["max_cc"]):
        avg = round(info["total_cc"] / max(info["functions"], 1), 1)
        max_cc = info["max_cc"]
        col = _cc_color(max_cc)
        cc_file_rows += f"""
        <tr>
          <td><code class="fn-name">{fpath}</code></td>
          <td style="text-align:center">{info['functions']}</td>
          <td style="text-align:center">{info['total_nloc']:,}</td>
          <td style="text-align:center;font-weight:600">{avg}</td>
          <td class="cc-cell"><span class="cc-badge" style="background:{col}">{max_cc}</span></td>
          <td><div class="mini-bar-track" style="max-width:100px"><div class="mini-bar-fill" style="width:{min(int(avg/15*100),100)}%;background:{col}"></div></div></td>
        </tr>"""

    # ── All functions CC table ──
    all_fn_rows = ""
    for i, fn in enumerate(cc.get("all_functions", [])):
        col = _cc_color(fn["cc"])
        all_fn_rows += f"""
        <tr>
          <td>{i+1}</td>
          <td><code class="fn-name">{fn['name']}</code><br><span class="fn-file">{fn['file']}:{fn['line']}</span></td>
          <td class="cc-cell"><span class="cc-badge" style="background:{col}">{fn['cc']}</span></td>
          <td style="text-align:center">{fn['nloc']}</td>
          <td><div class="mini-bar-track" style="max-width:120px"><div class="mini-bar-fill" style="width:{min(int(fn['cc']/120*100),100)}%;background:{col}"></div></div></td>
        </tr>"""

    # ── Dependency categories ──
    dep_categories = {
        "Backend Framework": [
            "fastapi",
            "uvicorn[standard]",
            "pydantic",
            "pydantic-settings",
            "pydantic-ai",
        ],
        "Database": ["sqlalchemy", "asyncpg", "alembic", "chromadb", "aiosqlite"],
        "Document Parsing": [
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
        "Observability": [
            "logfire",
            "opentelemetry-api",
            "opentelemetry-sdk",
            "opentelemetry-proto",
        ],
        "Other": ["python-multipart", "aioresponses", "responses", "python-dotenv"],
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
        "#8b5cf6",
        "#95a5a6",
    ]
    for i, (cat, pkgs) in enumerate(dep_categories.items()):
        col = colors[i % len(colors)]
        badges = " ".join(
            f'<span class="dep-tag" style="border-color:{col}">{p}</span>' for p in pkgs
        )
        dep_grid += f"""
        <div class="dep-card" style="border-top:3px solid {col}">
          <div class="dep-card-title">{cat}</div>
          <div class="dep-card-count">{len(pkgs)}</div>
          <div class="dep-card-list">{badges}</div>
        </div>"""

    # ── Test file rows ──
    test_file_rows = ""
    for f, d in sorted(junit.get("by_file", {}).items()):
        status_badge = (
            '<span class="cc-badge" style="background:var(--success)">PASS</span>'
            if d["failed"] + d["errors"] == 0
            else '<span class="cc-badge" style="background:var(--danger)">FAIL</span>'
        )
        test_file_rows += f"""
        <tr>
          <td><code>{f.replace('tests/', '')}</code></td>
          <td style="text-align:center">{d['total']}</td>
          <td style="color:var(--success);font-weight:600;text-align:center">{d['passed']}</td>
          <td style="color:var(--danger);font-weight:600;text-align:center">{d['failed'] + d['errors']}</td>
          <td style="text-align:center">{d['time']:.2f}s</td>
          <td>{status_badge}</td>
        </tr>"""

    # ── All test case rows ──
    all_tc_rows = ""
    idx = 0
    for f, d in sorted(junit.get("by_file", {}).items()):
        for c in d.get("cases", []):
            idx += 1
            icon = (
                '<span style="color:var(--success)">&#10003;</span>'
                if c["status"] == "passed"
                else '<span style="color:var(--danger)">&#10007;</span>'
            )
            all_tc_rows += f"""
          <tr>
            <td>{idx}</td>
            <td><code class="fn-name">{c['name']}</code><br><span class="fn-file">{f.replace('tests/', '')}</span></td>
            <td style="text-align:center">{c['time']:.3f}s</td>
            <td style="text-align:center">{icon}</td>
          </tr>"""

    # ── Coverage package rows ──
    cov_pkg_rows = ""
    for p in coverage.get("packages", []):
        pct = p["rate"] * 100
        col = _rate_color(pct)
        cov_pkg_rows += f"""
        <tr>
          <td><code>{p['name'] or '.'}</code></td>
          <td style="font-weight:600;color:{col};width:80px">{pct:.1f}%</td>
          <td><div class="mini-bar-track" style="max-width:300px"><div class="mini-bar-fill" style="width:{pct:.1f}%;background:{col}"></div></div></td>
        </tr>"""

    # ── Coverage module rows (all, sorted by rate) ──
    all_modules = sorted(
        [c for p in coverage.get("packages", []) for c in p.get("classes", [])],
        key=lambda x: x["rate"],
    )
    cov_mod_rows = ""
    for c in all_modules:
        pct = c["rate"] * 100
        col = _rate_color(pct)
        cov_mod_rows += f"""
        <tr>
          <td><code class="fn-name">{c['name']}</code></td>
          <td style="font-weight:600;color:{col};width:80px">{pct:.1f}%</td>
          <td><div class="mini-bar-track" style="max-width:250px"><div class="mini-bar-fill" style="width:{max(pct,1):.1f}%;background:{col}"></div></div></td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Project Metrics &mdash; Student Productivity Agent</title>
<style>{CSS}</style>
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
    <div class="card">
      <div class="card-icon">&#128202;</div>
      <div class="card-value">{cov_pct}%</div>
      <div class="card-label">Line Coverage</div>
    </div>
    <div class="card">
      <div class="card-icon">&#9203;</div>
      <div class="card-value">{junit['time']:.1f}s</div>
      <div class="card-label">Test Duration</div>
    </div>
  </div>

  <div class="dual-col">
    <div class="panel">
      <div class="panel-header">LOC by Directory</div>
      <div class="panel-body">{loc_bars}</div>
    </div>
    <div class="panel">
      <div class="panel-header">CC Distribution</div>
      <div class="panel-body">{dist_bars}</div>
    </div>
  </div>
</div>

<!-- ════ LOC ════ -->
<div class="section" id="tab-loc">
  <div class="dashboard">
    <div class="card">
      <div class="card-value">{loc['total_loc']:,}</div>
      <div class="card-label">Total LOC</div>
    </div>
    <div class="card">
      <div class="card-value">{loc['python_loc']:,}</div>
      <div class="card-label">Python LOC</div>
    </div>
    <div class="card">
      <div class="card-value">{loc['total_files']}</div>
      <div class="card-label">Total Files</div>
    </div>
    <div class="card">
      <div class="card-value">{loc['python_files']}</div>
      <div class="card-label">Python Files</div>
    </div>
  </div>
  <div class="panel">
    <div class="panel-header">Breakdown by Directory</div>
    <div class="panel-body">{loc_bars}</div>
  </div>
  <div class="panel">
    <div class="panel-header">Top 30 Files by LOC <span style="font-weight:400;font-size:.8rem;color:var(--gray-500)">(of {loc['total_files']} total)</span></div>
    <div class="panel-body scroll-table">
      <table>
        <tr><th style="width:40px">#</th><th>File</th><th style="width:70px">LOC</th><th>Relative</th></tr>
        {top_files_rows}
      </table>
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

  <div class="dual-col">
    <div class="panel">
      <div class="panel-header">CC Distribution</div>
      <div class="panel-body">{dist_bars}</div>
    </div>
    <div class="panel">
      <div class="panel-header">CC Legend</div>
      <div class="panel-body">
        <table>
          <tr><th style="width:60px">Range</th><th>Risk</th><th style="width:60px">Count</th></tr>
          <tr><td><span class="cc-badge" style="background:#27ae60">1-5</span></td><td>Simple &mdash; easy to test</td><td style="font-weight:600">{dist.get('1-5 Simple',0)}</td></tr>
          <tr><td><span class="cc-badge" style="background:#2ecc71">6-10</span></td><td>Moderate &mdash; manageable</td><td style="font-weight:600">{dist.get('6-10 Moderate',0)}</td></tr>
          <tr><td><span class="cc-badge" style="background:#f39c12">11-20</span></td><td>Complex &mdash; needs review</td><td style="font-weight:600">{dist.get('11-20 Complex',0)}</td></tr>
          <tr><td><span class="cc-badge" style="background:#e67e22">21-50</span></td><td>High risk &mdash; refactor recommended</td><td style="font-weight:600">{dist.get('21-50 High',0)}</td></tr>
          <tr><td><span class="cc-badge" style="background:#e74c3c">51+</span></td><td>Critical &mdash; untestable, must refactor</td><td style="font-weight:600">{dist.get('51+ Critical',0)}</td></tr>
        </table>
      </div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header">Complexity by File <span style="font-weight:400;font-size:.8rem;color:var(--gray-500)">({len(by_file_cc)} files)</span></div>
    <div class="panel-body scroll-table">
      <table>
        <tr><th>File</th><th style="width:70px">Funcs</th><th style="width:70px">NLOC</th><th style="width:70px">Avg CC</th><th style="width:70px">Max CC</th><th>Bar</th></tr>
        {cc_file_rows}
      </table>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header">All Functions by CC <span style="font-weight:400;font-size:.8rem;color:var(--gray-500)">({cc['total_functions']} total, sorted descending)</span></div>
    <div class="panel-body">
      <input class="search-box" id="fnSearch" type="text" placeholder="Search function name or file...">
      <div class="scroll-table" style="max-height:600px">
        <table id="fnTable">
          <tr><th style="width:40px">#</th><th>Function</th><th style="width:60px">CC</th><th style="width:60px">NLOC</th><th>Relative</th></tr>
          {all_fn_rows}
        </table>
      </div>
    </div>
  </div>
</div>

<!-- ════ Dependencies ════ -->
<div class="section" id="tab-deps">
  <div class="summary-row" style="margin-bottom:1.5rem">
    <div class="summary-item"><div class="num">{deps['total_dependencies']}</div><div class="lbl">Direct Dependencies</div></div>
    <div class="summary-item"><div class="num">{deps['total_installed']}</div><div class="lbl">Installed Packages</div></div>
  </div>
  <div class="panel">
    <div class="panel-header">By Category</div>
    <div class="panel-body">
      <div class="dep-grid">{dep_grid}</div>
    </div>
  </div>
  <div class="panel">
    <div class="panel-header">Full Dependency List</div>
    <div class="panel-body" style="columns:2">{"".join(f'<span class="dep-tag" style="margin-bottom:.3rem;display:inline-block">{d}</span> ' for d in deps['dependencies'])}</div>
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
    <div class="card" style="border-left-color:var(--success)">
      <div class="card-icon">&#128994;</div>
      <div class="card-value" style="color:var(--success)">{junit['passed']}</div>
      <div class="card-label">Passed</div>
    </div>
    <div class="card" style="border-left-color:var(--danger)">
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
        <tr><th>Test File</th><th style="width:60px">Total</th><th style="width:60px">Passed</th><th style="width:60px">Failed</th><th style="width:70px">Time</th><th style="width:70px">Status</th></tr>
        {test_file_rows}
      </table>
    </div>
  </div>
  <div class="panel">
    <div class="panel-header">All Test Cases <span style="font-weight:400;font-size:.8rem;color:var(--gray-500)">{junit['total']} total</span></div>
    <div class="panel-body">
      <input class="search-box" id="tcSearch" type="text" placeholder="Search test name...">
      <div class="scroll-table" style="max-height:600px">
        <table id="tcTable">
          <tr><th style="width:40px">#</th><th>Test</th><th style="width:80px">Time</th><th style="width:60px">Status</th></tr>
          {all_tc_rows}
        </table>
      </div>
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
      <div class="card-value">{coverage['lines_covered']:,}</div>
      <div class="card-label">Lines Covered</div>
    </div>
    <div class="card">
      <div class="card-value">{coverage['lines_valid']:,}</div>
      <div class="card-label">Total Lines</div>
    </div>
  </div>
  <div class="dual-col">
    <div class="panel">
      <div class="panel-header">Coverage Gauge</div>
      <div class="panel-body" style="text-align:center;padding:1.5rem">
        <div style="position:relative;width:160px;height:160px;margin:0 auto">
          <svg viewBox="0 0 36 36" style="width:100%;height:100%;transform:rotate(-90deg)">
            <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="var(--gray-200)" stroke-width="3"/>
            <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="{cov_color}" stroke-width="3" stroke-dasharray="{cov_pct}, 100" stroke-linecap="round"/>
          </svg>
          <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:1.8rem;font-weight:800;color:{cov_color}">{cov_pct}%</div>
        </div>
        <p style="margin-top:.75rem;color:var(--gray-500);font-size:.85rem">{coverage['lines_covered']:,} / {coverage['lines_valid']:,} lines covered</p>
      </div>
    </div>
    <div class="panel">
      <div class="panel-header">Coverage by Package</div>
      <div class="panel-body scroll-table" style="max-height:250px">
        <table>
          <tr><th>Package</th><th style="width:70px">Rate</th><th>Bar</th></tr>
          {cov_pkg_rows}
        </table>
      </div>
    </div>
  </div>
  <div class="panel">
    <div class="panel-header">Coverage by Module <span style="font-weight:400;font-size:.8rem;color:var(--gray-500)">({len(all_modules)} modules, sorted ascending)</span></div>
    <div class="panel-body">
      <input class="search-box" id="covSearch" type="text" placeholder="Search module name...">
      <div class="scroll-table" style="max-height:600px">
        <table id="covTable">
          <tr><th>Module</th><th style="width:70px">Rate</th><th>Bar</th></tr>
          {cov_mod_rows}
        </table>
      </div>
    </div>
  </div>
</div>

</div><!-- /.content -->

<div class="footer">
  Generated by <code>scripts/generate_metrics.py</code> &bull; {ts}
</div>

<script>
// Tab switching
document.querySelectorAll('.nav-tab').forEach(function(tab) {{
  tab.addEventListener('click', function() {{
    document.querySelectorAll('.nav-tab').forEach(function(t) {{ t.classList.remove('active'); }});
    document.querySelectorAll('.section').forEach(function(s) {{ s.classList.remove('active'); }});
    tab.classList.add('active');
    document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
  }});
}});

// Search filter
function setupSearch(inputId, tableId) {{
  var input = document.getElementById(inputId);
  var table = document.getElementById(tableId);
  if (!input || !table) return;
  input.addEventListener('input', function() {{
    var q = this.value.toLowerCase();
    var rows = table.querySelectorAll('tr');
    for (var i = 1; i < rows.length; i++) {{
      rows[i].style.display = rows[i].textContent.toLowerCase().indexOf(q) >= 0 ? '' : 'none';
    }}
  }});
}}
setupSearch('fnSearch', 'fnTable');
setupSearch('tcSearch', 'tcTable');
setupSearch('covSearch', 'covTable');
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

    print("Parsing test results...")
    junit = parse_junit_xml()

    print("Counting test cases...")
    tests = count_test_cases()
    if tests["total"] == 0 and junit["total"] > 0:
        tests["total"] = junit["total"]

    print("Parsing coverage data...")
    coverage = parse_coverage_xml()

    metrics = {
        "timestamp": datetime.now().isoformat(),
        "loc": loc,
        "complexity": cc,
        "deps": deps,
        "tests": tests,
    }

    json_path = REPORTS_DIR / "metrics.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    print(f"Metrics JSON written to {json_path}")

    html = generate_html_report(metrics, junit, coverage)

    html_path = REPORTS_DIR / "metrics.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML report written to {html_path}")

    staging_dir = REPORTS_DIR / "staging"
    staging_dir.mkdir(exist_ok=True)
    staging_path = staging_dir / "index.html"
    with open(staging_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Staging site written to {staging_path}")

    # Also write as reports/index.html for convenience
    index_path = REPORTS_DIR / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)

    print("\n=== Summary ===")
    print(f"  LOC:          {loc['total_loc']:,} ({loc['python_loc']:,} Python)")
    print(f"  Source Files: {loc['total_files']} ({loc['python_files']} Python)")
    print(f"  Functions:    {cc['total_functions']} (avg CC: {cc['average']})")
    print(f"  Dependencies: {deps['total_dependencies']}")
    print(f"  Test Cases:   {tests['total']}")
    if junit["total"] > 0:
        print(
            f"  Tests:        {junit['passed']} passed / {junit['failed']} failed / {junit['total']} total"
        )
        print(f"  Duration:     {junit['time']:.1f}s")
    if coverage["lines_valid"] > 0:
        print(
            f"  Coverage:     {coverage['line_rate']*100:.1f}% ({coverage['lines_covered']}/{coverage['lines_valid']} lines)"
        )


if __name__ == "__main__":
    main()
