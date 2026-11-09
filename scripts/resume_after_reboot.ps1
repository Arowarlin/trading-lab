# Reabre Windows Terminal y la sesion exacta de OpenCode tras el reinicio.
# Se ejecuta al iniciar sesion, como maximo una vez por arranque.
$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"

$root = "E:\trading-lab"
$terminalScript = Join-Path $root "scripts\resume_terminal.ps1"
$logDir = Join-Path $root "logs\resume"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("resume_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

function Write-Log([string]$Message) {
    Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message) -Encoding utf8
}

$bootTime = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString("o")
$bootMarker = Join-Path $logDir "last_boot.txt"
$lastBoot = ""
if (Test-Path $bootMarker) {
    $lastBoot = [string](Get-Content $bootMarker -Raw)
}
if ($lastBoot.Trim() -eq $bootTime) {
    Write-Log "Ya se reabrio la sesion en este arranque ($bootTime); saliendo"
    exit 0
}

Write-Log "Resume task start (boot $bootTime)"
Start-Sleep -Seconds 20

$wt = Get-Command wt.exe -ErrorAction SilentlyContinue
try {
    if ($wt) {
        Write-Log "Abriendo Windows Terminal"
        $wtArgs = "new-tab -d `"$root`" powershell.exe -NoExit -NoProfile -ExecutionPolicy Bypass -File `"$terminalScript`""
        Start-Process -FilePath $wt.Source -ArgumentList $wtArgs
    } else {
        Write-Log "wt.exe no disponible; abriendo PowerShell"
        Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit -NoProfile -ExecutionPolicy Bypass -File `"$terminalScript`""
    }
    Set-Content -Path $bootMarker -Value $bootTime -Encoding utf8
} catch {
    Write-Log "No se pudo abrir la terminal: $($_.Exception.Message)"
    exit 1
}

Write-Log "Resume task end"
