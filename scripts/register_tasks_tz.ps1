# Registra las tareas TradingLab desde config/schedule.yaml.
#
# Cada tarea declara su zona de anclaje: America/New_York, Europe/London o
# local. Las horas `at` se convierten a la hora local del PC para la fecha de
# ejecucion. `local` se deja tal cual.
#
# Por defecto SOLO LISTA. No registra nada hasta que se pase -Apply.
# -IfChanged: si las horas, los triggers y WakeToRun ya coinciden, no toca nada.
param(
    [switch]$Apply,
    [switch]$IfChanged,
    [string]$Schedule = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $Schedule) { $Schedule = Join-Path $root "config\schedule.yaml" }
$python = Join-Path $root ".venv\Scripts\python.exe"

function Get-AnchorTimeZone([string]$Anchor) {
    if (-not $Anchor -or $Anchor -eq "local") { return $null }
    $map = @{
        "America/New_York" = "Eastern Standard Time"
        "Europe/London" = "GMT Standard Time"
    }
    $id = $Anchor
    if ($map.ContainsKey($Anchor)) { $id = $map[$Anchor] }
    try { return [TimeZoneInfo]::FindSystemTimeZoneById($id) }
    catch { throw "Zona no disponible: $Anchor" }
}

function Convert-AnchorToLocal([string]$Hhmm, [datetime]$Day, [string]$Anchor) {
    $tz = Get-AnchorTimeZone $Anchor
    if ($null -eq $tz) { return $Hhmm }
    $parts = $Hhmm.Split(":")
    $when = [datetime]::new($Day.Year, $Day.Month, $Day.Day, [int]$parts[0], [int]$parts[1], 0, [DateTimeKind]::Unspecified)
    $utc = [TimeZoneInfo]::ConvertTimeToUtc($when, $tz)
    return [TimeZoneInfo]::ConvertTimeFromUtc($utc, [TimeZoneInfo]::Local).ToString("HH:mm")
}

function Convert-IsoDuration([string]$Value) {
    if (-not $Value) { return $null }
    try { return [System.Xml.XmlConvert]::ToTimeSpan($Value) }
    catch { return $null }
}

function Format-Span($Span) {
    if ($null -eq $Span) { return "-" }
    $total = [int][math]::Floor($Span.TotalMinutes)
    $days = [int][math]::Floor($total / 1440)
    $hours = [int][math]::Floor(($total % 1440) / 60)
    $minutes = $total % 60
    if ($days -gt 0) {
        if ($hours -eq 0 -and $minutes -eq 0) { return "$($days)d" }
        return "$($days)d $($hours)h $($minutes)m"
    }
    if ($hours -gt 0) { return "$($hours)h $($minutes)m" }
    return "$($minutes)m"
}

function Format-DayName([datetime]$Day) {
    switch ($Day.DayOfWeek) {
        "Sunday" { return "dom" }
        "Monday" { return "lun" }
        "Tuesday" { return "mar" }
        "Wednesday" { return "mie" }
        "Thursday" { return "jue" }
        "Friday" { return "vie" }
        "Saturday" { return "sab" }
    }
    return "-"
}

function Format-DayMask([int]$Mask) {
    if ($Mask -eq 0) { return "diario" }
    if ($Mask -eq 62) { return "L-V" }
    if ($Mask -eq 127) { return "todos" }
    $names = @()
    if ($Mask -band 1) { $names += "dom" }
    if ($Mask -band 2) { $names += "lun" }
    if ($Mask -band 4) { $names += "mar" }
    if ($Mask -band 8) { $names += "mie" }
    if ($Mask -band 16) { $names += "jue" }
    if ($Mask -band 32) { $names += "vie" }
    if ($Mask -band 64) { $names += "sab" }
    return ($names -join ",")
}

function Get-Days($Days) {
    if ($null -eq $Days) { return @() }
    if ($Days -is [string]) {
        if ($Days -eq "weekdays") {
            return @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
        }
        return @($Days)
    }
    return @($Days)
}

function Get-DayMask($Days) {
    $mask = 0
    foreach ($d in (Get-Days $Days)) {
        switch ([string]$d) {
            "Sunday" { $mask = $mask -bor 1 }
            "Monday" { $mask = $mask -bor 2 }
            "Tuesday" { $mask = $mask -bor 4 }
            "Wednesday" { $mask = $mask -bor 8 }
            "Thursday" { $mask = $mask -bor 16 }
            "Friday" { $mask = $mask -bor 32 }
            "Saturday" { $mask = $mask -bor 64 }
        }
    }
    return $mask
}

function Get-DayOfWeek([string]$Name) {
    return [System.DayOfWeek]$Name
}

function Get-CurrentTriggers([string]$Name) {
    $task = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if (-not $task) { return @() }
    $out = @()
    foreach ($t in @($task.Triggers)) {
        $start = $null
        if ($t.StartBoundary) {
            try { $start = [datetime]$t.StartBoundary } catch { $start = $null }
        }
        $interval = $null
        $duration = $null
        if ($null -ne $t.Repetition) {
            if ($t.Repetition.Interval) { $interval = Convert-IsoDuration ([string]$t.Repetition.Interval) }
            if ($t.Repetition.Duration) { $duration = Convert-IsoDuration ([string]$t.Repetition.Duration) }
        }
        $kind = [string]$t.CimClass.CimClassName
        $out += [pscustomobject]@{
            start = $start
            kind = $kind
            mask = [int]$t.DaysOfWeek
            interval = $interval
            duration = $duration
            weekly = $kind -like "*Weekly*"
        }
    }
    return @($out)
}

function Merge-WeeklyTriggers($Triggers) {
    $groups = @{}
    foreach ($t in @($Triggers)) {
        if (-not $t.weekly -or $null -eq $t.start) { continue }
        $intervalMin = 0
        if ($null -ne $t.interval) { $intervalMin = [int][math]::Round($t.interval.TotalMinutes) }
        $durationMin = 0
        if ($null -ne $t.duration) { $durationMin = [int][math]::Round($t.duration.TotalMinutes) }
        $key = "$($t.start.ToString('HH:mm'))|$intervalMin|$durationMin"
        if (-not $groups.ContainsKey($key)) {
            $groups[$key] = [pscustomobject]@{
                start = $t.start
                mask = 0
                interval = $t.interval
                duration = $t.duration
                weekly = $true
            }
        }
        $groups[$key].mask = $groups[$key].mask -bor $t.mask
    }
    return @($groups.Values)
}

function Get-TriggerSignatures($Triggers, [bool]$WeeklyOnly = $false) {
    $sigs = @()
    foreach ($t in @($Triggers)) {
        if ($WeeklyOnly -and -not $t.weekly) { continue }
        $startText = "-"
        if ($null -ne $t.start) { $startText = $t.start.ToString("HH:mm") }
        $intervalMin = 0
        if ($null -ne $t.interval) { $intervalMin = [int][math]::Round($t.interval.TotalMinutes) }
        $durationMin = 0
        if ($null -ne $t.duration) { $durationMin = [int][math]::Round($t.duration.TotalMinutes) }
        $sigs += "$startText|$($t.mask)|$intervalMin|$durationMin"
    }
    return @($sigs | Sort-Object -Unique)
}

function Format-CurrentTrigger($T) {
    $startText = "-"
    if ($null -ne $T.start) { $startText = $T.start.ToString("HH:mm") }
    $daysText = "diario"
    if ($T.weekly) {
        $daysText = Format-DayMask $T.mask
    } elseif ($T.kind -like "*Daily*") {
        $daysText = "diario"
    } elseif ($T.kind -like "*Time*") {
        if ($null -eq $T.interval -and $null -eq $T.duration) {
            $daysText = "unico"
        } elseif ($null -ne $T.duration -and $T.duration.TotalDays -lt 30) {
            $daysText = "temporal"
        } else {
            $daysText = "continuo"
        }
    }
    $text = "$startText $daysText"
    if ($null -ne $T.interval -and $T.interval.TotalMinutes -gt 0) {
        $text = "$text cada $([int]$T.interval.TotalMinutes)m"
    }
    if ($null -ne $T.duration -and $T.duration.TotalMinutes -gt 0) {
        $text = "$text durante $(Format-Span $T.duration)"
    }
    return $text
}

function Format-CurrentSet($Triggers) {
    $weekly = @(Merge-WeeklyTriggers $Triggers)
    $parts = @()
    if ($weekly.Count -gt 0) {
        $parts += @($weekly | ForEach-Object { Format-CurrentTrigger $_ })
    }
    $others = @($Triggers | Where-Object { -not $_.weekly -and $null -ne $_.start })
    if ($others.Count -gt 0) {
        $parts += @($others | ForEach-Object { Format-CurrentTrigger $_ })
    }
    if ($parts.Count -eq 0) { return "sin trigger" }
    return ($parts -join "; ")
}

function Format-ExpectedTrigger($T) {
    $startText = $T.start.ToString("HH:mm")
    $daysText = Format-DayMask $T.mask
    if ($T.type -eq "repetition") {
        $endText = $T.end.ToString("HH:mm")
        if ($T.end.Date -gt $T.start.Date) {
            return "$startText $daysText cada $($T.intervalMinutes)m durante $($T.spanText)"
        }
        return "$startText-$endText $daysText cada $($T.intervalMinutes)m"
    }
    return "$startText $daysText"
}

function Get-CatchUpTrigger($Config, $Trigger) {
    if (-not $Config.catch_up) { return $null }
    $today = (Get-Date).Date
    $anchor = [string]$Config.anchor
    $daysSinceSunday = [int]$today.DayOfWeek
    $sunday = $today.AddDays(-$daysSinceSunday)
    $startText = Convert-AnchorToLocal ([string]$Trigger.at) $sunday $anchor
    $windowStart = [datetime]::ParseExact("$($sunday.ToString('yyyy-MM-dd')) $startText", "yyyy-MM-dd HH:mm", $null)
    $duration = New-TimeSpan -Days ([int]$Trigger.duration_days) -Hours ([int]$Trigger.duration_hours)
    $windowEnd = $windowStart.Add($duration)
    $now = Get-Date
    if ($now -lt $windowStart -or $now -ge $windowEnd) { return $null }
    $interval = [int]$Trigger.interval_minutes
    $minute = $now.Minute
    $add = ($interval - ($minute % $interval)) % $interval
    $next = $now.Date.AddHours($now.Hour).AddMinutes($minute + $add)
    if ($next -lt $now) { $next = $next.AddMinutes($interval) }
    if ($next -ge $windowEnd) { return $null }
    $remaining = $windowEnd - $next
    if ($remaining.TotalMinutes -lt $interval) { return $null }
    return [pscustomobject]@{
        start = $next
        end = $windowEnd
        interval = $interval
        duration = $remaining
    }
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
$wakeGlobal = @($config.wake_to_run)

$plans = @()
$rows = @()
foreach ($cfg in $config.tasks) {
    $name = [string]$cfg.name
    $managed = $true
    if ($null -ne $cfg.manage) { $managed = [bool]$cfg.manage }
    $anchor = [string]$cfg.anchor
    if (-not $anchor) { $anchor = [string]$config.default_anchor }
    if (-not $anchor) { $anchor = "local" }

    $currentTask = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    $currentTriggers = @(Get-CurrentTriggers $name)
    $currentWeekly = @(Merge-WeeklyTriggers $currentTriggers)
    $currentSigs = @(Get-TriggerSignatures $currentTriggers ([bool]$cfg.catch_up))
    $currentWake = $false
    if ($currentTask) { $currentWake = [bool]$currentTask.Settings.WakeToRun }
    $hasEnabled = $cfg.PSObject.Properties.Name -contains "enabled"
    $desiredEnabled = $null
    if ($hasEnabled) { $desiredEnabled = [bool]$cfg.enabled }
    $stateChanged = $false
    if ($hasEnabled -and -not $desiredEnabled -and $currentTask) {
        if ($currentTask.State -ne "Disabled") { $stateChanged = $true }
    }
    $disabledReason = ""
    if ($hasEnabled -and $cfg.disabled_reason) { $disabledReason = [string]$cfg.disabled_reason }

    $desiredWake = $currentWake
    $hasTaskWake = $cfg.PSObject.Properties.Name -contains "wake_to_run"
    if ($managed) {
        if ($hasTaskWake) { $desiredWake = [bool]$cfg.wake_to_run }
        else { $desiredWake = [bool]($wakeGlobal -contains $name) }
    } elseif ($hasTaskWake) {
        $desiredWake = [bool]$cfg.wake_to_run
    }

    $expectedTriggers = @()
    $expectedSigs = @()
    $triggerChanged = $false
    $corregida = "igual"
    $actual = Format-CurrentSet $currentTriggers
    if ($currentTask -and $currentTask.State -eq "Disabled") {
        $actual = "$actual (Disabled)"
    }
    if (-not $currentTask) { $actual = "nueva" }

    if ($managed) {
        foreach ($trig in @($cfg.triggers)) {
            if ($null -eq $trig -or -not $trig.at) { continue }
            $startText = Convert-AnchorToLocal ([string]$trig.at) $today $anchor
            $startLocal = [datetime]::ParseExact("$($today.ToString('yyyy-MM-dd')) $startText", "yyyy-MM-dd HH:mm", $null)
            $mask = Get-DayMask $trig.days
            $intervalMinutes = 0
            if ($null -ne $trig.interval_minutes) { $intervalMinutes = [int]$trig.interval_minutes }
            $endLocal = $null
            $spanText = ""
            $type = "weekly"
            if ($trig.type -eq "repetition") {
                $type = "repetition"
                if ($trig.end) {
                    $endText = Convert-AnchorToLocal ([string]$trig.end) $today $anchor
                    $endLocal = [datetime]::ParseExact("$($today.ToString('yyyy-MM-dd')) $endText", "yyyy-MM-dd HH:mm", $null)
                    if ($endLocal -le $startLocal) { $endLocal = $endLocal.AddDays(1) }
                } elseif ($null -ne $trig.duration_days) {
                    $hours = 0
                    if ($null -ne $trig.duration_hours) { $hours = [int]$trig.duration_hours }
                    $endLocal = $startLocal.AddDays([int]$trig.duration_days).AddHours($hours)
                }
                if ($null -eq $endLocal) {
                    throw "Repeticion sin fin para $name"
                }
                $spanText = Format-Span ($endLocal - $startLocal)
            }
            $expectedTriggers += [pscustomobject]@{
                start = $startLocal
                end = $endLocal
                mask = $mask
                type = $type
                at = [string]$trig.at
                intervalMinutes = $intervalMinutes
                duration_days = $trig.duration_days
                duration_hours = $trig.duration_hours
                spanText = $spanText
            }
            $durationMin = 0
            if ($null -ne $endLocal) { $durationMin = [int][math]::Round(($endLocal - $startLocal).TotalMinutes) }
            $expectedSigs += "$($startLocal.ToString('HH:mm'))|$mask|$intervalMinutes|$durationMin"
        }
        $expectedSigs = @($expectedSigs | Sort-Object -Unique)
        $triggerChanged = (($currentSigs -join "|") -ne ($expectedSigs -join "|"))
        if ($expectedTriggers.Count -gt 0) {
            $corregida = (@($expectedTriggers | ForEach-Object { Format-ExpectedTrigger $_ }) -join "; ")
        }
    } else {
        $corregida = $actual
    }
    if ($hasEnabled -and -not $desiredEnabled -and -not ($currentTask -and $currentTask.State -eq "Disabled")) {
        $corregida = "$corregida (Disabled)"
    }

    $wakeChanged = ($currentWake -ne $desiredWake)
    $cambia = "no"
    if (-not $currentTask) {
        $cambia = "nueva"
    } elseif ($stateChanged) {
        $cambia = "deshabilitar"
    } elseif ($managed -and $triggerChanged) {
        $cambia = "si"
    } elseif ($wakeChanged) {
        $cambia = "solo WakeToRun"
    } elseif (-not $managed) {
        $cambia = "no (inventario)"
    }
    $wakeText = "$currentWake"
    if ($wakeChanged) { $wakeText = "$currentWake->$desiredWake" }

    $rows += [pscustomobject]@{
        Tarea = $name
        Zona = $anchor
        Actual = $actual
        Corregida = $corregida
        Cambia = $cambia
        WakeToRun = $wakeText
    }
    $plans += [pscustomobject]@{
        name = $name
        config = $cfg
        managed = $managed
        exists = [bool]$currentTask
        currentTask = $currentTask
        currentWake = $currentWake
        desiredWake = $desiredWake
        triggerChanged = $triggerChanged
        wakeChanged = $wakeChanged
        stateChanged = $stateChanged
        disabledReason = $disabledReason
        expectedTriggers = $expectedTriggers
    }
}

$declared = @($config.tasks | ForEach-Object { [string]$_.name })
if ($config.maintenance -and $config.maintenance.name) {
    $declared += [string]$config.maintenance.name
}
$extras = @(Get-ScheduledTask -TaskName "TradingLab-*" -ErrorAction SilentlyContinue | Where-Object { $declared -notcontains $_.TaskName })
foreach ($extra in $extras) {
    $currentTriggers = @(Get-CurrentTriggers $extra.TaskName)
    $actual = Format-CurrentSet $currentTriggers
    $rows += [pscustomobject]@{
        Tarea = $extra.TaskName
        Zona = "no declarada"
        Actual = $actual
        Corregida = $actual
        Cambia = "no declarada"
        WakeToRun = "$([bool]$extra.Settings.WakeToRun)"
    }
}

$maintenance = $config.maintenance
$mChanged = $false
$mExists = $false
if ($maintenance) {
    $mTask = Get-ScheduledTask -TaskName $maintenance.name -ErrorAction SilentlyContinue
    $mExists = [bool]$mTask
    $mActual = "nueva"
    $mWake = $false
    if ($mTask) {
        $mWake = [bool]$mTask.Settings.WakeToRun
        $mTriggers = @($mTask.Triggers)
        if ($mTriggers.Count -gt 0) {
            $mActual = (@($mTriggers | ForEach-Object {
                $start = "-"
                if ($_.StartBoundary) { $start = ([datetime]$_.StartBoundary).ToString("HH:mm") }
                "$start diario"
            }) -join "; ")
        }
        $mOk = $false
        if ($mTriggers.Count -eq 1) {
            $start = "-"
            if ($mTriggers[0].StartBoundary) { $start = ([datetime]$mTriggers[0].StartBoundary).ToString("HH:mm") }
            $kind = [string]$mTriggers[0].CimClass.CimClassName
            if ($start -eq [string]$maintenance.at -and $kind -like "*Daily*" -and -not $mTriggers[0].Repetition.Interval) {
                $mOk = $true
            }
        }
        if (-not $mOk) { $mChanged = $true }
        if ([string]$mTask.Principal.RunLevel -ne "Highest") { $mChanged = $true }
    } else {
        $mChanged = $true
    }
    $mCambia = "no"
    if (-not $mExists) { $mCambia = "nueva" }
    elseif ($mChanged) { $mCambia = "si" }
    $rows += [pscustomobject]@{
        Tarea = $maintenance.name
        Zona = "local"
        Actual = $mActual
        Corregida = "$($maintenance.at) diario"
        Cambia = $mCambia
        WakeToRun = "$mWake"
    }
}

Write-Output "AI-Manage: disparadores actuales"
$manageTask = Get-ScheduledTask -TaskName "TradingLab-AI-Manage" -ErrorAction SilentlyContinue
if ($manageTask) {
    foreach ($t in @($manageTask.Triggers)) {
        $start = "-"
        if ($t.StartBoundary) { $start = ([datetime]$t.StartBoundary).ToString("HH:mm") }
        $mask = [int]$t.DaysOfWeek
        $days = Format-DayMask $mask
        if ($t.CimClass.CimClassName -like "*Time*" -and -not ($t.CimClass.CimClassName -like "*Daily*")) {
            $days = "temporal"
        }
        $interval = Convert-IsoDuration ([string]$t.Repetition.Interval)
        $duration = Convert-IsoDuration ([string]$t.Repetition.Duration)
        $intervalText = "sin repeticion"
        if ($null -ne $interval) { $intervalText = "$([int]$interval.TotalMinutes) min" }
        $durationText = "-"
        if ($null -ne $duration) { $durationText = Format-Span $duration }
        Write-Output "  inicio $start ($days) | intervalo $intervalText | duracion $durationText"
    }
} else {
    Write-Output "  (no existe)"
}
$manageCfg = $config.tasks | Where-Object { $_.name -eq "TradingLab-AI-Manage" } | Select-Object -First 1
if ($manageCfg) {
    $manageTrig = @($manageCfg.triggers)[0]
    $manageStart = Convert-AnchorToLocal ([string]$manageTrig.at) $today ([string]$manageCfg.anchor)
    $durDays = 0
    if ($null -ne $manageTrig.duration_days) { $durDays = [int]$manageTrig.duration_days }
    $durHours = 0
    if ($null -ne $manageTrig.duration_hours) { $durHours = [int]$manageTrig.duration_hours }
    $intervalMin = [int]$manageTrig.interval_minutes
    $totalMin = ($durDays * 1440) + ($durHours * 60)
    $intervals = [int]($totalMin / $intervalMin)
    Write-Output "AI-Manage: propuesto"
    Write-Output "  inicio $manageStart local ($($manageTrig.at) $($manageCfg.anchor)) | intervalo $intervalMin min | duracion $durDays d $durHours h | $intervals intervalos"
    Write-Output "  cobertura: domingo $($manageTrig.at) NY -> viernes $($manageTrig.at) NY; 0 huecos"
    $temporal = @()
    if ($manageTask) {
        $temporal = @($manageTask.Triggers | Where-Object {
            ($_.CimClass.CimClassName -like "*Time*") -and
            -not ($_.CimClass.CimClassName -like "*Daily*")
        })
    }
    $longTemporal = @($temporal | Where-Object {
        $duration = Convert-IsoDuration ([string]$_.Repetition.Duration)
        $null -ne $duration -and $duration.TotalDays -ge 2
    })
    if ($longTemporal.Count -gt 0) {
        Write-Output "  trigger temporal de recuperacion ya presente"
    } else {
        $catch = Get-CatchUpTrigger $manageCfg $manageTrig
        if ($catch) {
            $catchStart = "$($catch.start.ToString('HH:mm')) $(Format-DayName $catch.start)"
            $catchEnd = "$($catch.end.ToString('HH:mm')) $(Format-DayName $catch.end)"
            Write-Output "  ventana activa ahora: se anadira un trigger temporal $catchStart -> $catchEnd"
        }
    }
}

Write-Output ""
$rows | Sort-Object Tarea | Format-Table -AutoSize -Wrap | Out-String -Width 320
Write-Output "TradingLab-ScheduleNY: no existe en el Programador; se sustituye por TradingLab-ScheduleTZ."
$managedChanges = @($plans | Where-Object { $_.managed -and $_.triggerChanged }).Count
$wakeChanges = @($plans | Where-Object { $_.wakeChanged -and -not $_.triggerChanged }).Count
$stateChanges = @($plans | Where-Object { $_.stateChanged }).Count
$summary = "Cambian: $managedChanges gestionadas, $wakeChanges solo WakeToRun, $stateChanges estado"
if ($maintenance) {
    if ($mChanged) { $summary = "$summary, mantenimiento nuevo/actualizado" }
    else { $summary = "$summary, mantenimiento sin cambios" }
}
Write-Output $summary
Write-Output "Hoy local: $($today.ToString('yyyy-MM-dd')) - zona local: $([TimeZoneInfo]::Local.Id) - NY: $((Get-AnchorTimeZone 'America/New_York').Id) - Londres: $((Get-AnchorTimeZone 'Europe/London').Id)"
Write-Output "Modo: $(if ($Apply) { 'APLICAR' } else { 'SOLO LISTA (no registra nada)' })"

if (-not $Apply) { exit 0 }

$needApply = $false
if (-not $IfChanged) {
    $needApply = $true
} else {
    if ($managedChanges -gt 0 -or $wakeChanges -gt 0 -or $stateChanges -gt 0 -or $mChanged) { $needApply = $true }
}
if (-not $needApply) {
    Write-Output "Sin cambios: horas, triggers, WakeToRun y estado ya coinciden."
    exit 0
}

foreach ($plan in $plans) {
    $name = $plan.name
    if (-not $plan.exists) {
        Write-Output "Aviso: $name no existe; se crea desde el YAML"
    }
    if ($plan.managed -and $plan.triggerChanged) {
        $cfg = $plan.config
        if ($name -eq "TradingLab-AI-Scalp") {
            Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
            & schtasks.exe /End /TN $name 2>$null | Out-Null
        }
        $action = $null
        if ($plan.currentTask) {
            # Conservar la accion original: este bloque solo cambia horas,
            # triggers y WakeToRun.
            $action = $plan.currentTask.Actions
        } elseif ($cfg.executable) {
            $action = New-ScheduledTaskAction -Execute ([string]$cfg.executable) -Argument ([string]$cfg.args)
        } else {
            $scriptPath = Join-Path $root ([string]$cfg.script)
            $action = New-ScheduledTaskAction -Execute "powershell.exe" `
                -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" $($cfg.args)" `
                -WorkingDirectory $root
        }
        $triggers = @()
        foreach ($local in $plan.expectedTriggers) {
            $mask = $local.mask
            $dayNames = @()
            if ($mask -band 1) { $dayNames += "Sunday" }
            if ($mask -band 2) { $dayNames += "Monday" }
            if ($mask -band 4) { $dayNames += "Tuesday" }
            if ($mask -band 8) { $dayNames += "Wednesday" }
            if ($mask -band 16) { $dayNames += "Thursday" }
            if ($mask -band 32) { $dayNames += "Friday" }
            if ($mask -band 64) { $dayNames += "Saturday" }
            $days = @($dayNames | ForEach-Object { Get-DayOfWeek $_ })
            if ($local.type -eq "repetition") {
                $duration = $local.end - $local.start
                $once = New-ScheduledTaskTrigger -Once -At ((Get-Date).Date.AddDays(1)) `
                    -RepetitionInterval (New-TimeSpan -Minutes ([int]$local.intervalMinutes)) `
                    -RepetitionDuration $duration
                $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $local.start
                $trigger.Repetition = $once.Repetition
            } else {
                $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $local.start
            }
            $triggers += $trigger
        }
        $catch = Get-CatchUpTrigger $cfg (@($cfg.triggers)[0])
        if ($catch) {
            $catchTrigger = New-ScheduledTaskTrigger -Once -At $catch.start `
                -RepetitionInterval (New-TimeSpan -Minutes ([int]$catch.interval)) `
                -RepetitionDuration $catch.duration
            $triggers += $catchTrigger
            Write-Output "  $($name): ventana activa; trigger temporal $($catch.start.ToString('HH:mm')) -> $($catch.end.ToString('HH:mm'))"
        }
        if ($plan.currentTask) {
            $settings = $plan.currentTask.Settings
            $principal = $plan.currentTask.Principal
            $description = $plan.currentTask.Description
        } else {
            $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
            $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
            $description = "TradingLab: tarea re-registrada desde config/schedule.yaml"
        }
        $settings.WakeToRun = [bool]$plan.desiredWake
        if ($cfg.multiple_instances -eq "IgnoreNew") {
            $settings.MultipleInstances = "IgnoreNew"
        }
        if ($null -ne $cfg.execution_limit_minutes) {
            $settings.ExecutionTimeLimit = "PT$([int]$cfg.execution_limit_minutes)M"
        }
        Register-ScheduledTask -TaskName $name -Action $action -Trigger $triggers `
            -Settings $settings -Principal $principal -Description $description -Force | Out-Null
        Write-Output "Actualizada: $name"
    } elseif ($plan.managed -and $plan.wakeChanged) {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($task) {
            $settings = $task.Settings
            $settings.WakeToRun = [bool]$plan.desiredWake
            Set-ScheduledTask -TaskName $name -Settings $settings | Out-Null
            Write-Output "WakeToRun=$($plan.desiredWake): $name"
        }
    } elseif (-not $plan.managed -and $plan.wakeChanged) {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($task) {
            $settings = $task.Settings
            $settings.WakeToRun = [bool]$plan.desiredWake
            Set-ScheduledTask -TaskName $name -Settings $settings | Out-Null
            Write-Output "WakeToRun=$($plan.desiredWake): $name"
        }
    }
    if ($plan.stateChanged) {
        Disable-ScheduledTask -TaskName $name | Out-Null
        if ($plan.disabledReason) {
            Write-Output "Deshabilitada: $name ($($plan.disabledReason))"
        } else {
            Write-Output "Deshabilitada: $name"
        }
    }
}

if ($maintenance -and $mChanged) {
    $mScript = Join-Path $root ([string]$maintenance.script)
    $mAction = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$mScript`" $($maintenance.args)" `
        -WorkingDirectory $root
    $mAt = [datetime]::ParseExact([string]$maintenance.at, "HH:mm", $null)
    $mTrigger = New-ScheduledTaskTrigger -Daily -At $mAt
    $mUserId = "$env:USERDOMAIN\$env:USERNAME"
    $mLogon = "Interactive"
    if ($mTask) {
        $mSettings = $mTask.Settings
        if ($mTask.Principal.UserId) { $mUserId = [string]$mTask.Principal.UserId }
        if ($mTask.Principal.LogonType) { $mLogon = [string]$mTask.Principal.LogonType }
    } else {
        $mSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    }
    $mPrincipal = New-ScheduledTaskPrincipal -UserId $mUserId -LogonType $mLogon -RunLevel Highest
    $mSettings.WakeToRun = [bool]$maintenance.wake_to_run
    Register-ScheduledTask -TaskName $maintenance.name -Action $mAction -Trigger $mTrigger `
        -Settings $mSettings -Principal $mPrincipal -Description $maintenance.description -Force | Out-Null
    Write-Output "Mantenimiento: $($maintenance.name) diario $($maintenance.at) local"
}

Write-Output "Listo. No se inicio ninguna tarea ni se activo ningun bot."
