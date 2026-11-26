#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VA_DIR="$ROOT/voice_agents"

if [ -x "$VA_DIR/.venv/bin/python" ]; then
    PY="$VA_DIR/.venv/bin/python"
elif [ -x "$ROOT/../Voice_Agents/.venv/bin/python" ]; then
    PY="$ROOT/../Voice_Agents/.venv/bin/python"
else
    PY="$(command -v python3)"
fi

cd "$VA_DIR"
echo "Starting embedded Voice_Agents LiveKit worker using: $PY"
exec "$PY" -m voice.agent dev
