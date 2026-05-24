"""
Tests for document_parser pure functions.
"""

from backend.utils.document_parser import _normalize_text


class TestNormalizeText:
    def test_crlf_to_lf(self):
        assert _normalize_text("a\r\nb\r\n") == "a\nb"

    def test_carriage_return(self):
        assert _normalize_text("a\rb\r") == "a\nb"

    def test_trailing_whitespace_per_line(self):
        assert _normalize_text("hello   \nworld  ") == "hello\nworld"

    def test_collapse_blank_lines(self):
        assert _normalize_text("a\n\n\n\nb") == "a\n\nb"

    def test_strip_outer(self):
        assert _normalize_text("  hello  ") == "hello"

    def test_empty_string(self):
        assert _normalize_text("") == ""

    def test_none_like(self):
        assert _normalize_text(None) == ""  # type: ignore
