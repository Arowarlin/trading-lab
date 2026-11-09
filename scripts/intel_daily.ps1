# Ingesta diaria de noticias (solo lectura, sin ejecución).
# Sanea el texto, deduplica y guarda en SQLite. No activa ningún bot.
# -Finnhub y -Score son opt-in; la tarea registrada actual no los usa.
param(
    [switch]$Finnhub,
    [switch]$Score
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

$root = "E:\trading-lab"
Set-Location $root

$logDir = Join-Path $root "logs\intel"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("intel_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

& ".\.venv\Scripts\lab.exe" intel fetch *>> $log
$code = $LASTEXITCODE

if ($Finnhub) {
    & ".\.venv\Scripts\lab.exe" intel finnhub --limit 20 *>> $log
    if ($LASTEXITCODE -ne 0) {
        & ".\.venv\Scripts\lab.exe" alerts send intel_finnhub_failed -m "Finnhub falló con código $LASTEXITCODE" --severity warning *>> $log
        $code = 1
    }
}

if ($Score) {
    & ".\.venv\Scripts\lab.exe" intel score --limit 20 --batch-size 4 *>> $log
    if ($LASTEXITCODE -ne 0) {
        & ".\.venv\Scripts\lab.exe" alerts send intel_score_failed -m "Scoring de noticias falló con código $LASTEXITCODE" --severity warning *>> $log
        $code = 1
    }
}

if ($code -ne 0) {
    & ".\.venv\Scripts\lab.exe" alerts send intel_failed -m "La ingesta de noticias falló con código $code" --severity warning *>> $log
} else {
    & ".\.venv\Scripts\lab.exe" alerts heartbeat *>> $log
}
exit $code
