"""
Tests for study_copilot helper functions (pure, no LLM/DB).
"""

from backend.agent.tools.study_copilot import (
    _as_int,
    _coerce_subject_type,
    _meta_get,
    _normalize_file_ref,
    _pack_chunks,
)


class TestAsInt:
    def test_none(self):
        assert _as_int(None) == 0

    def test_int(self):
        assert _as_int(42) == 42

    def test_float(self):
        assert _as_int(3.7) == 3

    def test_string(self):
        assert _as_int("10") == 10

    def test_bool_ignored(self):
        assert _as_int(True) == 0

    def test_empty_string(self):
        assert _as_int("") == 0

    def test_invalid_string(self):
        assert _as_int("abc") == 0

    def test_default(self):
        assert _as_int(None, default=-1) == -1


class TestMetaGet:
    def test_dict_key(self):
        assert _meta_get({"a": 1}, "a") == 1

    def test_dict_missing(self):
        assert _meta_get({"a": 1}, "b") is None

    def test_non_dict(self):
        assert _meta_get("not a dict", "a") is None


class TestCoerceSubjectType:
    def test_valid(self):
        assert _coerce_subject_type("cs") == "cs"

    def test_uppercase(self):
        assert _coerce_subject_type("CS") == "cs"

    def test_invalid(self):
        assert _coerce_subject_type("foobar") == "other"

    def test_none(self):
        assert _coerce_subject_type(None) == "other"

    def test_empty(self):
        assert _coerce_subject_type("") == "other"


class TestNormalizeFileRef:
    def test_basic(self):
        assert _normalize_file_ref("lecture1.pdf") == "lecture1.pdf"

    def test_path_extracts_name(self):
        assert _normalize_file_ref("/some/path/to/file.txt") == "file.txt"

    def test_trailing_dots(self):
        assert _normalize_file_ref("lecture1.pdf...") == "lecture1.pdf"

    def test_empty(self):
        assert _normalize_file_ref("") == ""


class TestPackChunks:
    def test_single_chunk(self):
        chunks = [{"chunk_index": 0, "text": "hello"}]
        result = _pack_chunks(chunks, max_chars=1000)
        assert len(result) == 1
        assert "hello" in result[0]

    def test_empty(self):
        assert _pack_chunks([], max_chars=1000) == []

    def test_split_by_max_chars(self):
        chunks = [{"chunk_index": i, "text": "x" * 500} for i in range(5)]
        result = _pack_chunks(chunks, max_chars=600)
        assert len(result) >= 2
