# Simulacro mensual de emergencia (R8).
#
# Solo paper/demo. Requiere el operador ARMADO y el flag --confirm.
# NO registra la tarea: eso lo hace register_drill_task.ps1 y necesita
# autorización explícita del usuario.
param(
    [switch]$Confirm
)

$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$root = "E:\trading-lab"
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("drill_{0}.log" -f (Get-Date -Format "yyyyMM"))

function Write-Log([string]$Message) {
    Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message) -Encoding utf8
}

if (-not $Confirm) {
    Write-Log "simulacro cancelado: falta -Confirm"
    Write-Output "Falta -Confirm: no se ejecuta nada."
    exit 1
}

Write-Log "INICIO simulacro R8"
$output = & $lab drill --confirm 2>&1
$code = $LASTEXITCODE
$output | ForEach-Object {
    Add-Content -Path $log -Value ([string]$_) -Encoding utf8
    Write-Output $_
}
Write-Log "FIN simulacro exit=$code"
exit $code
