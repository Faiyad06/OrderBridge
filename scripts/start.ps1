# Windows PowerShell: single-process local demo on http://127.0.0.1:8000
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not (Test-Path "data/orderbridge.sqlite3")) { & "backend/.venv/Scripts/python.exe" "scripts/reset_demo.py" }
Set-Location "$root/backend"
$port = if ($env:PORT) { $env:PORT } else { "8000" }
& ".venv/Scripts/python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port $port
