[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/py413vYq)

## Student Productivity Agent Frontend Prototype

This repository now includes a `PyQt6` frontend prototype for the Student Productivity Agent project.

### What is included

- A desktop layout adapted from the previous OOAD frontend structure
- A landing page, auth page, and dashboard flow
- English / Chinese language switching
- Left sidebar for profile and uploaded materials
- Main dashboard with agent chat, schedule view, and campus encyclopedia view
- Right-side Thought Trace panel
- A Human-in-the-Loop authorization dialog
- Local mock data plus a REST client scaffold for backend integration

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
  - `GET /api/dashboard/bootstrap`
  - `POST /api/agent/run`
- Login and registration are still local in this prototype, while dashboard bootstrap, chat, schedule, encyclopedia, and HITL flows are ready for backend wiring.
- The interface contracts are documented in:
  - [docs/backend-interface-contract.md](docs/backend-interface-contract.md)
  - [docs/backend-interface-contract-zh.md](docs/backend-interface-contract-zh.md)
- A backend-oriented Chinese README is also available:
  - [docs/backend-readme-zh.md](docs/backend-readme-zh.md)
