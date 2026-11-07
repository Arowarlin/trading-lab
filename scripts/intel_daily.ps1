# Ingesta diaria de noticias RSS (solo lectura, sin ejecución).
# Sanea el texto, deduplica y guarda en SQLite. No activa ningún bot.
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

$root = "E:\trading-lab"
Set-Location $root

$logDir = Join-Path $root "logs\intel"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("intel_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

& ".\.venv\Scripts\lab.exe" intel fetch *> $log
$code = $LASTEXITCODE
if ($code -ne 0) {
    & ".\.venv\Scripts\lab.exe" alerts send intel_failed -m "La ingesta RSS falló con código $code" --severity warning *>> $log
} else {
    & ".\.venv\Scripts\lab.exe" alerts heartbeat *>> $log
}
exit $code
