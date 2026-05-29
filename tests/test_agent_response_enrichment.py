"""
Tests for backend-side Agent response enrichment.

These tests avoid real LLM calls and focus on the deterministic post-processing
that turns tool observations into cited answers and UI payloads.
"""

import json

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)

from backend.agent.core import FinalResponse
from backend.agent.loop import (
    _build_encyclopedia_payload,
    _build_llm_user_prompt,
    _build_trace,
    _build_schedule_data_from_tool_returns,
    _ensure_source_citations,
)


def _tool_return(tool_name: str, content: str) -> ModelRequest:
    return ModelRequest(
        parts=[
            ToolReturnPart(
                tool_name=tool_name, content=content, tool_call_id=f"tc_{tool_name}"
            )
        ]
    )


def test_ensure_source_citations_appends_rag_sources_to_final_answer():
    raw_messages = [
        _tool_return(
            "query_rag",
            json.dumps(
                {
                    "chunks": [
                        {
                            "text": "Minor requirements require enough credits.",
                            "file_name": "Student Handbook / Degree Requirements",
                            "subject_type": "policy",
                            "distance": 0.12,
                        },
                        {
                            "text": "Duplicate source chunk.",
                            "file_name": "Student Handbook / Degree Requirements",
                            "subject_type": "policy",
                            "distance": 0.18,
                        },
                    ],
                    "collections_queried": ["policy", "other"],
                }
            ),
        )
    ]

    enriched = _ensure_source_citations(
        FinalResponse(content="需要满足手册规定的学分要求。", route="encyclopedia"),
        raw_messages,
    )

    assert "来源" in enriched.content
    assert "Student Handbook / Degree Requirements" in enriched.content
    assert enriched.content.count("Student Handbook / Degree Requirements") == 1


def test_build_encyclopedia_payload_uses_cited_final_answer():
    raw_messages = [
        _tool_return(
            "query_rag",
            json.dumps(
                {
                    "chunks": [
                        {
                            "text": "Policy text",
                            "file_name": "Dorm Change Policy.pdf",
                            "subject_type": "policy",
                            "distance": 0.1,
                        }
                    ],
                    "collections_queried": ["policy"],
                }
            ),
        )
    ]

    payload = _build_encyclopedia_payload(
        "换宿舍截止时间是什么？",
        "答案正文\n\n来源：\n1. Dorm Change Policy.pdf",
        raw_messages,
    )

    assert payload is not None
    assert payload.query == "换宿舍截止时间是什么？"
    assert payload.citations == ["Dorm Change Policy.pdf"]
    assert "Dorm Change Policy.pdf" in payload.answer_markdown


def test_build_schedule_data_prefers_proactive_schedule_context():
    proactive_context = {
        "planning_window_days": 14,
        "events": [
            {
                "event_id": "bb:1",
                "title": "OOAD Report",
                "time": "2026-05-12T23:59:00+08:00",
                "source": "Blackboard",
                "detail": "course_id=CS304",
            },
            {
                "event_id": "todo:1",
                "title": "Project meeting",
                "time": "2026-05-12T22:00:00+08:00~2026-05-12T23:30:00+08:00",
                "source": "Local TODO",
                "detail": "location=Library",
            },
        ],
        "conflicts": [
            {
                "title": "OOAD Report",
                "detail": "deadline_inside_event=Project meeting",
            }
        ],
        "proactive_notes": ["检测到 1 个潜在时间冲突，优先处理冲突项。"],
        "sources": ["Blackboard", "Local TODO"],
    }
    raw_messages = [
        _tool_return(
            "build_proactive_schedule_context",
            json.dumps(proactive_context, ensure_ascii=False),
        )
    ]

    schedule = _build_schedule_data_from_tool_returns(
        "我压力很大，帮我规划一下期末周",
        raw_messages,
        blackboard_result=None,
    )

    assert schedule is not None
    assert [event.source for event in schedule.events] == ["Blackboard", "Local TODO"]
    assert schedule.conflicts[0].title == "OOAD Report"


def test_library_prompt_enrichment_keeps_llm_tool_path():
    prompt = _build_llm_user_prompt("帮我查看一丹图书馆311讨论间今天的预约情况")

    assert "query_library_rooms" in prompt
    assert "do not call `query_rag`" in prompt
    assert '"location": "一丹图书馆311讨论间"' in prompt
    assert '"time_slot": "今天"' in prompt
    assert '"capacity": 0' in prompt


def test_library_prompt_enrichment_uses_empty_time_for_open_window_query():
    prompt = _build_llm_user_prompt("帮我查看一丹图书馆311讨论间什么时候可预约")

    assert "query_library_rooms" in prompt
    assert '"location": "一丹图书馆311讨论间"' in prompt
    assert '"time_slot": ""' in prompt


def test_library_trace_is_concise_and_summarized():
    raw_messages = [
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="query_library_rooms",
                    args={
                        "location": "一丹图书馆311讨论间",
                        "time_slot": "今天",
                        "capacity": 0,
                    },
                    tool_call_id="call_1",
                )
            ]
        ),
        _tool_return(
            "query_library_rooms",
            json.dumps(
                {
                    "query_location": "一丹图书馆311讨论间",
                    "query_time": "2026-05-27",
                    "query_capacity": None,
                    "has_available": True,
                    "rooms": [
                        {
                            "room_id": "311",
                            "room_name": "311（1-3人）",
                            "location": "一丹三层",
                            "capacity": 3,
                            "time_slots": ["21:00-21:15"],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
        ),
    ]

    traces = _build_trace(raw_messages, visible_user_prompt="帮我查一丹311")

    assert len(traces) == 2
    assert [item.title for item in traces] == ["查询图书馆讨论间", "图书馆查询完成"]
    assert "一丹图书馆311讨论间" in traces[0].detail
    assert "找到 1 个" in traces[1].detail
    assert "room_id" not in traces[1].detail
