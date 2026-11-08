# Job semanal de lecciones: Qwen solo redacta propuestas.
# No aprueba, no aplica, no activa bots y no envía órdenes.
$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"

$root = "E:\trading-lab"
Set-Location $root

$logDir = Join-Path $root "logs\lessons"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("lessons_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

& ".\.venv\Scripts\lab.exe" lessons weekly *>> $log
if ($LASTEXITCODE -ne 0) {
    & ".\.venv\Scripts\lab.exe" alerts send lessons_weekly_failed `
        -m "Fallo el job semanal de lecciones; revisa logs/lessons." `
        --severity warning *>> $log
    exit 1
}
& ".\.venv\Scripts\lab.exe" alerts heartbeat *>> $log
exit 0
