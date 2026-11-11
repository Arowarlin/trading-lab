# Forward intradía demo: EJECUCIÓN automática.
#
# Ejecuta `lab intraday forward --execute --confirm FORWARD-DEMO` una vez por
# barra M15 dentro de las ventanas UTC de Tokio y Londres. Solo demo, volumen
# mínimo, máximo 1 trade/día por bot y cierres obligatorios por sesión.
# No toca `config/intraday_forward.yaml`.
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
$log = Join-Path $logDir ("forward_execute_{0}.log" -f (Get-Date -Format "yyyyMMdd"))

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

# Registro diario del guardián: una línea por día UTC con las sesiones en
# ALERT, los disparos y si la puerta de CLOSE está cumplida. Es la evidencia
# de la ventana de 5 sesiones. No bloquea el forward: si el guardián no
# responde, se anota y se sigue.
$guardianState = Join-Path $logDir "guardian_state.txt"
$todayKey = $utc.ToString("yyyy-MM-dd")
$lastGuardian = ""
if (Test-Path $guardianState) {
    $lastGuardian = (Get-Content $guardianState -Raw -Encoding utf8).Trim()
}
if ($lastGuardian -ne $todayKey) {
    try {
        $raw = & $lab guardian status --json 2>&1
        $status = ($raw -join "`n") | ConvertFrom-Json
        $sessions = $status.sessions
        $gate = if ($sessions.gate_ok) { "cumple" } else { "pendiente" }
        Write-Log ("GUARDIAN sesiones={0}/{1} disparos={2} puerta={3} ({4})" -f `
            $sessions.sessions, $sessions.required, $sessions.triggers, $gate, $sessions.reason)
        Set-Content -Path $guardianState -Value $todayKey -Encoding utf8 -NoNewline
    } catch {
        Write-Log ("GUARDIAN no se pudo consultar: {0}" -f $_.Exception.Message)
    }
}

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
    Write-Log ("INICIO forward demo execute utc={0} force={1}" -f $utc.ToString("yyyy-MM-dd HH:mm:ss"), $Force)
    $output = & $lab intraday forward --bars 5000 --execute --confirm FORWARD-DEMO 2>&1
    $code = $LASTEXITCODE
    $output | ForEach-Object {
        Add-Content -Path $log -Value ([string]$_) -Encoding utf8
    }
    Write-Log "FIN forward demo execute exit=$code"
    if ($code -ne 0) {
        $null = & $lab alerts send intraday_forward_failed -m ("Forward demo execute fallo exit={0} en {1} UTC" -f $code, $utc.ToString("yyyy-MM-dd HH:mm")) --severity error 2>&1
        exit $code
    }
    exit 0
}
finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
