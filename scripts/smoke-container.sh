#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
image="${1:?image required}"
name="audience-smoke-$$"
export MEETING_PASSWORD ADMIN_PASSWORD METRICS_TOKEN
MEETING_PASSWORD="$(openssl rand -hex 24)"
ADMIN_PASSWORD="$(openssl rand -hex 24)"
METRICS_TOKEN="$(openssl rand -hex 24)"
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT
docker run -d --name "$name" -p 127.0.0.1::8000 --read-only --tmpfs /tmp --tmpfs /app/data:uid=1000,gid=1000   --cap-drop ALL --security-opt no-new-privileges -e PROVIDER_MODE=mock -e COOKIE_SECURE=false   -e MEETING_PASSWORD -e ADMIN_PASSWORD -e METRICS_TOKEN "$image" >/dev/null
port="$(docker port "$name" 8000/tcp | cut -d: -f2)"
export SMOKE_URL="http://127.0.0.1:$port"
for attempt in $(seq 1 30); do
  if curl -fsS "$SMOKE_URL/healthz" >/dev/null 2>&1; then break; fi
  sleep 1
done
.venv/bin/python scripts/smoke.py
