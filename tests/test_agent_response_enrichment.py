"""
Tests for backend-side Agent response enrichment.

These tests avoid real LLM calls and focus on the deterministic post-processing
that turns tool observations into cited answers and UI payloads.
"""

import json

from pydantic_ai.messages import ModelRequest, ToolReturnPart

from backend.agent.core import FinalResponse
from backend.agent.loop import (
    _build_encyclopedia_payload,
    _build_schedule_data_from_tool_returns,
    _ensure_source_citations,
)


def _tool_return(tool_name: str, content: str) -> ModelRequest:
    return ModelRequest(parts=[ToolReturnPart(tool_name=tool_name, content=content)])


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
