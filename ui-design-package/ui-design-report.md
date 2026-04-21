# UI Design for Student Productivity Agent

This document provides a standalone UI design for the current frontend of the Student Productivity Agent. It is intentionally separate from the implementation itself. The purpose of this section is to explain the information hierarchy, layout decisions, and interaction flow of the primary interfaces before evaluating the code-level implementation.

## Design Scope

The current frontend has already converged to a chat-first desktop workspace instead of multiple independent feature pages. Therefore, the UI design in this report follows the actual product structure of the frontend:

1. A home page for product introduction and entry
2. A single main dashboard with a three-column layout
3. A chat-first interaction model in which Schedule and Campus QA appear as structured result cards inside the main conversation area
4. A dedicated Thought Trace panel on the right
5. A separate HITL authorization dialog for risky operations
6. A settings dialog for CAS credentials and LLM API key configuration

Common authentication pages are not the focus here because the report asks for the primary interfaces of the system rather than generic login or registration screens.

## Fidelity Choice

This UI design uses low-to-mid fidelity wireframes:

- Separate from the implemented frontend
- Concrete enough to show layout, modules, and interaction flow
- Close enough to the current real frontend to support report discussion

## Screen 1. Main Dashboard

Purpose:
- This is the actual core workspace of the current frontend.
- It uses a three-column structure: left sidebar, center chat workspace, and right Thought Trace panel.
- It matches the implemented frontend structure rather than an abstract multi-page system dashboard.

![Main Dashboard Wireframe](ui-design/assets/dashboard-wireframe.svg)

Design notes:
- The top header contains language switching, settings, schedule refresh, and logout actions.
- The left sidebar contains workspace summary, conversation history, and loaded materials.
- The center area is entirely chat-first, with a message stream and a composer.
- The composer includes a dropdown mode selector for Chat, Schedule, and Campus QA.
- The right side permanently displays Thought Trace and the HITL entry point.

## Screen 2. Schedule Result in Chat Flow

Purpose:
- The final frontend no longer treats the scheduler as a fully separate page.
- Instead, a schedule request is issued from the same main dashboard and the response is rendered as a structured result card inside the chat stream.
- This better matches the current product direction and implementation.

![Schedule Result Wireframe](ui-design/assets/scheduler-wireframe.svg)

Design notes:
- The chat composer is set to Schedule mode.
- The center conversation contains a dedicated schedule result card.
- The schedule card presents events and conflicts directly in the chat flow.
- The right trace panel shows the scheduler reasoning and data collection steps.
- This design preserves the agent-centric interaction style while still clearly presenting structured schedule data.

## Screen 3. Campus QA Result in Chat Flow

Purpose:
- Similar to schedule, Campus Encyclopedia is now represented as a specialized response state inside the main chat interface.
- The user chooses Campus QA mode, asks a question, and receives a structured answer card with citations.

![Campus QA Result Wireframe](ui-design/assets/encyclopedia-wireframe.svg)

Design notes:
- The center panel still remains the same chat workspace.
- The answer appears as a Campus QA card rather than an independent encyclopedia page.
- The card includes the question, markdown-like answer layout, and citation list.
- This design makes the interface consistent with the rest of the agent workflow.

## Screen 4. HITL Authorization Dialog

Purpose:
- This dialog represents the safety mechanism for risky operations.
- In the current frontend, the dialog is triggered from the dashboard and is conceptually tied to the Thought Trace panel.
- It remains one of the most distinctive interfaces in the project.

![HITL Dialog Wireframe](ui-design/assets/hitl-wireframe.svg)

Design notes:
- The dimmed background shows that the current workflow is interrupted.
- The dialog foreground contains action summary, risk level, reason, and payload details.
- The confirm and reject actions are visually separated to reduce accidental approval.
- The dialog is designed as a strong interruption instead of a minor notification, matching the security requirement.

## Screen 5. Settings Dialog

Purpose:
- The current frontend includes a settings entry in the dashboard header.
- This does not open a separate feature page. Instead, it opens a modal dialog on top of the current workspace.
- The dialog is important because it configures the two external dependencies that the frontend actually exposes to users: CAS credentials and the LLM API key.

![Settings Dialog Wireframe](ui-design/assets/settings-wireframe.svg)

Design notes:
- The settings interface belongs to the current dashboard context and appears as an overlay rather than a route switch.
- The dialog contains two stacked cards: one for CAS account/password and one for API key input.
- Each card includes a short explanation and a dedicated save action.
- The bottom close action is visually lighter than the primary save buttons to reflect the current implementation.

## Summary of UI Design Decisions

- The final frontend is chat-first rather than page-first.
- Schedule and Campus QA are not designed as independent primary pages anymore; they are specialized result cards within the conversation flow.
- Persistent context stays on the left, interaction stays in the center, and reasoning stays on the right.
- HITL remains a modal safety checkpoint because that behavior is central to the project's identity.
- Settings is also modal instead of page-based, because it supports the current workspace rather than replacing it.

## Suggested Report Usage

If this section is inserted into the report, a concise explanation can be added before the images:

> We prepared a separate set of low-to-mid fidelity wireframes for the current frontend structure of the Student Productivity Agent. These wireframes are independent from the implementation screenshots and focus on layout, interaction flow, and feature organization. They reflect the final chat-first design adopted by the frontend, where scheduler and campus QA are rendered as structured result states within the main dashboard conversation flow.
