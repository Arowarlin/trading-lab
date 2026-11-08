# Registra el puente Telegram para que arranque al iniciar sesión Windows.
# No requiere administrador y no se ejecuta automáticamente.
$ErrorActionPreference = "Stop"

$root = "E:\trading-lab"
$script = Join-Path $root "scripts\telegram_bridge.ps1"
$taskName = "TradingLab-Telegram"

if (-not (Test-Path $script)) {
    throw "No existe $script"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 30)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Puente Telegram de TradingLab (long polling, solo paper)" `
    -Force | Out-Null

Write-Host "Tarea registrada: $taskName"
Write-Host "Iníciala ahora con: Start-ScheduledTask -TaskName $taskName"
Write-Host "Estado: Get-ScheduledTaskInfo -TaskName $taskName"
Write-Host "Para quitarla: Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"
