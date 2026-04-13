"""Preferred entrypoint for the desktop frontend on the main branch.

The current product UI lives in ``frontend.app``. The earlier module-oriented
``views/`` skeleton is still present in the repository for future refactors,
but this entrypoint now launches the working desktop application directly so
``python3 frontend/main.py`` is reliable for teammates.
"""

from frontend.app import main as run_desktop_frontend


def main() -> int:
    """Launch the working desktop frontend and return the Qt exit code."""
    return run_desktop_frontend()


if __name__ == "__main__":
    raise SystemExit(main())
