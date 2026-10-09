#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m compileall -q backend/app
.venv/bin/pytest -q
node --test frontend/tests/*.test.mjs
npm run build --prefix frontend
scripts/scan.sh
