# Registra la reapertura única de Windows Terminal + OpenCode tras el reinicio.
# La tarea se elimina sola después de abrir la sesión.
$ErrorActionPreference = "Stop"

$root = "E:\trading-lab"
$script = Join-Path $root "scripts\resume_after_reboot.ps1"
$taskName = "TradingLab-Resume"

if (-not (Test-Path $script)) {
    throw "No existe $script"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "TradingLab: reabrir Windows Terminal y la sesión OpenCode tras el reinicio." `
    -Force

Write-Output "Tarea registrada: $taskName"
Write-Output "Se ejecutará al iniciar sesión y se eliminará después."
