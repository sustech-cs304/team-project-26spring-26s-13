from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str


@dataclass(frozen=True)
class ResponseValidationContext:
    user_prompt: str
    assistant_content: str
    route: str
    tool_names: list[str] = field(default_factory=list)


def detect_alignment_issue(context: ResponseValidationContext) -> ValidationIssue | None:
    """
    Route-aware response validation entrypoint.

    The loop only depends on this registry-style function; concrete domain
    validators live in their own modules to keep validation rules decoupled
    from orchestration and from each other.
    """
    if not context.assistant_content.strip():
        return ValidationIssue(code="empty_answer", message="回答内容为空。")

    if context.route == "scheduler":
        from .scheduler import validate_scheduler_response

        return validate_scheduler_response(context)

    return None
