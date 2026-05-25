"""Tests for tool exposure policy (LLM-driven tool selection)."""

import pytest

from backend.agent.tool_policy import prepare_tools_for_prompt


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeCtx:
    prompt = "你好，今天天气怎么样"


@pytest.mark.asyncio
async def test_prepare_tools_always_exposes_file_tools() -> None:
    tool_defs = [
        _FakeTool("query_rag"),
        _FakeTool("file_create"),
        _FakeTool("file_update"),
    ]
    visible = await prepare_tools_for_prompt(_FakeCtx(), tool_defs)
    visible_names = {t.name for t in visible}
    assert visible_names == {"query_rag", "file_create", "file_update"}
    assert "file_create" in visible_names


@pytest.mark.asyncio
async def test_prepare_tools_does_not_filter_on_greeting() -> None:
    tool_defs = [_FakeTool(name) for name in ("save_personal_task", "file_delete")]
    visible = await prepare_tools_for_prompt(_FakeCtx(), tool_defs)
    assert len(visible) == 2
