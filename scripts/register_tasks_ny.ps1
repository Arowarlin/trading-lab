# Registra las tareas ancladas a la sesion de Nueva York.
#
# Fuente unica: config/schedule.yaml. Las horas `at` estan en America/New_York
# y se convierten a la hora local del PC para la fecha de ejecucion.
#
# Por defecto SOLO LISTA. No registra nada hasta que se pase -Apply.
# -IfChanged: si todas las horas ya coinciden, no toca ninguna tarea.
param(
    [switch]$Apply,
    [switch]$IfChanged,
    [string]$Schedule = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $Schedule) { $Schedule = Join-Path $root "config\schedule.yaml" }
$python = Join-Path $root ".venv\Scripts\python.exe"

function Get-NyTz {
    try { return [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time") }
    catch { return [TimeZoneInfo]::FindSystemTimeZoneById("America/New_York") }
}

function Convert-NyToLocal([string]$Hhmm, [datetime]$Day) {
    $parts = $Hhmm.Split(":")
    $ny = [datetime]::new($Day.Year, $Day.Month, $Day.Day, [int]$parts[0], [int]$parts[1], 0, [DateTimeKind]::Unspecified)
    $utc = [TimeZoneInfo]::ConvertTimeToUtc($ny, (Get-NyTz))
    return [TimeZoneInfo]::ConvertTimeFromUtc($utc, [TimeZoneInfo]::Local)
}

function Get-DayOfWeek([string]$Name) {
    return [System.DayOfWeek]$Name
}

function Get-CurrentStartTimes([string]$Name) {
    $task = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if (-not $task) { return @() }
    return @($task.Triggers | ForEach-Object {
        if ($_.StartBoundary) {
            try { ([datetime]$_.StartBoundary).ToString("HH:mm") } catch { }
        }
    })
}

function Format-Times([object[]]$Times) {
    if (-not $Times -or $Times.Count -eq 0) { return "-" }
    return ($Times -join ", ")
}

if (-not (Test-Path $Schedule)) {
    throw "No existe el calendario: $Schedule"
}
if (-not (Test-Path $python)) {
    throw "No existe el Python del lab: $python"
}

$json = & $python -c "import json,sys,yaml; print(json.dumps(yaml.safe_load(open(sys.argv[1],encoding='utf-8')),ensure_ascii=False))" $Schedule
if ($LASTEXITCODE -ne 0) { throw "No se pudo leer $Schedule" }
$config = $json | ConvertFrom-Json
$today = (Get-Date).Date
$wake = @($config.wake_to_run)

$rows = @()
$plans = @()
foreach ($task in $config.tasks) {
    $current = @(Get-CurrentStartTimes $task.name)
    $expected = @()
    $localTriggers = @()
    foreach ($trigger in $task.triggers) {
        $startLocal = Convert-NyToLocal $trigger.at $today
        $expected += $startLocal.ToString("HH:mm")
        $localTriggers += [pscustomobject]@{
            start = $startLocal
            ny = $trigger.at
            type = if ($trigger.type) { $trigger.type } else { "weekly" }
            end = $trigger.end
            interval = $trigger.interval_minutes
            days = $trigger.days
            duration_days = $trigger.duration_days
            duration_hours = $trigger.duration_hours
        }
    }
    $currentText = Format-Times $current
    $expectedText = Format-Times $expected
    $nyText = (($task.triggers | ForEach-Object { $_.at }) -join ", ")
    $endLocal = $null
    if ($task.triggers.Count -eq 1 -and $task.triggers[0].type -eq "repetition") {
        $t = $task.triggers[0]
        if ($t.end) {
            $endLocal = Convert-NyToLocal $t.end $today
            $currentText = "$($currentText)-$($endLocal.ToString('HH:mm'))"
            $expectedText = "$($expectedText)-$($endLocal.ToString('HH:mm'))"
            $nyText = "$($t.at)-$($t.end)"
        }
    }
    $current = @($current | Select-Object -Unique)
    $currentText = Format-Times $current
    if ($endLocal) { $currentText = "$($currentText)-$($endLocal.ToString('HH:mm'))" }
    $rows += [pscustomobject]@{
        Tarea = $task.name
        NY = $nyText
        Actual = $currentText
        Corregida = $expectedText
        Cambia = if (($current -join ",") -eq ($expected -join ",")) { "no" } else { "si" }
        WakeToRun = if ($wake -contains $task.name) { "true" } else { "false" }
    }
    $plans += [pscustomobject]@{
        task = $task
        triggers = $localTriggers
        current = $current
        expected = $expected
    }
}

foreach ($name in $wake) {
    if ($plans | Where-Object { $_.task.name -eq $name }) { continue }
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $task) { continue }
    $times = @(Get-CurrentStartTimes $name)
    $rows += [pscustomobject]@{
        Tarea = $name
        NY = "-"
        Actual = (Format-Times $times)
        Corregida = (Format-Times $times)
        Cambia = "solo WakeToRun"
        WakeToRun = "true"
    }
}

$maintenance = $config.maintenance
if ($maintenance) {
    $exists = Get-ScheduledTask -TaskName $maintenance.name -ErrorAction SilentlyContinue
    $actual = if ($exists) { "existe" } else { "nueva" }
    $cambia = if ($exists) { "revisar" } else { "nueva" }
    $days = ($maintenance.days -join ",")
    $rows += [pscustomobject]@{
        Tarea = $maintenance.name
        NY = "-"
        Actual = $actual
        Corregida = "$days $($maintenance.at) local"
        Cambia = $cambia
        WakeToRun = "false"
    }
}

$rows | Format-Table -AutoSize
Write-Output ""
Write-Output "Hoy local: $($today.ToString('yyyy-MM-dd')) - zona local: $([TimeZoneInfo]::Local.Id) - NY: $((Get-NyTz).Id)"
Write-Output "Modo: $(if ($Apply) { 'APLICAR' } else { 'SOLO LISTA (no registra nada)' })"

if (-not $Apply) { exit 0 }

$changed = @($plans | Where-Object { ($_.current -join ",") -ne ($_.expected -join ",") })
$wakeMissing = @($wake | Where-Object {
    $t = Get-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue
    $t -and (-not $t.Settings.WakeToRun)
})
if ($IfChanged -and $changed.Count -eq 0 -and $wakeMissing.Count -eq 0) {
    Write-Output "Sin cambios: las horas y WakeToRun ya coinciden."
    exit 0
}

foreach ($plan in $plans) {
    $task = $plan.task
    $name = $task.name
    $currentTask = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($name -eq "TradingLab-AI-Scalp") {
        Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        schtasks /end /tn $name 2>$null | Out-Null
    }
    $scriptPath = Join-Path $root $task.script
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" $($task.args)" `
        -WorkingDirectory $root
    $triggers = @()
    foreach ($local in $plan.triggers) {
        $days = @($local.days | ForEach-Object { Get-DayOfWeek $_ })
        if ($local.type -eq "repetition") {
            if ($local.end) {
                $endLocal = Convert-NyToLocal $local.end $today
                $duration = $endLocal - $local.start
            } else {
                $duration = New-TimeSpan -Days ([int]$local.duration_days) -Hours ([int]$local.duration_hours)
            }
            $once = New-ScheduledTaskTrigger -Once -At ((Get-Date).Date.AddDays(1)) `
                -RepetitionInterval (New-TimeSpan -Minutes ([int]$local.interval)) `
                -RepetitionDuration $duration
            $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $local.start
            $trigger.Repetition = $once.Repetition
        } else {
            $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $local.start
        }
        $triggers += $trigger
    }
    if ($currentTask) {
        $settings = $currentTask.Settings
        $principal = $currentTask.Principal
        $description = $currentTask.Description
    } else {
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
        $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
        $description = "TradingLab: tarea re-registrada desde config/schedule.yaml"
    }
    $settings.WakeToRun = [bool]($wake -contains $name)
    if ($task.multiple_instances -eq "IgnoreNew") {
        $settings.MultipleInstances = "IgnoreNew"
    }
    if ($task.execution_limit_minutes) {
        $settings.ExecutionTimeLimit = "PT$([int]$task.execution_limit_minutes)M"
    }
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $triggers `
        -Settings $settings -Principal $principal -Description $description -Force | Out-Null
    Write-Output "Actualizada: $name"
}

foreach ($name in $wake) {
    if ($plans | Where-Object { $_.task.name -eq $name }) { continue }
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $task) { continue }
    $settings = $task.Settings
    $settings.WakeToRun = $true
    Set-ScheduledTask -TaskName $name -Settings $settings | Out-Null
    Write-Output "WakeToRun=true: $name"
}

if ($maintenance) {
    $scriptPath = Join-Path $root $maintenance.script
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" $($maintenance.args)" `
        -WorkingDirectory $root
    $days = @($maintenance.days | ForEach-Object { Get-DayOfWeek $_ })
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $maintenance.at
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
    Register-ScheduledTask -TaskName $maintenance.name -Action $action -Trigger $trigger `
        -Settings $settings -Description $maintenance.description -Force | Out-Null
    Write-Output "Mantenimiento: $($maintenance.name) domingo $($maintenance.at) local"
}

Write-Output "Listo. No se inicio ninguna tarea ni se activo ningun bot."
