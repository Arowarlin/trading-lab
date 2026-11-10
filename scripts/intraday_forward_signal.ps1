# Forward intradía signal-only.
#
# Ejecuta `lab intraday forward` (dry-run) una vez por barra M15 dentro de las
# ventanas UTC de Tokio y Londres. No activa bots, no envía órdenes y no toca
# `config/intraday_forward.yaml`.
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
$logDir = Join-Path $root "logs\intraday_forward"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("forward_{0}.log" -f (Get-Date -Format "yyyyMMdd"))

function Write-Log([string]$Message) {
    Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message) -Encoding utf8
}

$utc = [DateTime]::UtcNow
$isWeekday = $utc.DayOfWeek -notin @([DayOfWeek]::Saturday, [DayOfWeek]::Sunday)
$minuteOfDay = $utc.Hour * 60 + $utc.Minute
# Tokio 00:00-03:00 + margen de cierre hasta 04:30.
# Londres 07:00-16:00 + margen de cierre hasta 16:30.
$inTokyo = $minuteOfDay -ge 0 -and $minuteOfDay -le (4 * 60 + 30)
$inLondon = $minuteOfDay -ge (7 * 60) -and $minuteOfDay -le (16 * 60 + 30)
$inWindow = $isWeekday -and ($inTokyo -or $inLondon)

# Una sola pasada por barra M15: la tarea despierta cada 5 min y solo actúa
# en los primeros 5 minutos tras el cierre de la vela.
$barPhase = $utc.Minute % 15
if (-not $Force -and (-not $inWindow -or $barPhase -gt 4)) {
    exit 0
}

$mutex = New-Object System.Threading.Mutex($false, "TradingLab-IntradayForward")
if (-not $mutex.WaitOne(0)) {
    Write-Log "otra ejecución en curso; se omite"
    exit 0
}

try {
    Set-Location $root
    Write-Log ("INICIO forward signal-only utc={0} force={1}" -f $utc.ToString("yyyy-MM-dd HH:mm:ss"), $Force)
    $output = & $lab intraday forward --bars 5000 2>&1
    $code = $LASTEXITCODE
    $output | ForEach-Object {
        Add-Content -Path $log -Value ([string]$_) -Encoding utf8
    }
    Write-Log "FIN forward signal-only exit=$code"
    if ($code -ne 0) {
        $null = & $lab alerts send intraday_forward_failed -m ("Forward signal-only fallo exit={0} en {1} UTC" -f $code, $utc.ToString("yyyy-MM-dd HH:mm")) --severity error 2>&1
        exit $code
    }
    exit 0
}
finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
