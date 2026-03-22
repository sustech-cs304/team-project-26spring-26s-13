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
python3 frontend/app.py
```

### Notes

- By default the app runs in local mock mode.
- To enable the REST backend skeleton, set `SPA_API_BASE_URL`, for example:

```bash
export SPA_API_BASE_URL=http://127.0.0.1:8000
python3 frontend/app.py
```

- The frontend currently calls these REST endpoints when `SPA_API_BASE_URL` is set:
  - `POST /api/auth/login`
  - `POST /api/auth/register`
  - `POST /api/auth/logout`
  - `PUT /api/user/credentials`
  - `GET /api/materials`
  - `POST /api/materials/upload`
  - `GET /api/dashboard/bootstrap`
  - `POST /api/agent/run`
- Login and registration use the backend when REST mode is enabled; otherwise the app falls back to local mock auth.
- The settings dialog now maps to backend credentials storage (`CAS` + `LLM API Key`) when the user is authenticated.
- The `Add Resource` button uploads files to `/api/materials/upload` in REST mode and falls back to local sidebar-only loading in mock mode.
- After login, the dashboard uses a chat-first flow:
  - left: conversation history + materials
  - center: chat composer and result cards
  - right: thought trace + HITL
- `Schedule` and `Campus QA` are rendered as chat result cards instead of separate main pages.
- The composer mode menu is kept for UX guidance and local mock routing; the current backend framework performs its own route selection from the message content.
- Dashboard bootstrap, auth, materials upload, chat, schedule, encyclopedia, and HITL flows are wired to the current backend contract.
- Current backend-facing docs:
  - [docs/backend-interface-contract-zh.md](docs/backend-interface-contract-zh.md)
  - [docs/backend-interface-contract.md](docs/backend-interface-contract.md)
  - [docs/backend-readme-zh.md](docs/backend-readme-zh.md)
