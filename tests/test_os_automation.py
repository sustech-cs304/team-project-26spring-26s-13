"""
Tests for OS automation path-safety utilities.
Only tests the pure functions (_safe_path, _rel) that don't need DB or HITL.
"""

import pytest
from pathlib import Path

from backend.agent.tools.os_automation import _safe_path, _rel


@pytest.fixture
def workspace(tmp_path):
    return tmp_path.resolve()


class TestSafePath:
    def test_normal_relative_path(self, workspace):
        result = _safe_path(workspace, "notes/hello.txt")
        assert result == workspace / "notes" / "hello.txt"

    def test_dot_path(self, workspace):
        result = _safe_path(workspace, ".")
        assert result == workspace

    def test_empty_path_raises(self, workspace):
        with pytest.raises(PermissionError, match="Empty path"):
            _safe_path(workspace, "")

    def test_traversal_attack_raises(self, workspace):
        with pytest.raises(PermissionError, match="outside"):
            _safe_path(workspace, "../../../etc/passwd")

    def test_absolute_path_inside_workspace(self, workspace):
        result = _safe_path(workspace, str(workspace / "safe.txt"))
        assert result.is_relative_to(workspace)

    def test_backslash_normalized(self, workspace):
        result = _safe_path(workspace, "sub\\dir\\file.txt")
        assert result == workspace / "sub" / "dir" / "file.txt"

    def test_leading_slash_stripped(self, workspace):
        result = _safe_path(workspace, "/etc/passwd")
        assert result == workspace / "etc" / "passwd"


class TestRelPath:
    def test_relative_display(self, workspace):
        target = workspace / "a" / "b.txt"
        assert _rel(workspace, target) == "a/b.txt"

    def test_workspace_root(self, workspace):
        assert _rel(workspace, workspace) == "."
