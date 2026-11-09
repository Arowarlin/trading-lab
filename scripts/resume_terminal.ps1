# Contenido de la terminal que reabre TradingLab tras el reinicio.
# Se lanza con `powershell -File` desde resume_after_reboot.ps1: asi la linea
# de wt.exe no lleva separadores `;` que Windows Terminal interpretaria como
# comandos distintos.
$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"

Set-Location "E:\trading-lab"
Write-Host "Reinicio completado. TradingLab y OpenCode se reabren en la sesion guardada." -ForegroundColor Cyan
Write-Host "WSL: características habilitadas; falta instalar Ubuntu. Guia: docs\reinicio_wsl.md" -ForegroundColor Yellow
opencode --session ses_e5220563affelHrJU9DmgfjCb3
