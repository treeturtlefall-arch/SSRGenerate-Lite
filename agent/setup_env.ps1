# SSRGenerate-Lite — Windows PowerShell 環境セットアップスクリプト
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "=== [1/3] Checking Python environment ==="
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
$VenvScripts = Join-Path $ProjectRoot ".venv\Scripts"
$env:PATH = "$VenvScripts;$env:PATH"
python -m pip install -r requirements.txt -q

Write-Host "=== [2/3] Fetching pinned fonts & building deterministic assets ==="
python "$ProjectRoot\agent\ssr_agent.py" setup $args

Write-Host "=== [3/3] Setup complete ==="
