# Registra la comparacion nocturna lite vs deep. NO se ejecuta desde el laboratorio.
# El usuario debe revisar y ejecutar este script manualmente cuando toque.
# Horario: todos los dias a las 02:30 hora local (Praga), fuera de mercado.
$ErrorActionPreference = "Stop"

$root = "E:\trading-lab"
$script = Join-Path $root "scripts\deep_compare_nightly.ps1"
$taskName = "TradingLab-DeepCompare"

if (-not (Test-Path $script)) {
    throw "No existe $script"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger -Daily -At "02:30"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 8)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "TradingLab: comparacion nocturna lite vs deep; solo mide, no envia ordenes ni activa bots." `
    -Force

Write-Output "Tarea registrada: $taskName"
Write-Output "Script: $script"
Write-Output "Horario: diario 02:30 hora local (Praga)"
