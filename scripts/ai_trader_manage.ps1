# Manage del carril IA discrecional cada 15 min en horario de mercado.
# NO registrada: la registra el operador cuando lo decida.
$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"
$root = "E:\trading-lab"
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$logDir = Join-Path $root "logs\ai_trader"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("manage_{0}.log" -f (Get-Date -Format "yyyyMMdd"))
& $lab ai-trader manage *>> $log
exit $LASTEXITCODE
