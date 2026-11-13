# F13 diario: orquestar qqq-trend-f13, reconciliar y comprobar.
# NO se registra automaticamente. Requiere F13 congelado y el bot enabled:true.
# Los cierres/reducciones siempre estan permitidos; las aperturas pasan por
# kill-switch, calendario/blackout, sesion y guard.
param(
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

$root = "E:\trading-lab"
. (Join-Path $PSScriptRoot "heartbeat_task.ps1")
Send-TaskHeartbeat -Root $root -Check "f13" -Status "start"
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$logDir = Join-Path $root "logs\f13"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $logDir "f13_$stamp.log"

function Write-Log([string]$Message) {
    Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message) -Encoding utf8
}

function Invoke-Lab([string[]]$Arguments) {
    $output = & $lab @Arguments 2>&1
    $code = $LASTEXITCODE
    $output | Out-File -FilePath $log -Encoding utf8 -Append
    return $code
}

function Run-Step([string]$Label, [string[]]$Arguments) {
    Write-Log "INICIO $Label"
    $code = Invoke-Lab $Arguments
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
    Send-TaskHeartbeat -Root $root -Check "f13" -Status "ok"
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
    $null = Invoke-Lab @(
        "alerts", "send", "f13_daily_failed",
        "-m", "F13 daily fallo codigos $($codes -join ',')",
        "--severity", "error"
    )
    Send-TaskHeartbeat -Root $root -Check "f13" -Status "fail"
    exit 1
}

Write-Log "F13 daily OK"
Send-TaskHeartbeat -Root $root -Check "f13" -Status "ok"
exit 0
