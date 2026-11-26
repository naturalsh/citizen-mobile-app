# Nature Shield — Citizen Mobile App + 112 Voice Agent

Unified, mobile-ready civilian web app with an embedded **112 LiveKit Voice Agent** (`voice_agent/`, copied from `Voice_Agents`).

- **Safe places & offline walking routes** (`citizen_app/`): assembly points, shelters, hospitals, and street-level passability computed locally on the device.
- **112 Voice Agent** (`voice_agent/` + `citizen_app/voice.js`): tapping the **112** button opens a mobile emergency voice call screen and connects directly to the running LiveKit `voice.agent` worker.
- **Responsive by device**: automatically displays the mobile UI (bottom navigation, draggable bottom sheet, floating map controls) on phones and split-screen layout on desktop (with an optional Mobile View frame toggle).

## Quick Start (Current Network)

Requires **Node.js 20+** and the Python virtualenv in `voice_agent/.venv` (with `voice_agent/.env` configured).

### Start everything (Web Server + Embedded LiveKit Voice Worker)

```bash
npm start
```

Or with **HTTPS** (recommended for testing on a real phone over Wi-Fi so iOS/Android allow Microphone + GPS):

```bash
npm run start:https
```

This single command:
1. Starts the embedded `voice_agent` LiveKit worker (`voice_agent/.venv/bin/python -m voice.agent start`)
2. Starts the local network server bound to `0.0.0.0:3000`
3. Prints `Local`, `Mobile View`, and `Phone (LAN)` URLs
4. Serves `POST /api/voice/token` (invokes `voice_agent/voice/mint_token.py` to mint a fresh LiveKit room JWT for each 112 call)

### Useful commands

- `npm run start:web-only` — start only the web server (if you run the voice worker separately)
- `npm run voice:worker` — start only the embedded `Voice_Agents` LiveKit worker
- `npm run voice:check` — verify `voice_agent/.env` API keys
- `npm test` — run citizen web app unit tests (44 tests)
- `npm run test:voice` — run embedded `voice_agent` pytest suite (423 tests)
- `node server.mjs --api http://127.0.0.1:8000` — proxy `/public/` to a live `drone-vision` backend
