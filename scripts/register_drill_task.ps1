# Registra la tarea mensual del simulacro R8.
#
# NO se ejecuta sin autorización: el simulacro cancela órdenes y cierra
# posiciones, así que solo se registra cuando el usuario lo pide.
param(
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

$root = "E:\trading-lab"
$script = Join-Path $root "scripts\drill_monthly.ps1"
$taskName = "TradingLab-Drill"

if (-not (Test-Path $script)) {
    throw "No existe el script: $script"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument (
    "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -Confirm"
)
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

if ($WhatIf) {
    Write-Output "WhatIf: se registraria la tarea $taskName (domingo 03:00)."
    Write-Output "No se registra nada sin autorización explicita."
    exit 0
}

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Simulacro de emergencia R8 en paper/demo" -Force | Out-Null
Write-Output "Tarea registrada: $taskName (domingo 03:00)"
