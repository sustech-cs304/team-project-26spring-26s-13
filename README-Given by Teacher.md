[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/py413vYq)

## Student Productivity Agent Frontend Prototype

This repository now includes a `PyQt6` frontend prototype for the Student Productivity Agent project.

### What is included

- A desktop frontend prototype built with PyQt6
- A landing page, auth page, and dashboard flow
- English / Chinese language switching
- Left sidebar for conversation history and loaded materials
- Main dashboard with a chat-first workspace and result cards for schedule / campus QA
- A mode selector under the composer for `Chat / Schedule / Campus QA`
- Right-side Thought Trace panel
- A Human-in-the-Loop authorization dialog
- Local mock data plus a REST client adapted to the current backend framework on `main`

### Run the prototype

```bash
python3 -m pip install -r requirements.txt
python3 God Xun-Frontend/app.py
```

### Notes

- By default the app runs in local mock mode.
- To enable the REST backend skeleton, set `SPA_API_BASE_URL`, for example:

```bash
export SPA_API_BASE_URL=http://127.0.0.1:8000
python3 God Xun-Frontend/app.py
```

- The frontend currently calls these REST endpoints when `SPA_API_BASE_URL` is set:
  - `POST /api/auth/login`
  - `POST /api/auth/register`
  - `POST /api/auth/logout`
  - `PUT /api/user/credentials`
  - `GET /api/materials`
  - `POST /api/materials/upload`
  - `GET /api/dashboard/bootstrap`
  - `POST /api/schedule/refresh`
  - `GET /api/agent/sessions`
  - `DELETE /api/agent/sessions/{session_id}`
  - `POST /api/agent/run`
- Login and registration use the backend when REST mode is enabled; otherwise the app falls back to local mock auth.
- The settings dialog now maps to backend credentials storage (`CAS` + `LLM API Key`) when the user is authenticated, and `CAS` supports partial updates.
- The `Add Resource` button uploads files to `/api/materials/upload`, then refreshes the authoritative material list from `GET /api/materials` in REST mode.
- After login, the dashboard uses a chat-first flow:
  - left: conversation history + materials
  - center: chat composer and result cards
  - right: thought trace + HITL
- `Schedule` and `Campus QA` are rendered as chat result cards instead of separate main pages.
- The composer mode menu is kept for UX guidance and local mock routing; the current backend framework performs its own route selection from the message content.
- Assistant replies and trace steps now render progressively in the desktop UI instead of appearing all at once.
- Selected materials in the left sidebar are forwarded to `POST /api/agent/run` as `attachments`.
- Conversation history now syncs with `GET /api/agent/sessions`, `Delete Chat` uses `DELETE /api/agent/sessions/{session_id}`, and `Refresh Schedule` uses `POST /api/schedule/refresh`.
- Dashboard bootstrap, auth, materials upload, sessions, schedule refresh, chat, encyclopedia, and HITL flows are wired to the current backend contract.
- Current backend-facing docs:
  - [docs/backend-interface-contract-zh.md](Guideline/docs/Frontend Relevant/backend-interface-contract-zh.md)
  - [docs/backend-interface-contract.md](Guideline/docs/Frontend Relevant/backend-interface-contract.md)
  - [docs/backend-readme-zh.md](Guideline/docs/Frontend Relevant/backend-readme-zh.md)
  - [docs/frontend-api-connection-zh.md](Guideline/docs/Frontend Relevant/frontend-api-connection-zh.md)
