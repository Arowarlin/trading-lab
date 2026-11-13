# Prepara la tarea TradingLab-Heartbeat. NO la registra: el operador debe
# ejecutar este script y aceptar el UAC si quiere programarla.
#
# Cada 5 minutos, con el usuario actual y solo con sesión iniciada. El script
# heartbeat_pc.ps1 comprueba MT5 y SQLite antes de hacer el ping.
$ErrorActionPreference = "Stop"

$root = "E:\trading-lab"
$script = Join-Path $root "scripts\heartbeat_pc.ps1"
if (-not (Test-Path $script)) { throw "No existe $script" }

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
$principal = New-ScheduledTaskPrincipal -UserId $user `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName "TradingLab-Heartbeat" -Action $action `
    -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "TradingLab latido PC: MT5 + SQLite, sin órdenes." -Force | Out-Null
Write-Output "Registrada: TradingLab-Heartbeat (cada 5 min, usuario $user)"
