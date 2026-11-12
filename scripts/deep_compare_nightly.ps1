# Comparacion nocturna lite vs deep sobre un activo rotatorio.
# Solo mide y guarda decisiones: NO ejecuta ordenes ni activa bots.
# No se registra automaticamente; usa register_deep_compare_task.ps1.
param(
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"

$root = "E:\trading-lab"
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$logDir = Join-Path $root "logs\agents"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("deep_compare_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

function Write-Log([string]$Message) {
    Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message) -Encoding utf8
}

Set-Location $root
Write-Log "Deep compare start"

if (-not (Test-Path $lab)) {
    Write-Log "No existe $lab"
    exit 1
}

# Deep en pausa (2026-11-11): sin saldo (402) ni clave valida (401) no se
# lanza. El deep se corre bajo demanda; la tarea programada queda deshabilitada
# en cuanto haya permisos de administrador para el Programador de tareas.
$envFile = Join-Path $root ".env"
$deepKey = $env:LAB_DEEP_LLM_API_KEY
$deepBase = $env:LAB_DEEP_LLM_BASE_URL
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^\s*LAB_DEEP_LLM_API_KEY\s*=\s*(.+)$') {
            $deepKey = $Matches[1].Trim().Trim('"').Trim("'")
        }
        if ($line -match '^\s*LAB_DEEP_LLM_BASE_URL\s*=\s*(.+)$') {
            $deepBase = $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
}
if (-not $deepKey -or -not $deepBase) {
    Write-Log "Deep en pausa: sin credencial o endpoint. El deep se corre bajo demanda."
    exit 0
}
try {
    $headers = @{ Authorization = "Bearer $deepKey" }
    $probeUrl = $deepBase.TrimEnd("/") + "/models"
    if ($deepBase -match 'opencode\.ai') {
        $headers["x-opencode-session"] = "lab-deep-nightly"
        $headers["User-Agent"] = "trading-lab/1.0"
        # El base de chat es /inference/go/openai/v1; el listado de modelos
        # vive en /inference/v1/models (el chat no expone /models).
        $probeUrl = "https://opencode.ai/inference/v1/models"
    }
    Invoke-WebRequest -Uri $probeUrl -Headers $headers -TimeoutSec 10 -UseBasicParsing | Out-Null
} catch {
    $status = $_.Exception.Response.StatusCode.value__
    Write-Log ("Deep en pausa: proveedor no disponible (HTTP {0}). Saldo agotado (402) o clave invalida (401); el deep se corre bajo demanda." -f $status)
    exit 0
}

if ($PreflightOnly) {
    & $lab agent-compare --report *>> $log
    Write-Log "PreflightOnly: fin sin lanzar deep."
    exit 0
}

# Un activo por noche para no encadenar varios runs multi-agente.
$watchlist = @("SPY", "QQQ", "NVDA")
$index = [int](Get-Date).DayOfWeek % $watchlist.Count
$ticker = $watchlist[$index]
Write-Log "Ticker nocturno: $ticker"

# El lado lite necesita el modelo local; tras dormir LM Studio lo descarga.
& (Join-Path $root "scripts\lmstudio_start.ps1") -Quick *>> $log

& $lab agent-compare $ticker --analysts "market,news,fundamentals,social" *>> $log
$code = $LASTEXITCODE
Write-Log "agent-compare $ticker exit=$code"

# Rellena retornos 1/5/20d; no envia ordenes.
& $lab decisions update *>> $log
if ($LASTEXITCODE -ne 0) {
    Write-Log "decisions update fallo"
    exit 1
}

if ($code -ne 0) {
    & $lab alerts send deep_compare_failed -m "Deep compare fallo para $ticker (exit=$code)" --severity warning *>> $log
    exit 1
}

Write-Log "Deep compare OK"
& $lab alerts heartbeat *>> $log
exit 0
