# Orquestador diario de SPY en paper (bot trend-spy).
#
# La tarea despierta dos veces en hora local (09:35 y 10:35, UTC-4) para
# cubrir el cambio de horario de Nueva York: el script solo actua cuando en
# ET son las 09:30-09:59, asi que en invierno entra el disparo de las 10:35
# local (09:35 EST) y en verano el de las 09:35 local (09:35 EDT).
#
# Solo paper: `lab orchestrate` usa el broker configurado (paper) y los
# guards de riesgo/kill-switch siguen decidiendo. No envia nada a live.
param(
    [switch]$Force
)

$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

$root = "E:\trading-lab"
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$logDir = Join-Path $root "logs\orchestrate"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("orchestrate_spy_{0}.log" -f (Get-Date -Format "yyyyMMdd"))

function Write-Log([string]$Message) {
    Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message) -Encoding utf8
}

$et = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
$nowEt = [TimeZoneInfo]::ConvertTimeFromUtc((Get-Date).ToUniversalTime(), $et)

if (-not $Force) {
    if ($nowEt.DayOfWeek -in @([DayOfWeek]::Saturday, [DayOfWeek]::Sunday)) {
        exit 0
    }
    $minutes = $nowEt.Hour * 60 + $nowEt.Minute
    if ($minutes -lt (9 * 60 + 30) -or $minutes -gt (9 * 60 + 59)) {
        exit 0
    }
}

$mutex = New-Object System.Threading.Mutex($false, "TradingLab-OrchestrateSPY")
if (-not $mutex.WaitOne(0)) {
    Write-Log "otra ejecucion en curso; se omite"
    exit 0
}

try {
    Set-Location $root
    Write-Log ("INICIO orchestrate trend-spy et={0} force={1}" -f $nowEt.ToString("yyyy-MM-dd HH:mm"), $Force)
    $output = & $lab orchestrate --bot trend-spy 2>&1
    $code = $LASTEXITCODE
    $output | ForEach-Object {
        Add-Content -Path $log -Value ([string]$_) -Encoding utf8
    }
    Write-Log "FIN orchestrate trend-spy exit=$code"
    if ($code -ne 0) {
        $null = & $lab alerts send orchestrate_spy_failed -m ("Orchestrate SPY fallo exit={0}" -f $code) --severity error 2>&1
        exit $code
    }
    exit 0
}
finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
