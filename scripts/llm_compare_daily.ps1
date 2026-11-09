# Compara el MoE 30B con el modelo actual en modo lite, una vez al dia.
# No cambia el modelo por defecto ni envia ordenes.
param(
    [switch]$PreflightOnly,
    [string]$Tickers = "SPY,QQQ,NVDA",
    [string]$Actual = "qwen/qwen3.8-27b",
    [string]$Candidate = "qwen/qwen3-30b-a3b"
)

$ErrorActionPreference = "Continue"
$root = "E:\trading-lab"
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$lms = "C:\Users\PC\.lmstudio\bin\lms.exe"
$logDir = Join-Path $root "logs\llm"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $logDir "compare_daily_$stamp.log"

function Write-Log([string]$Message) {
    Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message) -Encoding utf8
}

function Fail([string]$Message) {
    Write-Log "ERROR: $Message"
    if (Test-Path $lab) {
        & $lab alerts send llm_compare_failed -m $Message --severity warning *>> $log
    }
    exit 1
}

Write-Log "llm compare daily start"
if (-not (Test-Path $lab)) {
    Fail "No existe $lab"
}
if (-not (Test-Path $lms)) {
    Fail "No existe $lms"
}

$available = & $lms ls 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    Fail "lms ls fallo con codigo $LASTEXITCODE"
}
if ($available -notmatch [regex]::Escape($Candidate)) {
    Fail "Modelo candidato no descargado: $Candidate"
}

$loaded = & $lms ps 2>&1 | Out-String
$actualLoaded = $loaded -match [regex]::Escape($Actual)
$candidateLoaded = $loaded -match [regex]::Escape($Candidate)
Write-Log "loaded: actual=$actualLoaded candidate=$candidateLoaded"

if ($PreflightOnly) {
    Write-Log "PreflightOnly: lab, lms y modelos OK; sin cargar ni comparar."
    Write-Output "Preflight OK: $Actual vs $Candidate; cargados actual=$actualLoaded candidato=$candidateLoaded"
    exit 0
}

$candidateLoadedHere = $false
if (-not $candidateLoaded) {
    Write-Log "cargando candidato $Candidate"
    $out = & $lms load $Candidate --context-length 16384 --parallel 1 -y 2>&1
    if ($LASTEXITCODE -ne 0) {
        $out | Select-Object -Last 20 | ForEach-Object { Write-Log $_ }
        Fail "No se pudo cargar $Candidate"
    }
    $candidateLoadedHere = $true
}

if (-not $actualLoaded) {
    Write-Log "cargando actual $Actual"
    $out = & $lms load $Actual --context-length 16384 --parallel 1 -y 2>&1
    if ($LASTEXITCODE -ne 0) {
        $out | Select-Object -Last 20 | ForEach-Object { Write-Log $_ }
        Fail "No se pudo cargar $Actual"
    }
}

$failed = $false
$tickerList = @($Tickers -split "," | ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ })
foreach ($ticker in $tickerList) {
    Write-Log "compare $ticker"
    & $lab llm compare $ticker --models "$Actual,$Candidate" *>> $log
    $code = $LASTEXITCODE
    Write-Log "compare $ticker exit=$code"
    if ($code -ne 0) {
        $failed = $true
    }
}

if ($candidateLoadedHere) {
    Write-Log "descargando candidato $Candidate"
    & $lms unload $Candidate *>> $log
    Write-Log "unload exit=$LASTEXITCODE"
}

if ($failed) {
    Fail "Una o mas comparaciones fallaron; revisar $log"
}

& $lab llm report *>> $log
Write-Log "llm compare daily OK"
exit 0
