# Current Frontend/Backend Interface Contract

This document describes how the current `zhaoxun` frontend branch integrates with the backend framework that now exists on `main`.

Current stack:

- Frontend: `PyQt6` desktop client
- Backend: `FastAPI` REST API
- Auth: `JWT Bearer Token`

When `SPA_API_BASE_URL` is not set, the frontend stays in local mock mode.
When it is set, the frontend switches to the real backend contract described below.

## Endpoints the current frontend actually calls

In REST mode, the frontend currently calls:

1. `POST /api/auth/login`
2. `POST /api/auth/register`
3. `POST /api/auth/logout`
4. `GET /api/dashboard/bootstrap`
5. `PUT /api/user/credentials`
6. `POST /api/materials/upload`
7. `GET /api/materials`
8. `POST /api/schedule/refresh`
9. `GET /api/agent/sessions`
10. `DELETE /api/agent/sessions/{session_id}`
11. `POST /api/agent/run`

The backend also exposes more endpoints on `main`, but the current frontend does not actively depend on them yet:

- `GET /api/user/profile`
- `PUT /api/user/profile`

## Current frontend behavior

The frontend flow is:

1. `HomePage`
2. `AuthPage`
3. `DashboardPage`

The dashboard layout is:

- left: workspace summary, conversation history, materials
- center: chat-first workflow
- right: thought trace + HITL

Important note:

- the mode menu (`Chat / Schedule / Campus QA`) is still visible in the UI
- but in real backend mode, the frontend no longer sends explicit route hints
- backend-side routing is expected to happen inside the current agent/router implementation
- selected items in the left material list are forwarded as `attachments`
- the history sidebar is supplemented by `GET /api/agent/sessions`
- assistant replies and trace steps are progressively rendered in the UI for a streaming-like experience
- the transport contract is still ordinary JSON; SSE/WebSocket is not required for the current frontend to work

## Common rules

### Auth header

All authenticated requests use:

```http
Authorization: Bearer <jwt-token>
```

### Time format

Use `ISO 8601`, for example:

```text
2026-03-23T10:01:00+08:00
```

### Error handling

If the backend returns non-2xx, the frontend will surface FastAPI `detail` directly.
Readable string details are strongly recommended.

## 1. Auth

## `POST /api/auth/login`

Request:

```json
{
  "username": "zhaoxun",
  "password": "password123"
}
```

Response:

```json
{
  "user_id": "u_001",
  "display_name": "Zhaoxun",
  "major": "Software Engineering",
  "token": "eyJhbGciOi..."
}
```

Frontend usage:

- store JWT token
- switch into Dashboard
- immediately call `GET /api/dashboard/bootstrap`

## `POST /api/auth/register`

Request:

```json
{
  "username": "zhaoxun",
  "password": "password123",
  "display_name": "Zhaoxun",
  "major": "Software Engineering"
}
```

Response:

```json
{
  "user_id": "u_001",
  "display_name": "Zhaoxun",
  "major": "Software Engineering",
  "token": "eyJhbGciOi..."
}
```

## `POST /api/auth/logout`

Recommended response:

- `204 No Content`

## 2. Dashboard Bootstrap

## `GET /api/dashboard/bootstrap`

Headers:

```http
Authorization: Bearer <jwt-token>
```

Response:

```json
{
  "user_profile": {
    "user_id": "u_001",
    "display_name": "Zhaoxun",
    "major": "Software Engineering",
    "preferences": {
      "theme": "light",
      "language": "zh"
    }
  },
  "chat_history": [
    {
      "message_id": "msg_001",
      "role": "assistant",
      "content": "Welcome back.",
      "timestamp": "2026-03-23T10:00:00+08:00"
    }
  ],
  "materials": [
    {
      "file_id": "file_101",
      "file_name": "student_handbook_2026.pdf",
      "file_type": "application/pdf",
      "subject_type": "policy",
      "vectorized": true,
      "uploaded_at": "2026-03-23T09:58:00+08:00"
    }
  ],
  "local_schedule": {
    "events": [],
    "conflicts": []
  }
}
```

Frontend mapping:

- `user_profile` -> top bar + workspace summary
- `chat_history` -> center chat
- `materials` -> left sidebar material list
- `local_schedule` -> schedule baseline data for later result cards

Contract rule:

- do not omit fields
- return empty arrays / empty objects instead of `null`

## 3. Credentials

## `PUT /api/user/credentials`

Headers:

```http
Authorization: Bearer <jwt-token>
```

Request:

```json
{
  "cas_account": "1221xxxx",
  "cas_password": "example-password",
  "llm_api_key": null
}
```

or:

```json
{
  "cas_account": null,
  "cas_password": null,
  "llm_api_key": "sk-example"
}
```

Recommended response:

- `204 No Content`

Frontend behavior:

- `Save CAS` sends whichever CAS fields the user filled in
- `Save API` sends `llm_api_key`

## 4. Material Upload

## `POST /api/materials/upload`

Headers:

```http
Authorization: Bearer <jwt-token>
Content-Type: multipart/form-data
```

Form field:

- field name is always `file`

Current frontend file picker filters:

- `.pdf`
- `.ppt`
- `.pptx`
- `.md`

Response:

```json
{
  "file_id": "file_201",
  "file_name": "uploaded_notes.md",
  "file_type": "text/markdown",
  "subject_type": "cs",
  "vectorized": false,
  "uploaded_at": "2026-03-23T10:02:00+08:00"
}
```

Frontend behavior:

- call `GET /api/materials` after successful uploads
- refresh the left material list from the backend response
- append a trace item saying materials were loaded

## `GET /api/materials`

Headers:

```http
Authorization: Bearer <jwt-token>
```

Frontend behavior:

- called after successful uploads
- used to refresh the authoritative left-sidebar material list

## `POST /api/schedule/refresh`

Headers:

```http
Authorization: Bearer <jwt-token>
```

Request:

```json
{}
```

Frontend behavior:

- triggered by the `Refresh Schedule` button in the dashboard header
- response data is rendered as a schedule result card inside the chat flow

## `GET /api/agent/sessions`

Headers:

```http
Authorization: Bearer <jwt-token>
```

Frontend behavior:

- called after bootstrap to populate the left conversation history with remote summaries
- used again after chat responses to keep timestamps/previews in sync

## `DELETE /api/agent/sessions/{session_id}`

Headers:

```http
Authorization: Bearer <jwt-token>
```

Frontend behavior:

- triggered by `Delete Chat` in the left sidebar
- only used when the current chat has remote-backed state

## 5. Agent

## `POST /api/agent/run`

Headers:

```http
Authorization: Bearer <jwt-token>
Content-Type: application/json
```

Normal request:

```json
{
  "user_id": "u_001",
  "session_id": "sess_ab12cd34",
  "message": "Check whether my Blackboard deadlines conflict with lab time.",
  "attachments": [
    {
      "file_id": "file_201",
      "file_name": "uploaded_notes.md",
      "file_type": "text/markdown"
    }
  ],
  "hitl_reply": null
}
```

HITL follow-up request:

```json
{
  "user_id": "u_001",
  "session_id": "sess_ab12cd34",
  "message": "",
  "attachments": [],
  "hitl_reply": {
    "request_id": "hitl_sess_ab12cd34_001",
    "approved": true
  }
}
```

Response:

```json
{
  "session_id": "sess_ab12cd34",
  "assistant_message": {
    "role": "assistant",
    "content": "I found a conflict on Thursday 16:00. Please review the schedule summary below.",
    "timestamp": "2026-03-23T10:01:00+08:00"
  },
  "trace": [
    {
      "phase": "Observation",
      "title": "Read user goal",
      "detail": "Need a schedule conflict check.",
      "status": "done",
      "timestamp": "2026-03-23T10:00:58+08:00"
    }
  ],
  "route": "scheduler",
  "ui_payload": {
    "schedule": {
      "events": [
        {
          "event_id": "evt_002",
          "title": "Blackboard Deadline: OOAD Report",
          "time": "Thu 15:30",
          "source": "Blackboard",
          "detail": "Upload final report before the submission closes."
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

Valid route values:

- `chat`
- `scheduler`
- `encyclopedia`
- `os_automation`

Trace status values supported by the frontend:

- `pending`
- `running`
- `done`
- `error`

Trace phase values expected by the backend schema:

- `Observation`
- `Reasoning`
- `Tool Use`
- `Reflection`

Frontend mapping:

- `assistant_message.content` -> center chat
- `trace` -> right-side thought trace panel
- `ui_payload.schedule` -> schedule card inside chat
- `ui_payload.encyclopedia` -> campus QA card inside chat
- `hitl_request` -> authorization dialog
- `error` -> error trace item
- selected materials are forwarded as `attachments`; when nothing is selected, the frontend sends `[]`

## Most important implementation target

If the backend team wants the current frontend to run successfully as soon as possible, these are the critical pieces:

1. `login/register` must return a JWT token
2. `bootstrap` must return a full object with no missing fields
3. `PUT /api/user/credentials` must accept the payload and return `204`
4. `POST /api/materials/upload` must return `MaterialInfo`
5. `POST /api/agent/run` must return a complete `AgentResponse`
