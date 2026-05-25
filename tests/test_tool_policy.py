"""Tests for file-operation intent gating."""

from backend.agent.tool_policy import has_explicit_file_operation_intent


def test_generate_txt_triggers_file_tools() -> None:
    assert has_explicit_file_operation_intent("直接生成一个报告.txt 里面放123456")


def test_overwrite_without_filename_still_triggers_with_cover_action() -> None:
    assert has_explicit_file_operation_intent("覆盖里面的内容为456789")


def test_memory_request_not_file_operation() -> None:
    assert not has_explicit_file_operation_intent("请为我记忆：我 5 月 15 日去考 TOEFL")
