# Reabre Windows Terminal y la sesión exacta de OpenCode tras el reinicio.
# Se ejecuta una sola vez mediante la tarea TradingLab-Resume (AtLogOn).
$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"

$root = "E:\trading-lab"
$session = "ses_e5220563affelHrJU9DmgfjCb3"
$logDir = Join-Path $root "logs\resume"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("resume_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

function Write-Log([string]$Message) {
    Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message) -Encoding utf8
}

Write-Log "Resume task start"
Start-Sleep -Seconds 20

$command = "Set-Location '$root'; Write-Host 'Reinicio completado. TradingLab y OpenCode se reabren en la sesion guardada.' -ForegroundColor Cyan; Write-Host 'WSL: características habilitadas; falta instalar Ubuntu. Guia: docs\reinicio_wsl.md' -ForegroundColor Yellow; opencode --session $session"
$wt = Get-Command wt.exe -ErrorAction SilentlyContinue
if ($wt) {
    Write-Log "Abriendo Windows Terminal"
    Start-Process -FilePath $wt.Source -ArgumentList "new-tab -d `"$root`" powershell.exe -NoExit -NoProfile -Command `"$command`""
} else {
    Write-Log "wt.exe no disponible; abriendo PowerShell"
    Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit", "-NoProfile", "-Command", $command
}

Start-Sleep -Seconds 5
try {
    Unregister-ScheduledTask -TaskName "TradingLab-Resume" -Confirm:$false -ErrorAction Stop
    Write-Log "Tarea TradingLab-Resume eliminada tras abrir la terminal"
} catch {
    Write-Log "No se pudo eliminar la tarea: $($_.Exception.Message)"
}
Write-Log "Resume task end"
