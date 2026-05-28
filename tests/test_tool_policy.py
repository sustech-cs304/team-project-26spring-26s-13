"""Tests for tool exposure policy (LLM-driven tool selection)."""

import asyncio

from backend.agent.tool_policy import prepare_tools_for_prompt


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeGreetingCtx:
    prompt = "你好，今天天气怎么样"


class _FakeFileCtx:
    prompt = "读取本地 notes.txt"


class _FakeLibraryCtx:
    prompt = "帮我查看一丹图书馆311讨论间今天的预约情况"


def test_prepare_tools_always_exposes_file_tools() -> None:
    tool_defs = [
        _FakeTool("query_rag"),
        _FakeTool("file_create"),
        _FakeTool("file_update"),
    ]
    visible = asyncio.run(prepare_tools_for_prompt(_FakeFileCtx(), tool_defs))
    visible_names = {t.name for t in visible}
    assert visible_names == {"query_rag", "file_create", "file_update"}
    assert "file_create" in visible_names


def test_prepare_tools_filters_file_tools_on_greeting() -> None:
    tool_defs = [_FakeTool(name) for name in ("save_personal_task", "file_delete")]
    visible = asyncio.run(prepare_tools_for_prompt(_FakeGreetingCtx(), tool_defs))
    assert len(visible) == 1
    assert visible[0].name == "save_personal_task"


def test_prepare_tools_keeps_only_library_lookup_for_library_query() -> None:
    tool_defs = [
        _FakeTool("query_rag"),
        _FakeTool("get_current_time"),
        _FakeTool("fetch_blackboard_deadlines"),
        _FakeTool("query_library_rooms"),
        _FakeTool("book_library_room"),
    ]

    visible = asyncio.run(prepare_tools_for_prompt(_FakeLibraryCtx(), tool_defs))

    assert [tool.name for tool in visible] == ["query_library_rooms"]
