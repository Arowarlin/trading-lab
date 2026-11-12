# Registra las tareas del carril IA discrecional. NO lo ejecutes desde el
# laboratorio: el operador lo revisa y lo lanza manualmente cuando quiera.
#
# Hora de República Dominicana (UTC-4 todo el año). Usuario actual, sin
# privilegios elevados y solo con sesión iniciada. Las tareas quedan listas,
# no se inician al registrarlas.
$ErrorActionPreference = "Stop"

$root = "E:\trading-lab"
$user = "$env:USERDOMAIN\$env:USERNAME"
$sessionScript = Join-Path $root "scripts\ai_trader_session.ps1"
$manageScript = Join-Path $root "scripts\ai_trader_manage.ps1"
$scalpScript = Join-Path $root "scripts\ai_trader_scalp.ps1"

foreach ($script in @($sessionScript, $manageScript, $scalpScript)) {
    if (-not (Test-Path $script)) { throw "No existe $script" }
}

$tz = Get-TimeZone
if ([math]::Abs($tz.BaseUtcOffset.TotalHours + 4) -gt 0.01 -or $tz.SupportsDaylightSavingTime) {
    throw "Las tareas usan hora de República Dominicana (UTC-4 sin DST). Zona actual: $($tz.Id) $($tz.BaseUtcOffset), DST=$($tz.SupportsDaylightSavingTime)."
}

function New-AiWeeklyRepetitionTrigger {
    param(
        [System.DayOfWeek[]]$Days,
        [string]$At,
        [TimeSpan]$Interval,
        [TimeSpan]$Duration
    )
    $once = New-ScheduledTaskTrigger -Once -At ((Get-Date).Date.AddDays(1)) `
        -RepetitionInterval $Interval -RepetitionDuration $Duration
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Days -At $At
    $trigger.Repetition = $once.Repetition
    return $trigger
}

function Register-AiTask {
    param(
        [string]$Name,
        [string]$Script,
        [string]$Arguments,
        $Triggers,
        [int]$LimitMinutes,
        [string]$Description
    )
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`" $Arguments" `
        -WorkingDirectory $root
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Minutes $LimitMinutes)
    $principal = New-ScheduledTaskPrincipal -UserId $user `
        -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $Triggers `
        -Settings $settings -Principal $principal -Description $Description -Force | Out-Null
    Write-Output "Registrada: $Name"
}

$weekdays = @(
    [System.DayOfWeek]::Monday,
    [System.DayOfWeek]::Tuesday,
    [System.DayOfWeek]::Wednesday,
    [System.DayOfWeek]::Thursday,
    [System.DayOfWeek]::Friday
)

# London: 03:05 DOM = 07:05/08:05 London según DST. El script comprueba la
# ventana local y sale sin LLM si no corresponde.
$london = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At "03:05"
Register-AiTask -Name "TradingLab-AI-London" -Script $sessionScript `
    -Arguments "-Session london" -Triggers $london -LimitMinutes 15 `
    -Description "TradingLab IA discrecional London: snapshot/propose/skip; solo demo."

# NY: dos candidatos; el script comprueba 09:30-10:00 NY y sale en el otro.
$ny = @(
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At "09:35"),
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At "10:35")
)
Register-AiTask -Name "TradingLab-AI-NY" -Script $sessionScript `
    -Arguments "-Session ny" -Triggers $ny -LimitMinutes 15 `
    -Description "TradingLab IA discrecional NY: intraday + plan de scalping; solo demo."

# Daily: 18:15 DOM; swing del universo completo.
$daily = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At "18:15"
Register-AiTask -Name "TradingLab-AI-Daily" -Script $sessionScript `
    -Arguments "-Session daily" -Triggers $daily -LimitMinutes 15 `
    -Description "TradingLab IA discrecional daily: swing; solo demo."

# Scalp: cada minuto de 09:25 a 13:05 DOM, L-V. El script comprueba 09:30-12:00
# NY y sale sin operar fuera de la ventana.
$scalpTriggers = @()
foreach ($day in $weekdays) {
    $scalpTriggers += New-AiWeeklyRepetitionTrigger -Days @($day) -At "09:25" `
        -Interval (New-TimeSpan -Minutes 1) -Duration (New-TimeSpan -Hours 3 -Minutes 40)
}
Register-AiTask -Name "TradingLab-AI-Scalp" -Script $scalpScript `
    -Arguments "" -Triggers $scalpTriggers -LimitMinutes 2 `
    -Description "TradingLab IA scalp sin LLM: plan + ventana NY + candado; solo demo."

# Manage: cada 15 min desde domingo 17:00 hasta viernes 18:00 DOM.
$manage = New-AiWeeklyRepetitionTrigger -Days @([System.DayOfWeek]::Sunday) `
    -At "17:00" -Interval (New-TimeSpan -Minutes 15) `
    -Duration (New-TimeSpan -Days 5 -Hours 1)
$manageTriggers = @($manage)
# Si se registra a mitad de semana, añade una ventana única hasta el viernes
# para no esperar al domingo siguiente.
$now = Get-Date
$manageOpen = (
    ($now.DayOfWeek -eq [System.DayOfWeek]::Sunday -and $now.Hour -ge 17) -or
    ($now.DayOfWeek -in @([System.DayOfWeek]::Monday, [System.DayOfWeek]::Tuesday,
                          [System.DayOfWeek]::Wednesday, [System.DayOfWeek]::Thursday)) -or
    ($now.DayOfWeek -eq [System.DayOfWeek]::Friday -and $now.Hour -lt 18)
)
if ($manageOpen) {
    $next = $now.AddMinutes(15 - ($now.Minute % 15))
    $next = $next.AddSeconds(-$next.Second).AddMilliseconds(-$next.Millisecond)
    $daysToFriday = (5 - [int]$now.DayOfWeek + 7) % 7
    $fridayEnd = $now.Date.AddDays($daysToFriday).AddHours(18)
    $duration = $fridayEnd - $next
    if ($duration.TotalMinutes -gt 0) {
        $once = New-ScheduledTaskTrigger -Once -At $next `
            -RepetitionInterval (New-TimeSpan -Minutes 15) `
            -RepetitionDuration $duration
        $manageTriggers += $once
        Write-Output "Manage: ventana única desde $next hasta $fridayEnd"
    }
}
Register-AiTask -Name "TradingLab-AI-Manage" -Script $manageScript `
    -Arguments "" -Triggers $manageTriggers -LimitMinutes 5 `
    -Description "TradingLab IA manage sin LLM: trailing y cierres; solo demo."

Write-Output ""
Write-Output "Tareas registradas (no iniciadas). Revisa con: Get-ScheduledTask -TaskName 'TradingLab-AI-*'"
Write-Output "London 03:05 L-V · NY 09:35 y 10:35 L-V · Daily 18:15 L-V · Scalp 09:25-13:05 L-V · Manage cada 15 min dom 17:00-vie 18:00 (hora DOM, UTC-4)"
