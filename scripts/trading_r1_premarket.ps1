# Informe pre-market con Trading-R1 en WSL2. Research en paper; no envia ordenes.
# Requiere el backend de Trading-R1 vivo: TUI abierta o `trading-r1 serve`.
param(
    [switch]$PreflightOnly,
    [switch]$Send,
    [string]$Tickers = "SPY,QQQ,NVDA",
    [string]$Profile = "vllm",
    [string]$Mode = "auto"
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

$root = "E:\trading-lab"
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$wsl = "C:\Program Files\WSL\wsl.exe"
$distro = "Ubuntu-24.04"
$logDir = Join-Path $root "logs\premarket"
$reportDir = Join-Path $root "reports\premarket"
New-Item -ItemType Directory -Force -Path $logDir, $reportDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $logDir "trading_r1_premarket_$stamp.log"
$md = Join-Path $reportDir "premarket_trading_r1_$stamp.md"
$json = Join-Path $reportDir "premarket_trading_r1_$stamp.json"

function Write-Log([string]$Message) {
    Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message) -Encoding utf8
}

function Get-TradingR1Backend {
    if (-not (Test-Path $wsl)) {
        throw "No existe $wsl"
    }
    $raw = & $wsl -d $distro --exec cat /home/pc/.trading-r1/backend.json 2>> $log
    if ($LASTEXITCODE -ne 0 -or -not $raw) {
        throw "No hay backend de Trading-R1. Abre Trading-R1 o ejecuta: trading-r1 serve"
    }
    $backend = $raw | ConvertFrom-Json
    $live = Invoke-RestMethod -Uri "$($backend.url)/livez" -TimeoutSec 10
    if ($live.status -ne "ok") {
        throw "El backend no responde en $($backend.url)"
    }
    return $backend
}

function Get-LmStudioModels {
    return Invoke-RestMethod -Uri "http://127.0.0.1:1234/v1/models" -TimeoutSec 15
}

Write-Log "trading-r1 premarket start"
$backend = Get-TradingR1Backend
Write-Log "backend OK: $($backend.url) (pid $($backend.pid))"

$models = Get-LmStudioModels
$modelIds = @($models.data | ForEach-Object { $_.id })
if ($modelIds -notcontains "qwen3.8-27b") {
    throw "LM Studio no ofrece qwen3.8-27b. Modelos: $($modelIds -join ', ')"
}
Write-Log "LM Studio OK: qwen3.8-27b disponible"

if ($PreflightOnly) {
    Write-Log "PreflightOnly: backend y LM Studio OK; sin LLM ni Telegram."
    Write-Output "Preflight OK: $($backend.url) + qwen3.8-27b"
    exit 0
}

$date = Get-Date -Format "yyyy-MM-dd"
$tickerList = @($Tickers -split "," | ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ })
if ($tickerList.Count -eq 0) {
    throw "No hay tickers en -Tickers"
}
$sections = $tickerList -join ", "

$question = @"
Genera un informe pre-market breve (maximo 700 palabras) para $sections con fecha $date.
Para cada activo incluye, solo si puedes verificarlo con tus herramientas: ultimo precio o cierre disponible y su fecha/hora, variacion reciente, niveles tecnicos clave y catalizadores o noticias de hoy.
Incluye una seccion de eventos macro relevantes de hoy y otra de riesgos.
Si un dato no esta disponible o no puedes verificarlo, escribe exactamente "Sin datos"; no inventes precios, niveles ni historicos.
No des ordenes ni recomendaciones de compra/venta: es investigacion en paper.
Devuelve Markdown con secciones: Resumen, $sections, Eventos, Riesgos, Sin datos.
"@

$payload = @{
    question = $question
    mode = $Mode
    profile = $Profile
    stream = $false
} | ConvertTo-Json -Depth 5

$headers = @{ Authorization = "Bearer $($backend.token)" }
Write-Log "research start: profile=$Profile mode=$Mode tickers=$sections"
$response = Invoke-RestMethod `
    -Uri "$($backend.url)/research" `
    -Method Post `
    -Headers $headers `
    -ContentType "application/json; charset=utf-8" `
    -Body $payload `
    -TimeoutSec 900

if (-not $response.text) {
    throw "Trading-R1 no devolvio texto (termination=$($response.termination), error=$($response.error))"
}

$utf8 = New-Object System.Text.UTF8Encoding($false)
$rawJson = $response | ConvertTo-Json -Depth 8
[IO.File]::WriteAllText($json, $rawJson, $utf8)

$header = "# Pre-market Trading-R1 - $((Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm UTC"))`r`n`r`nPerfil: $Profile. Research en paper; sin ordenes.`r`n`r`n"
[IO.File]::WriteAllText($md, $header + $response.text.Trim() + "`r`n", $utf8)

Write-Log "research OK: termination=$($response.termination) rounds=$($response.rounds) chars=$($response.text.Length)"
Write-Log "report: $md"

if ($Send) {
    & $lab telegram send --file $md *>> $log
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        Write-Log "Telegram fallo con codigo $code"
        & $lab alerts send premarket_failed -m "Trading-R1 pre-market fallo al enviar Telegram ($code)" --severity warning *>> $log
        exit $code
    }
    Write-Log "Telegram OK"
}

Write-Output $md
exit 0
