# Informe pre-market nativo con Qwen local. NO usa Trading-R1 ni envia ordenes.
# Genera Markdown y lo envia al chat autorizado de Telegram.
param(
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"

$root = "E:\trading-lab"
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$logDir = Join-Path $root "logs\premarket"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $logDir "premarket_$stamp.log"
$report = Join-Path $logDir "premarket_$stamp.md"

Set-Location $root
Add-Content -Path $log -Value ("{0} premarket start" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) -Encoding utf8

if (-not (Test-Path $lab)) {
    Add-Content -Path $log -Value "No existe $lab" -Encoding utf8
    exit 1
}

if ($PreflightOnly) {
    & $lab premarket --no-llm --out $report *>> $log
    Add-Content -Path $log -Value "PreflightOnly: fin sin LLM ni Telegram." -Encoding utf8
    exit $LASTEXITCODE
}

& $lab premarket --send --out $report *>> $log
$code = $LASTEXITCODE
if ($code -ne 0) {
    & $lab alerts send premarket_failed -m "El pre-market fallo con codigo $code" --severity warning *>> $log
    exit $code
}

& $lab alerts heartbeat *>> $log
Add-Content -Path $log -Value "premarket OK" -Encoding utf8
exit 0
