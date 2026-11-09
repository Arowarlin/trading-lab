# Espera a que termine la descarga del MoE y programa el reinicio para WSL.
# No reinicia si el modelo no aparece; deja rastro en logs/resume.
$ErrorActionPreference = "Continue"
$root = "E:\trading-lab"
$logDir = Join-Path $root "logs\resume"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "reboot_after_download.log"

function Write-Log([string]$Message) {
    Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message) -Encoding utf8
}

$lms = Join-Path $env:LOCALAPPDATA "Programs\LM Studio\resources\app\.webpack\lms.exe"
$deadline = (Get-Date).AddHours(4)
Write-Log "Watcher start"

while ((Get-Date) -lt $deadline) {
    $running = Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -match 'lms(\.exe)? get qwen/qwen3-30b-a3b' }
    if (-not $running) {
        break
    }
    Start-Sleep -Seconds 60
}

if (-not (Test-Path $lms)) {
    Write-Log "No existe lms.exe; no se reinicia"
    exit 1
}

$list = (& $lms ls 2>&1 | Out-String)
if ($list -notmatch 'qwen3-30b-a3b') {
    Write-Log "Descarga terminada pero el modelo no aparece; no se reinicia"
    exit 1
}

Write-Log "Modelo MoE presente; programando reinicio en 120 s"
& shutdown.exe /r /t 120 /c "TradingLab: reinicio para WSL. Backup verificado. La terminal se reabre al iniciar sesion."
Write-Log "Reboot scheduled; ejecuta shutdown /a para cancelar"
