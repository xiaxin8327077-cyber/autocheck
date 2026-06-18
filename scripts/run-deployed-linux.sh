#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
HOST="${AUTO_CHECK_HOST:-0.0.0.0}"
PORT="${AUTO_CHECK_PORT:-8765}"
CONFIG="${AUTO_CHECK_CONFIG:-}"

case "$PORT" in
  ''|*[!0-9]*)
    echo "AUTO_CHECK_PORT must be an integer." >&2
    exit 2
    ;;
esac

if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
  echo "AUTO_CHECK_PORT must be between 1 and 65535." >&2
  exit 2
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

echo "Starting Auto Check on http://$HOST:$PORT"
echo "Use http://<server-ip>:$PORT from another machine on the same network."

if [ -n "$CONFIG" ]; then
  exec "$PYTHON_BIN" -m auto_check --host "$HOST" --port "$PORT" --no-browser --config "$CONFIG"
fi

exec "$PYTHON_BIN" -m auto_check --host "$HOST" --port "$PORT" --no-browser
