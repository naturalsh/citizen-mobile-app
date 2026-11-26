# Nature Shield — Citizen Mobile App

Standalone, mobile-ready offline PWA for civilians, extracted and enhanced from `drone-vision/citizen_app`.

Shows nearby assembly points, shelters, hospitals, and health centres with walking routes computed **locally on the phone** (your position never leaves the device).

## Features

- **Mobile-first UI & touch gestures**
  - Draggable bottom sheet with grabber handle (`peek` / `half` / `full` snap states via swipe or tap)
  - Thumb-friendly mobile bottom navigation bar (**Map**, **Assembly**, **Hospitals**)
  - Floating map action buttons (**Find my location** GPS FAB & **Recenter route** FAB)
  - Full safe-area inset support (`viewport-fit=cover`, `100dvh`, `overscroll-behavior-y: none`)
- **Desktop Mobile View mode**
  - Click the phone icon in the header (or open `/app/?view=mobile`) to preview and demo the exact 390×844 mobile experience inside a phone frame on desktop screens
- **Offline-first PWA**
  - Service worker (`sw.js`) caches the entire app shell and MapLibre vector style/fonts
  - Area pack (`pack.json`) is cached on-device (`store.js`) so routing continues working without a network
  - Supports **Add to Home Screen / Install app** (`beforeinstallprompt` + iOS Safari instructions)
- **Multilingual**: English (`en`), Turkish (`tr`), Greek (`el`)
- **Strict security & privacy**: zero inline scripts/styles (strict CSP), zero tracking, no user coordinates ever sent to any server

## Quick Start

Requires Node.js 20+ (no `npm install` needed — zero external dependencies).

```bash
npm start
```

Then open:
- **Mobile View (on desktop)**: `http://127.0.0.1:3000/app/?view=mobile`
- **Responsive / Desktop**: `http://127.0.0.1:3000/app/`
- **On a real phone (same Wi-Fi)**: use the `Phone (LAN)` URL printed in the terminal

### Connecting to a live `drone-vision` backend

By default, the server serves the bundled offline snapshot in `public/` (Antakya – Defne, Hatay). To connect to a live `drone-vision` instance so operator street confirmations, notices, and place reports stream in real time:

```bash
node server.mjs --api http://127.0.0.1:8000
```

## Tests

```bash
npm test
```

Runs all unit tests in `tests/citizen/` (`i18n`, `route`, `store`, `sw`).
