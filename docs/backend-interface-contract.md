# Frontend Backend Interface Contract

This document defines the two core interfaces the frontend needs from the AI Loop layer and the database layer for the `Student Productivity Agent` project.

The goal is to keep the integration small:

1. One interface for the AI loop
2. One interface for the database bootstrap data

This is enough for the current frontend prototype:

- main chat
- thought trace panel
- HITL authorization dialog
- schedule dashboard
- campus encyclopedia result rendering
- profile and chat history initialization

## Interface 1: AI Loop

### Endpoint

`POST /api/agent/run`

### Purpose

The frontend sends one user action to the AI loop, and the backend returns:

- assistant reply
- thought trace events
- route result for schedule or encyclopedia
- optional HITL interception request

To keep the total number of interfaces at two, HITL approval can also reuse this same endpoint.

### Request Body

```json
{
  "user_id": "u_001",
  "session_id": "sess_20260321_01",
  "message": "Check whether my Blackboard deadlines conflict with lab time.",
  "attachments": [
    {
      "file_id": "file_101",
      "file_name": "week5_notes.md",
      "file_type": "text/markdown"
    }
  ],
  "context": {
    "active_tab": "chat",
    "selected_feature": "scheduler"
  },
  "hitl_reply": null,
  "connection_settings": {
    "cas": {
      "username": "1221xxxx",
      "password": "example-password"
    },
    "api": {
      "base_url": "https://api.example.com",
      "api_key": "example-api-key"
    }
  }
}
```

### Notes

- `message` is the natural language input from the main chat box.
- `attachments` is optional and is used for uploaded files or selected materials.
- `context.active_tab` helps the backend understand whether the user is currently asking about chat, schedule, or encyclopedia.
- `hitl_reply` is used only when the user is responding to a previously blocked high-risk action.
- `connection_settings` is optional. The frontend can store CAS / API configuration locally and forward it to the backend with the request.

### HITL Follow-up Request Example

```json
{
  "user_id": "u_001",
  "session_id": "sess_20260321_01",
  "message": "",
  "attachments": [],
  "context": {
    "active_tab": "chat",
    "selected_feature": "os_automation"
  },
  "connection_settings": {
    "cas": {
      "username": "1221xxxx",
      "password": "example-password"
    },
    "api": {
      "base_url": "https://api.example.com",
      "api_key": "example-api-key"
    }
  },
  "hitl_reply": {
    "request_id": "hitl_9001",
    "approved": true
  }
}
```

### Response Body

```json
{
  "session_id": "sess_20260321_01",
  "assistant_message": {
    "role": "assistant",
    "content": "I found a conflict on Thursday 16:00. Please review the suggested adjustment in the schedule panel.",
    "timestamp": "2026-03-21T20:00:00+08:00"
  },
  "trace": [
    {
      "phase": "Observation",
      "title": "Read user goal",
      "detail": "Need a schedule conflict check and concise explanation.",
      "status": "done",
      "timestamp": "2026-03-21T19:59:58+08:00"
    },
    {
      "phase": "Reasoning",
      "title": "Plan tool sequence",
      "detail": "Blackboard scraper -> merge local calendar -> detect overlap.",
      "status": "done",
      "timestamp": "2026-03-21T19:59:59+08:00"
    }
  ],
  "route": "scheduler",
  "ui_payload": {
    "schedule": {
      "events": [
        {
          "title": "Blackboard Deadline: OOAD Report",
          "time": "Thu 15:30",
          "source": "Blackboard",
          "detail": "Upload final report before the submission closes."
        },
        {
          "title": "Embedded Systems Lab",
          "time": "Thu 16:00 - 18:00",
          "source": "Campus Calendar",
          "detail": "Lab room 107, attendance required."
        }
      ],
      "conflicts": [
        {
          "title": "OOAD report overlaps with lab preparation",
          "detail": "Deadline is 30 minutes before a fixed lab block on Thursday."
        }
      ]
    },
    "encyclopedia": null
  },
  "hitl_request": null,
  "error": null
}
```

### When the Route Is Encyclopedia

Set:

- `route = "encyclopedia"`
- `ui_payload.encyclopedia.answer_markdown`
- `ui_payload.encyclopedia.citations`

Example:

```json
{
  "route": "encyclopedia",
  "ui_payload": {
    "schedule": null,
    "encyclopedia": {
      "query": "credit requirements",
      "answer_markdown": "### Credit Requirement Summary\n- ...",
      "citations": [
        "Student Handbook / Degree Requirements / General Rules"
      ]
    }
  }
}
```

### When a HITL Interception Is Triggered

Set `hitl_request` instead of directly executing the risky action.

```json
{
  "session_id": "sess_20260321_01",
  "assistant_message": {
    "role": "assistant",
    "content": "This action requires manual approval before execution.",
    "timestamp": "2026-03-21T20:05:00+08:00"
  },
  "trace": [
    {
      "phase": "Tool Use",
      "title": "Awaiting authorization",
      "detail": "Calendar overwrite is classified as a high-risk action.",
      "status": "pending",
      "timestamp": "2026-03-21T20:05:00+08:00"
    }
  ],
  "route": "chat",
  "ui_payload": {
    "schedule": null,
    "encyclopedia": null
  },
  "hitl_request": {
    "request_id": "hitl_9001",
    "action": "Overwrite local study calendar",
    "risk": "high",
    "reason": "The agent wants to move three study blocks to avoid a deadline collision.",
    "payload": [
      "Move OOAD report reminder from Thu 15:00 to Wed 21:00",
      "Create a 40-minute buffer before the Thursday lab"
    ]
  },
  "error": null
}
```

### Frontend Mapping

- Chat panel uses `assistant_message`
- Thought Trace panel uses `trace`
- Schedule tab uses `ui_payload.schedule`
- Encyclopedia tab uses `ui_payload.encyclopedia`
- HITL modal uses `hitl_request`

## Interface 2: Database Bootstrap

### Endpoint

`GET /api/dashboard/bootstrap?user_id=u_001`

### Purpose

The frontend needs one database-facing bootstrap interface to initialize the whole page.

This endpoint should return:

- user profile
- user settings
- historical chat records
- uploaded material list
- cached local schedule items

### Response Body

```json
{
  "user_profile": {
    "user_id": "u_001",
    "display_name": "SUSTech Student",
    "major": "Software Engineering",
    "preferences": {
      "theme": "cosmic",
      "language": "en"
    }
  },
  "chat_history": [
    {
      "message_id": "msg_001",
      "role": "assistant",
      "content": "Welcome back. I can track your schedule, search campus policies, and explain each tool step in the Thought Trace panel.",
      "timestamp": "2026-03-21T19:50:00+08:00"
    },
    {
      "message_id": "msg_002",
      "role": "user",
      "content": "Please check whether my Blackboard deadlines conflict with lab time.",
      "timestamp": "2026-03-21T19:51:00+08:00"
    }
  ],
  "materials": [
    {
      "file_id": "file_101",
      "file_name": "week5_notes.md",
      "file_type": "text/markdown",
      "vectorized": false,
      "uploaded_at": "2026-03-21T18:00:00+08:00"
    },
    {
      "file_id": "file_102",
      "file_name": "student_handbook_2026.pdf",
      "file_type": "application/pdf",
      "vectorized": true,
      "uploaded_at": "2026-03-20T21:00:00+08:00"
    }
  ],
  "local_schedule": {
    "events": [
      {
        "event_id": "evt_001",
        "title": "CS304 Team Meeting",
        "time": "Mon 19:00 - 20:30",
        "source": "Local TODO",
        "detail": "Finalize API contract and UI handoff."
      }
    ],
    "conflicts": [
      {
        "title": "OOAD report overlaps with lab preparation",
        "detail": "Deadline is 30 minutes before a fixed lab block on Thursday."
      }
    ]
  }
}
```

### Frontend Mapping

- Left profile card uses `user_profile`
- Material list uses `materials`
- Initial chat window uses `chat_history`
- Schedule dashboard can preload `local_schedule.events` and `local_schedule.conflicts`

## Recommended Field Rules

- All timestamps should use ISO 8601 format with timezone, for example `2026-03-21T20:00:00+08:00`
- `role` should only be `user` or `assistant`
- `trace.status` should only be `done`, `running`, or `pending`
- `route` should only be `chat`, `scheduler`, or `encyclopedia`
- `hitl_request.risk` should only be `low`, `medium`, or `high`

## Minimal Integration Flow

1. Frontend startup:
   `GET /api/dashboard/bootstrap`

2. User sends a message:
   `POST /api/agent/run`

3. AI loop returns:
   chat reply + trace + schedule update or encyclopedia result

4. If risky action is detected:
   frontend shows HITL dialog using `hitl_request`

5. User approves or rejects:
   frontend sends approval back to the same `POST /api/agent/run` endpoint using `hitl_reply`

## Why Only These Two Interfaces

For the current milestone, these two interfaces are enough because:

- AI loop already owns reasoning, routing, tool execution, and HITL interception
- database bootstrap already owns persistent user information and chat history
- the frontend only needs one dynamic channel and one initialization channel

If the backend later becomes more detailed, it can split into more endpoints such as:

- file upload
- profile update
- standalone HITL approval
- schedule sync refresh
- RAG search only

But for now, the frontend can move forward with just the two interfaces above.
