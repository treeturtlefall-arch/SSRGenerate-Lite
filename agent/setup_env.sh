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
# HF HOME の選択方針は agent/ssr_agent.py の _resolve_hf_home と同一:
# HyperFrames は「配置先自身と全ての親がグループ/他者書込不可 (sticky な /tmp 等は可)」と
# Chrome ダウンロード用の空き容量 (約 512 MB 以上) を要求するため、候補を優先順に
# プライベート性と空き容量 (1 GiB 以上、キャッシュ済みは除く) で検証して選ぶ。
hf_home_ok() {
  local dir="$1" cur mode avail_kb
  cur="$dir"
  while true; do
    if [ -e "$cur" ]; then
      mode="$(stat -c %a "$cur" 2>/dev/null || stat -f %Lp "$cur" 2>/dev/null || echo 0)"
      if [ $(( (8#$mode & 8#022) != 0 && (8#$mode & 8#1000) == 0 )) -eq 1 ]; then
        return 1
      fi
    fi
    [ "$cur" = "/" ] && break
    cur="$(dirname "$cur")"
  done
  if [ -d "$dir/.cache/hyperframes" ]; then
    return 0
  fi
  cur="$dir"
  while [ ! -e "$cur" ]; do cur="$(dirname "$cur")"; done
  avail_kb="$(df -P -k "$cur" 2>/dev/null | awk 'NR==2 {print $4}')"
  [ "${avail_kb:-0}" -ge 1048576 ]
}

if [ -n "${SSR_HF_HOME:-}" ]; then
  HF_HOME_DIR="${SSR_HF_HOME}"
else
  HF_HOME_DIR=""
  PW_HOME="$(getent passwd "$(id -u)" 2>/dev/null | cut -d: -f6 || true)"
  HF_CANDIDATES=(
    "${PROJECT_ROOT}/.hf_home"
    ${XDG_CACHE_HOME:+"${XDG_CACHE_HOME}/ssr-generate-lite/hf_home"}
    "${HOME}/.cache/ssr-generate-lite/hf_home"
    ${PW_HOME:+"${PW_HOME}/.cache/ssr-generate-lite/hf_home"}
    "/var/tmp/ssr_hf_home_$(id -u)"
    "${TMPDIR:-/tmp}/ssr_hf_home_$(id -u)"
  )
  for cand in "${HF_CANDIDATES[@]}"; do
    if hf_home_ok "$cand"; then
      HF_HOME_DIR="$cand"
      break
    fi
    echo "  [hf-home] skipped: $cand"
  done
  if [ -z "${HF_HOME_DIR}" ]; then
    echo "ERROR: HyperFrames 用のプライベート HOME を確保できませんでした。" >&2
    echo "環境変数 SSR_HF_HOME に「親ディレクトリまで含めてグループ/他者書込不可で、空き容量 1 GiB 以上」のディレクトリを指定してください。" >&2
    exit 1
  fi
  echo "  [hf-home] selected: ${HF_HOME_DIR}"
fi
# mkdir 前に存在しなかった途中ディレクトリは、作成後に 700 へ寄せる
# (umask が緩い環境では mkdir がグループ書込可能な中間ディレクトリを作り、
#  HyperFrames のプライベート性チェックに落ちるため。ssr_agent.py と同じ対処)
HF_MISSING_DIRS=()
hf_probe="${HF_HOME_DIR}"
while [ ! -e "$hf_probe" ]; do
  HF_MISSING_DIRS+=("$hf_probe")
  hf_probe="$(dirname "$hf_probe")"
done
mkdir -p "${HF_HOME_DIR}" "${PROJECT_ROOT}/.tmp"
chmod 700 "${HF_HOME_DIR}"
for created_dir in "${HF_MISSING_DIRS[@]}"; do
  chmod 700 "$created_dir" 2>/dev/null || true
done
export SSR_HF_HOME="${HF_HOME_DIR}"
export HOME="${HF_HOME_DIR}"
export TMPDIR="${PROJECT_ROOT}/.tmp"

echo "=== [3/4] Fetching pinned fonts & building deterministic assets ==="
python "${PROJECT_ROOT}/agent/ssr_agent.py" setup "$@"

echo "=== [4/4] Setup complete ==="
