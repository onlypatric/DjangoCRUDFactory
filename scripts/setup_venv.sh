#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${ROOT_DIR}/.venv"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Could not find Python interpreter: ${PYTHON_BIN}" >&2
  echo "Set PYTHON_BIN to a Python 3.12+ executable and rerun." >&2
  exit 1
fi

echo "Creating virtualenv at ${VENV_DIR}..."
"${PYTHON_BIN}" -m venv "${VENV_DIR}"

echo "Upgrading pip, setuptools, and wheel..."
"${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel

echo "Installing crudfactory with dev extras..."
"${VENV_DIR}/bin/python" -m pip install -e "${ROOT_DIR}[dev]"

echo "Virtualenv ready."
echo "Activate with: source ${VENV_DIR}/bin/activate"
