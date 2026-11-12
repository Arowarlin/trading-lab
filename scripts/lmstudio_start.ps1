# Arranque de LM Studio al iniciar sesión.
# No descarga modelos: solo arranca el servidor y carga el modelo ya instalado.
param(
    [switch]$Quick
)

$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"

$lms = Join-Path $env:LOCALAPPDATA "Programs\LM Studio\resources\app\.webpack\lms.exe"
$root = "E:\trading-lab"
$logDir = Join-Path $root "logs\lmstudio"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "startup.log"

function Write-Log([string]$Message) {
    Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message) -Encoding utf8
}

Write-Log "Inicio de tarea LM Studio"
if (-not $Quick) {
    Start-Sleep -Seconds 20
}

if (-not (Test-Path $lms)) {
    Write-Log "ERROR: no existe $lms"
    exit 1
}

# Si el modelo ya está cargado, no recargar.
$model = "qwen/qwen3-30b-a3b"
$ctx = 32768
$ps = (& $lms ps 2>&1 | Out-String)
if ($ps -match [regex]::Escape($model) -and $ps -match "$ctx") {
    Write-Log "$model ya está cargado con contexto $ctx; no se recarga"
    exit 0
}

Write-Log "Arrancando servidor LM Studio en 1234"
& $lms server start --port 1234 *>> $log

$healthy = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://127.0.0.1:1234/v1/models"
        if ($response.StatusCode -eq 200) {
            $healthy = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $healthy) {
    Write-Log "ERROR: el servidor no respondió en 60 s"
    exit 1
}

Write-Log "Cargando $model con contexto $ctx"
& $lms load $model --context-length $ctx --parallel 1 --identifier $model --ttl 86400 --yes *>> $log

$ps = (& $lms ps 2>&1 | Out-String)
if ($ps -match [regex]::Escape($model)) {
    Write-Log "Modelo cargado correctamente"
    exit 0
}

Write-Log "ERROR: el modelo no aparece en lms ps"
exit 1
