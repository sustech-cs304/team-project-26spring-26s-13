from __future__ import annotations

from dataclasses import dataclass

from .response_quality import ResponseValidationContext, ValidationIssue


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword in text or keyword in lowered for keyword in keywords)


@dataclass(frozen=True)
class SchedulerIntentProfile:
    asks_schedule: bool
    asks_specific_date: bool
    asks_first_slot: bool
    asks_conflict_decision: bool
    asks_adjustment_reasoning: bool


def extract_scheduler_intent(prompt: str) -> SchedulerIntentProfile:
    text = prompt or ""
    lowered = text.lower()
    asks_schedule = _contains_any(
        text,
        ("课表", "课程", "上课", "安排", "schedule", "course", "timetable", "class"),
    )
    asks_specific_date = (
        _contains_any(text, ("年", "月", "日", "202", "-")) and asks_schedule
    )
    asks_first_slot = _contains_any(
        text, ("第一节", "第1节", "first class", "first course")
    )
    asks_conflict_decision = _contains_any(
        text,
        ("冲突", "重叠", "撞课", "conflict", "overlap"),
    )
    asks_adjustment_reasoning = _contains_any(
        text,
        ("调休", "补课", "补班", "holiday", "make-up", "makeup", "校历", "calendar"),
    )
    return SchedulerIntentProfile(
        asks_schedule=asks_schedule,
        asks_specific_date=asks_specific_date,
        asks_first_slot=asks_first_slot,
        asks_conflict_decision=asks_conflict_decision,
        asks_adjustment_reasoning=asks_adjustment_reasoning,
    )


def validate_scheduler_response(
    context: ResponseValidationContext,
) -> ValidationIssue | None:
    intent = extract_scheduler_intent(context.user_prompt)
    answer = context.assistant_content or ""
    tool_names = set(context.tool_names)

    if not intent.asks_schedule:
        return None

    if intent.asks_conflict_decision:
        if not _contains_any(
            answer,
            (
                "会存在时间冲突",
                "不会与课表产生时间冲突",
                "存在时间冲突",
                "不会冲突",
                "有冲突",
                "无冲突",
            ),
        ):
            return ValidationIssue(
                code="scheduler_missing_conflict_decision",
                message="用户询问的是时间冲突判断，但回答没有给出明确冲突结论。",
            )

    if intent.asks_first_slot:
        if not _contains_any(
            answer, ("第一节", "第1节", "当天第一节课", "首门课程", "最早一节")
        ):
            return ValidationIssue(
                code="scheduler_missing_first_slot",
                message="用户询问的是第一节课，但回答没有明确标出第一节课。",
            )

    if intent.asks_adjustment_reasoning:
        has_adjustment_evidence = _contains_any(
            answer, ("调休", "补课", "教学日说明", "补 ", "停课")
        )
        used_adjustment_path = "fetch_schedule_adjustments" in tool_names
        if not has_adjustment_evidence and not used_adjustment_path:
            return ValidationIssue(
                code="scheduler_missing_adjustment_reasoning",
                message="用户询问的是调休/补课语义，但回答没有体现调休规则依据。",
            )

    if intent.asks_specific_date:
        if not answer.strip():
            return ValidationIssue(
                code="scheduler_empty_date_answer",
                message="用户询问具体日期课表，但回答为空。",
            )

    return None
