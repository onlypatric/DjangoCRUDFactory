#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${1:-${REPO_ROOT}/dist}"

mkdir -p "${OUTPUT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VERSION="$("${PYTHON_BIN}" - <<'PY'
from pathlib import Path
import tomllib

pyproject = Path("pyproject.toml")
data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
print(data["project"]["version"])
PY
)"

STAGING_DIR="$(mktemp -d)"
PACKAGE_ROOT="${STAGING_DIR}/crudfactory"
ARCHIVE_NAME="crudfactory-${VERSION}-export.tar.gz"
ARCHIVE_PATH="${OUTPUT_DIR}/${ARCHIVE_NAME}"

cleanup() {
    rm -rf "${STAGING_DIR}"
}
trap cleanup EXIT

mkdir -p "${PACKAGE_ROOT}/src"
mkdir -p "${PACKAGE_ROOT}/wiki"

cp "${REPO_ROOT}/pyproject.toml" "${PACKAGE_ROOT}/"
cp "${REPO_ROOT}/README.md" "${PACKAGE_ROOT}/"
rsync -a \
    --exclude='.DS_Store' \
    --exclude='*/.DS_Store' \
    --exclude='__pycache__/' \
    --exclude='*/__pycache__/' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='*.tar.gz' \
    "${REPO_ROOT}/src/crudfactory/" \
    "${PACKAGE_ROOT}/src/crudfactory/"
rsync -a \
    --exclude='.DS_Store' \
    --exclude='*/.DS_Store' \
    --exclude='__pycache__/' \
    --exclude='*/__pycache__/' \
    "${REPO_ROOT}/wiki/" \
    "${PACKAGE_ROOT}/wiki/"

tar -czf "${ARCHIVE_PATH}" -C "${STAGING_DIR}" crudfactory

echo "Created archive: ${ARCHIVE_PATH}"
echo "Archive contents:"
tar -tzf "${ARCHIVE_PATH}"
