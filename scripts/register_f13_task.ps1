# Registra la tarea F13. NO se ejecuta desde el laboratorio.
# El usuario debe revisar y ejecutar este script manualmente cuando toque.
# Horario: L-V 22:20 hora local de Praga (despues del cierre de EE. UU.).
$ErrorActionPreference = "Stop"

$root = "E:\trading-lab"
$script = Join-Path $root "scripts\f13_daily.ps1"
$taskName = "TradingLab-F13"

if (-not (Test-Path $script)) {
    throw "No existe $script"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "22:20"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "TradingLab F13: orquestar qqq-trend-f13, reconcile y f13 check. Paper; no activa el bot." `
    -Force

Write-Output "Tarea registrada: $taskName"
Write-Output "Script: $script"
Write-Output "Horario: L-V 22:20 hora local (Praga)"
