# Arranque silencioso del panel web (tarea programada al iniciar sesión).
# No abre el navegador: la consola queda disponible en http://127.0.0.1:8420
$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"

$root = "E:\trading-lab"
Set-Location $root

$logDir = Join-Path $root "logs\web"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "server.log"

& ".\.venv\Scripts\lab.exe" web --no-open *>&1 | Out-File -FilePath $log -Encoding utf8 -Append
