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

echo "=== [2/4] Preparing private HOME (mode 700) & TMPDIR (.tmp) ==="
if [ -n "${SSR_HF_HOME:-}" ]; then
  HF_HOME_DIR="${SSR_HF_HOME}"
elif find "${PROJECT_ROOT}" -maxdepth 0 -perm /022 2>/dev/null | grep -q .; then
  HF_HOME_DIR="${TMPDIR:-/tmp}/ssr_hf_home_$(id -u)"
else
  HF_HOME_DIR="${PROJECT_ROOT}/.hf_home"
fi
mkdir -p "${HF_HOME_DIR}" "${PROJECT_ROOT}/.tmp"
chmod 700 "${HF_HOME_DIR}"
export SSR_HF_HOME="${HF_HOME_DIR}"
export HOME="${HF_HOME_DIR}"
export TMPDIR="${PROJECT_ROOT}/.tmp"

echo "=== [3/4] Fetching pinned fonts & building deterministic assets ==="
python "${PROJECT_ROOT}/agent/ssr_agent.py" setup "$@"

echo "=== [4/4] Setup complete ==="
