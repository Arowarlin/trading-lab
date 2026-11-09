# Registra el pre-market nativo con Qwen. NO se ejecuta desde el laboratorio.
# Horario: L-V 07:45 hora local de Praga, antes de la apertura de EE. UU.
$ErrorActionPreference = "Stop"

$root = "E:\trading-lab"
$script = Join-Path $root "scripts\premarket_daily.ps1"
$taskName = "TradingLab-Premarket"

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
    -At "07:45"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "TradingLab: informe pre-market nativo con Qwen y Telegram; sin ordenes." `
    -Force

Write-Output "Tarea registrada: $taskName"
Write-Output "Script: $script"
Write-Output "Horario: L-V 07:45 hora local (Praga)"
