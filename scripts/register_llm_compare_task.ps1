# Registra la comparacion diaria MoE 30B vs modelo actual en lite.
# No cambia el modelo por defecto ni envia ordenes.
$ErrorActionPreference = "Stop"

$root = "E:\trading-lab"
$script = Join-Path $root "scripts\llm_compare_daily.ps1"
$taskName = "TradingLab-LLMCompare"

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
    -At "18:30"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "TradingLab: comparacion diaria MoE 30B vs actual en lite; sin ordenes." `
    -Force

Write-Output "Tarea registrada: $taskName"
Write-Output "Script: $script"
Write-Output "Horario: L-V 18:30 hora local"
