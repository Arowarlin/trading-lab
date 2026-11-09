# Comparacion nocturna lite vs deep sobre un activo rotatorio.
# Solo mide y guarda decisiones: NO ejecuta ordenes ni activa bots.
# No se registra automaticamente; usa register_deep_compare_task.ps1.
param(
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"

$root = "E:\trading-lab"
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$logDir = Join-Path $root "logs\agents"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("deep_compare_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

function Write-Log([string]$Message) {
    Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message) -Encoding utf8
}

Set-Location $root
Write-Log "Deep compare start"

if (-not (Test-Path $lab)) {
    Write-Log "No existe $lab"
    exit 1
}

if ($PreflightOnly) {
    & $lab agent-compare --report *>> $log
    Write-Log "PreflightOnly: fin sin lanzar deep."
    exit 0
}

# Un activo por noche para no encadenar varios runs multi-agente.
$watchlist = @("SPY", "QQQ", "NVDA")
$index = [int](Get-Date).DayOfWeek % $watchlist.Count
$ticker = $watchlist[$index]
Write-Log "Ticker nocturno: $ticker"

& $lab agent-compare $ticker --analysts "market,news,fundamentals,social" *>> $log
$code = $LASTEXITCODE
Write-Log "agent-compare $ticker exit=$code"

# Rellena retornos 1/5/20d; no envia ordenes.
& $lab decisions update *>> $log
if ($LASTEXITCODE -ne 0) {
    Write-Log "decisions update fallo"
    exit 1
}

if ($code -ne 0) {
    & $lab alerts send deep_compare_failed -m "Deep compare fallo para $ticker (exit=$code)" --severity warning *>> $log
    exit 1
}

Write-Log "Deep compare OK"
& $lab alerts heartbeat *>> $log
exit 0
