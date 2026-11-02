#!/usr/bin/env bash
set -euo pipefail

export PYTHONUNBUFFERED=1
set -a
source /opt/project2/shared/env/familylearning.env
set +a

RELEASE_DIR=$(cd "$(dirname "$0")" && pwd)
mkdir -p /opt/project2/logs

cleanup() {
  kill "${API_PID:-}" "${WEB_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "$RELEASE_DIR/backend"
.venv/bin/uvicorn app.main:app \
  --host 127.0.0.1 --port 8002 --proxy-headers \
  >>/opt/project2/logs/project2.out.log \
  2>>/opt/project2/logs/project2.err.log &
API_PID=$!

cd "$RELEASE_DIR/frontend"
python3 "$RELEASE_DIR/deploy/serve_spa.py" \
  --root "$RELEASE_DIR/frontend/dist" --host 127.0.0.1 --port 8003 \
  >>/opt/project2/logs/project2.out.log \
  2>>/opt/project2/logs/project2.err.log &
WEB_PID=$!

wait -n "$API_PID" "$WEB_PID"
