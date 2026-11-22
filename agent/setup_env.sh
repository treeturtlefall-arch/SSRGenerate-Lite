#!/usr/bin/env bash
# SSRGenerate-Lite — Muse VM / Linux / macOS 環境セットアップスクリプト (§7)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

echo "=== [1/4] Preparing Python venv (.venv) ==="
PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ ! -d ".venv" ]; then
  "${PYTHON_BIN}" -m venv .venv
fi
export PATH="${PROJECT_ROOT}/.venv/bin:${PATH}"
python -m pip install --upgrade pip -q
python -m pip install -r requirements.txt -q

echo "=== [2/4] Preparing private HOME (.hf_home, mode 700) & TMPDIR (.tmp) ==="
mkdir -p "${PROJECT_ROOT}/.hf_home" "${PROJECT_ROOT}/.tmp"
chmod 700 "${PROJECT_ROOT}/.hf_home"
export HOME="${PROJECT_ROOT}/.hf_home"
export TMPDIR="${PROJECT_ROOT}/.tmp"

echo "=== [3/4] Fetching pinned fonts & building deterministic assets ==="
python "${PROJECT_ROOT}/agent/ssr_agent.py" setup "$@"

echo "=== [4/4] Setup complete ==="
