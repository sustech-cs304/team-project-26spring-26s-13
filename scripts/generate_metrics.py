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

    skip_prefixes = (".git", ".pytest_cache", "__pycache__", "node_modules",
                     ".venv", "venv", "env", "data", "reports", ".mypy_cache")
    for root, _dirs, files in os.walk(str(PROJECT_ROOT)):
        # Skip hidden, virtual env, cache dirs
        rel = os.path.relpath(root, str(PROJECT_ROOT))
        parts = rel.replace("\\", "/").split("/")
        if any(p.startswith(sp) or p == sp for p in parts for sp in skip_prefixes):
            continue

        for f in files:
            if not f.endswith((".py", ".js", ".ts", ".html", ".css", ".sql", ".yml", ".yaml")):
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
    """Count project dependencies."""
    deps = set()
    for req_file in ("requirements.txt", "requirements-dev.txt"):
        fpath = PROJECT_ROOT / req_file
        if not fpath.exists():
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    pkg = line.split(">=")[0].split("==")[0].split("<")[0].split(";")[0].strip()
                    if pkg:
                        deps.add(pkg.lower())
    return {
        "total_dependencies": len(deps),
        "dependencies": sorted(deps),
    }


def compute_cyclomatic_complexity():
    """Compute cyclomatic complexity using lizard (if available), else flake8 radon."""
    result = {"average": 0.0, "total_functions": 0, "total_complexity": 0, "worst": []}
    try:
        output = subprocess.run(
            [sys.executable, "-m", "lizard", str(BACKEND_DIR)],
            capture_output=True, text=True, timeout=60, encoding="utf-8", errors="ignore",
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
                worst.append({"name": fn.get("name", ""), "file": fn.get("filename", ""), "cc": cc})
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
            capture_output=True, text=True, timeout=60, encoding="utf-8", errors="ignore",
            cwd=str(PROJECT_ROOT),
        )
        last_line = (output.stdout or "").strip().split("\n")[-1] if output.stdout else ""
        import re
        m = re.search(r"(\d+)\s+tests?\s+collected", last_line)
        if m:
            result["total"] = int(m.group(1))
    except Exception:
        pass
    return result


def generate_html_report(metrics):
    """Generate a standalone HTML report."""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Project Metrics Report — Student Productivity Agent</title>
<style>
body {{ font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; margin: 2rem auto; max-width: 900px; color: #333; }}
h1 {{ color: #1a5276; border-bottom: 2px solid #2980b9; padding-bottom: 0.5rem; }}
h2 {{ color: #2c3e50; margin-top: 2rem; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th, td {{ border: 1px solid #bdc3c7; padding: 8px 12px; text-align: left; }}
th {{ background: #2980b9; color: white; }}
tr:nth-child(even) {{ background: #ecf0f1; }}
.metric {{ font-size: 2rem; font-weight: bold; color: #2980b9; }}
.label {{ color: #7f8c8d; }}
.worst-cc {{ color: #e74c3c; }}
footer {{ margin-top: 3rem; font-size: 0.85rem; color: #95a5a6; text-align: center; }}
</style>
</head>
<body>
<h1>Project Metrics Report</h1>
<p><strong>Student Productivity Agent</strong> — Team 26s-13</p>
<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

<h2>1. Lines of Code</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Total LOC</td><td>{metrics['loc']['total_loc']:,}</td></tr>
<tr><td>Total Source Files</td><td>{metrics['loc']['total_files']}</td></tr>
<tr><td>Python LOC</td><td>{metrics['loc']['python_loc']:,}</td></tr>
<tr><td>Python Files</td><td>{metrics['loc']['python_files']}</td></tr>
</table>

<h3>LOC by Directory</h3>
<table>
<tr><th>Directory</th><th>LOC</th></tr>
"""
    for d, loc in sorted(metrics["loc"]["loc_by_directory"].items(), key=lambda x: -x[1]):
        html += f"<tr><td>{d}</td><td>{loc:,}</td></tr>\n"

    html += f"""
</table>

<h2>2. Cyclomatic Complexity</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Total Functions</td><td>{metrics['complexity']['total_functions']}</td></tr>
<tr><td>Total Complexity</td><td>{metrics['complexity']['total_complexity']}</td></tr>
<tr><td>Average Complexity</td><td>{metrics['complexity']['average']}</td></tr>
</table>
"""
    if metrics["complexity"].get("worst"):
        html += "<h3>Top 10 Most Complex Functions</h3><table>\n"
        html += "<tr><th>Function</th><th>CC</th></tr>\n"
        for fn in metrics["complexity"]["worst"]:
            cc_class = ' class="worst-cc"' if fn["cc"] > 15 else ""
            html += f'<tr><td>{fn["name"]}</td><td{cc_class}>{fn["cc"]}</td></tr>\n'
        html += "</table>\n"

    html += f"""
<h2>3. Dependencies</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Total Dependencies</td><td>{metrics['deps']['total_dependencies']}</td></tr>
</table>
<details><summary>Dependency List</summary>
<ul>
"""
    for d in metrics["deps"]["dependencies"]:
        html += f"<li>{d}</li>\n"

    html += f"""
</ul>
</details>

<h2>4. Test Suite</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Total Test Cases</td><td>{metrics['tests']['total']}</td></tr>
</table>

<footer>Generated by <code>scripts/generate_metrics.py</code></footer>
</body>
</html>
"""
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

    # Write HTML
    html_path = REPORTS_DIR / "metrics.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(generate_html_report(metrics))
    print(f"HTML report written to {html_path}")

    # Summary
    print("\n=== Summary ===")
    print(f"  LOC:          {loc['total_loc']:,} ({loc['python_loc']:,} Python)")
    print(f"  Source Files: {loc['total_files']} ({loc['python_files']} Python)")
    print(f"  Avg CC:       {cc['average']}")
    print(f"  Dependencies: {deps['total_dependencies']}")
    print(f"  Test Cases:   {tests['total']}")


if __name__ == "__main__":
    main()
