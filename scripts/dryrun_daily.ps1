# Dry-run diario de los bots habilitados (semana laborable, tras el cierre de EE.UU.).
# No envía órdenes: solo calcula señales y las guarda en logs y data\dryrun.
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

$root = "E:\trading-lab"
Set-Location $root

$logDir = Join-Path $root "logs\dryrun"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $logDir "dryrun_$stamp.log"

& ".\.venv\Scripts\lab.exe" orchestrate --dry-run *> $log
$code = $LASTEXITCODE

if ($code -ne 0) {
    Add-Content -Path $log -Value "EXIT=$code"
}
exit $code
