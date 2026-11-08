# F13 diario: orquestar qqq-trend-f13, reconciliar y comprobar.
# NO se registra automaticamente. Requiere F13 congelado y el bot enabled:true.
# Los cierres/reducciones siempre estan permitidos; las aperturas pasan por
# kill-switch, calendario/blackout, sesion y guard.
param(
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"

$root = "E:\trading-lab"
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$logDir = Join-Path $root "logs\f13"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $logDir "f13_$stamp.log"

function Write-Log([string]$Message) {
    Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message) -Encoding utf8
}

function Run-Step([string]$Label, [string[]]$Arguments) {
    Write-Log "INICIO $Label"
    & $lab @Arguments *>> $log
    $code = $LASTEXITCODE
    Write-Log "FIN $Label exit=$code"
    return $code
}

Set-Location $root
Write-Log "F13 daily start"

# Preflight: no ejecutar nada si F13 no esta congelado/iniciado.
$statusText = (& $lab f13 status 2>&1 | Out-String)
Add-Content -Path $log -Value $statusText -Encoding utf8
if ($statusText -match "no iniciado") {
    Write-Log "F13 no iniciado; no se ejecuta el bot. Congela y activa manualmente."
    exit 0
}
if ($PreflightOnly) {
    Write-Log "PreflightOnly: fin sin ejecutar el bot."
    exit 0
}

$codes = @()
$codes += Run-Step "orchestrate dry-run" @("orchestrate", "--bot", "qqq-trend-f13", "--dry-run")
$codes += Run-Step "orchestrate qqq-trend-f13" @("orchestrate", "--bot", "qqq-trend-f13")
$codes += Run-Step "reconcile" @("reconcile")
$codes += Run-Step "f13 check" @("f13", "check")
$codes += Run-Step "f13 report" @("f13", "report")

$failed = @($codes | Where-Object { $_ -ne 0 })
if ($failed.Count -gt 0) {
    Write-Log "F13 daily FAILED codes=$($codes -join ',')"
    & $lab alerts send f13_daily_failed -m "F13 daily fallo codigos $($codes -join ',')" --severity error *>> $log
    exit 1
}

Write-Log "F13 daily OK"
& $lab alerts heartbeat *>> $log
exit 0
