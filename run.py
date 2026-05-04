import subprocess
import sys
import os
import time
import argparse


def run_services():
    """Start the backend and frontend processes concurrently."""
    print("Starting backend service...")

    # Start backend
    backend_process = subprocess.Popen(
        [sys.executable, "-m", "backend.main"],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    # Wait a bit for backend to initialize
    time.sleep(2)

    print("Starting frontend service...")

    # Set environment variable for frontend
    env = os.environ.copy()
    env["SPA_API_BASE_URL"] = "http://127.0.0.1:8000"

    # Start frontend
    frontend_process = subprocess.Popen(
        [sys.executable, "frontend/app.py"],
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    try:
        # Wait for processes to complete
        backend_process.wait()
        frontend_process.wait()
    except KeyboardInterrupt:
        print("\n[INFO] Keyboard interrupt received. Shutting down services...")
        backend_process.terminate()
        frontend_process.terminate()
        backend_process.wait()
        frontend_process.wait()
        print("[INFO] Services stopped.")


def format_code():
    """Run black formatter on the codebase."""
    print("Running black formatter...")
    subprocess.run([sys.executable, "-m", "black", "."])


def lint_code():
    """Run flake8 linter on the codebase."""
    print("Running flake8 linter...")
    subprocess.run([sys.executable, "-m", "flake8", "."])


def test_code():
    """Run pytest."""
    print("Running tests...")
    subprocess.run([sys.executable, "-m", "pytest", "tests/"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automation script for the project.")
    parser.add_argument(
        "action",
        nargs="?",
        default="run",
        choices=["run", "format", "lint", "test"],
        help="Action to perform. Default is 'run' (start services).",
    )

    args = parser.parse_args()

    if args.action == "run":
        run_services()
    elif args.action == "format":
        format_code()
    elif args.action == "lint":
        lint_code()
    elif args.action == "test":
        test_code()
