# Registra las tareas CFD/futuros reconvertidas de TradingLab.
#
# NO se ejecuta automáticamente: el operador lo revisa y lo lanza cuando quiera.
# Sin elevación: usuario actual y solo con sesión iniciada. No activa bots ni
# envía órdenes; solo registra tareas de briefing, inteligencia y agentes.
#
# Horas ancla:
#   * Londres 07:30 Europe/London  -> briefing pre-Londres
#   * Nueva York 09:00 America/New_York -> briefing pre-NY
#   * Resto de tareas, antes de la sesión de Londres.
#
# Aviso: `TradingLab-ScheduleTZ` re-registra a diario las tareas que siguen en
# config/schedule.yaml. Si esa tarea sigue habilitada, volverá a poner las horas
# antiguas (Premarket 07:45 NY, Agents, Intel...). Antes de ejecutar este
# script, el operador debe deshabilitar `TradingLab-ScheduleTZ` o actualizar
# config/schedule.yaml con aprobación explícita (requiere administrador).
param(
    [switch]$List,
    [switch]$DisableLegacy
)

$ErrorActionPreference = "Stop"
$root = "E:\trading-lab"

function Get-AnchorLocalTime {
    param([string]$Anchor, [string]$Hhmm)
    $map = @{
        "America/New_York" = "Eastern Standard Time"
        "Europe/London" = "GMT Standard Time"
    }
    $id = if ($map.ContainsKey($Anchor)) { $map[$Anchor] } else { $Anchor }
    $tz = [TimeZoneInfo]::FindSystemTimeZoneById($id)
    $parts = $Hhmm.Split(":")
    $today = (Get-Date).Date
    $when = [datetime]::new($today.Year, $today.Month, $today.Day, [int]$parts[0], [int]$parts[1], 0)
    $utc = [TimeZoneInfo]::ConvertTimeToUtc($when, $tz)
    return [TimeZoneInfo]::ConvertTimeFromUtc($utc, [TimeZoneInfo]::Local).ToString("HH:mm")
}

function Register-LabTask {
    param(
        [string]$Name,
        [string]$Script,
        [string]$Arguments = "",
        [string]$Anchor,
        [string]$At,
        [string]$Description
    )
    $path = Join-Path $root $Script
    if (-not (Test-Path $path)) { throw "No existe $path" }
    $local = Get-AnchorLocalTime -Anchor $Anchor -Hhmm $At
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$path`" $Arguments" `
        -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -Weekly `
        -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $local
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    if ($List) {
        Write-Output ("[list] {0} -> {1} ({2} {3})" -f $Name, $local, $Anchor, $At)
        return
    }
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger `
        -Settings $settings -Description $Description -Force | Out-Null
    Write-Output ("registrada: {0} -> {1} local ({2} {3})" -f $Name, $local, $Anchor, $At)
}

# Briefing pre-Londres y pre-NY (mismo script, dos ventanas).
Register-LabTask -Name "TradingLab-Briefing-London" -Script "scripts\premarket_daily.ps1" `
    -Arguments "-Session pre_london" -Anchor "Europe/London" -At "07:30" `
    -Description "TradingLab: briefing pre-Londres del universo CFD; solo lectura."
Register-LabTask -Name "TradingLab-Briefing-NY" -Script "scripts\premarket_daily.ps1" `
    -Arguments "-Session pre_ny" -Anchor "America/New_York" -At "09:00" `
    -Description "TradingLab: briefing pre-NY del universo CFD; solo lectura."

# Inteligencia y agentes LLM reconvertidos (solo análisis, nunca órdenes).
Register-LabTask -Name "TradingLab-Intel" -Script "scripts\intel_daily.ps1" `
    -Anchor "Europe/London" -At "06:30" `
    -Description "TradingLab: noticias y calendario CFD/futuros; solo lectura."
Register-LabTask -Name "TradingLab-Agents" -Script "scripts\agents_daily.ps1" `
    -Anchor "Europe/London" -At "07:00" `
    -Description "TradingLab: análisis lite del universo CFD; no envía órdenes."
Register-LabTask -Name "TradingLab-LLMCompare" -Script "scripts\llm_compare_daily.ps1" `
    -Anchor "Europe/London" -At "06:00" `
    -Description "TradingLab: comparación de modelos LLM; no envía órdenes."
Register-LabTask -Name "TradingLab-DeepCompare" -Script "scripts\deep_compare_nightly.ps1" `
    -Anchor "Europe/London" -At "22:30" `
    -Description "TradingLab: comparación lite vs deep; no envía órdenes."

# Tareas del carril de acciones/ETF: solo se deshabilitan si el operador lo pide.
if ($DisableLegacy) {
    foreach ($name in @("TradingLab-F13", "TradingLab-OrchestrateSPY", "TradingLab-DryRun", "TradingLab-Premarket")) {
        try {
            Disable-ScheduledTask -TaskName $name -ErrorAction Stop | Out-Null
            Write-Output "deshabilitada: $name"
        } catch {
            Write-Output "no se pudo deshabilitar $name : $($_.Exception.Message)"
        }
    }
}

Write-Output ""
Write-Output "Recordatorio: deshabilita TradingLab-ScheduleTZ o actualiza config/schedule.yaml;"
Write-Output "si sigue activa, re-registrará las horas antiguas cada día."
