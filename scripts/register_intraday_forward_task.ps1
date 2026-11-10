# Registra la tarea signal-only del forward intradía.
#
# La tarea despierta cada 5 minutos y el script solo invoca el dry-run una vez
# por barra M15 dentro de las ventanas UTC. No activa bots ni envía órdenes.
$ErrorActionPreference = "Stop"

$root = "E:\trading-lab"
$script = Join-Path $root "scripts\intraday_forward_signal.ps1"
$taskName = "TradingLab-IntradayForward"

if (-not (Test-Path $script)) {
    throw "No existe $script"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $root

# Fase :02/:17/:32/:47 de cada hora, para ejecutar poco después del cierre M15.
$now = Get-Date
$delta = (2 - ($now.Minute % 15) + 15) % 15
if ($delta -eq 0) {
    $delta = 15
}
$start = $now.AddMinutes($delta)
$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At $start `
    -RepetitionInterval (New-TimeSpan -Minutes 5)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 4)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "TradingLab forward intradía signal-only: dry-run una vez por barra M15; sin órdenes." `
    -Force

Write-Output "Tarea registrada: $taskName"
Write-Output "Script: $script"
Write-Output "Inicio: $($start.ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Output "Cadencia: cada 5 min; una pasada por barra M15 dentro de Tokio/Londres UTC"
