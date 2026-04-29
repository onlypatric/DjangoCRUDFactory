#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
HOST="localhost"
PORT="${CRUDFACTORY_DEMO_PORT:-8765}"
BASE_URL="http://${HOST}:${PORT}"
OUTPUT_DIR="${ROOT_DIR}/demo_output"
LOG_FILE="${OUTPUT_DIR}/server.log"

export DJANGO_SETTINGS_MODULE="tests.django_project.settings"
export PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}:${PYTHONPATH:-}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Expected virtualenv python at ${PYTHON_BIN}" >&2
  echo "Create/install the environment first, then rerun this script." >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"

echo "Applying migrations to the demo SQLite database..."
"${PYTHON_BIN}" -m django migrate --noinput

echo "Resetting demo database for deterministic output..."
"${PYTHON_BIN}" -m django flush --noinput

echo "Starting Django server on ${BASE_URL}..."
"${PYTHON_BIN}" "${ROOT_DIR}/scripts/crudfactory_demo_server.py" \
  --host "${HOST}" \
  --port "${PORT}" >"${LOG_FILE}" 2>&1 &
SERVER_PID=$!

cleanup() {
  if kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
    wait "${SERVER_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "Waiting for Django server..."
"${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

base_url = f"http://localhost:{os.environ.get('CRUDFACTORY_DEMO_PORT', '8765')}"
deadline = time.monotonic() + 20

while time.monotonic() < deadline:
    try:
        request = Request(f"{base_url}/api/locations/")
        with urlopen(request, timeout=1) as response:
            if response.status < 500:
                sys.exit(0)
    except HTTPError as exc:
        if exc.code < 500:
            sys.exit(0)
    except URLError:
        time.sleep(0.25)

print(f"Django server did not become ready at {base_url}", file=sys.stderr)
sys.exit(1)
PY

echo "Running demo client and exporting JSON..."
"${PYTHON_BIN}" "${ROOT_DIR}/scripts/crudfactory_demo_client.py" \
  --base-url "${BASE_URL}" \
  --output-dir "${OUTPUT_DIR}"

echo "Demo complete."
echo "Combined JSON: ${OUTPUT_DIR}/crudfactory_demo_results.json"
echo "Individual responses: ${OUTPUT_DIR}/responses/"
echo "OpenAPI JSON: ${OUTPUT_DIR}/ev_openapi_schema.json"
echo "OpenAPI summary: ${ROOT_DIR}/wiki/generated/ev_openapi_summary.md"
echo "Server log: ${LOG_FILE}"
