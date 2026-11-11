# Simulacro mensual de emergencia (R8).
#
# Por defecto es una SIMULACION: informa de lo que habria que hacer y deja
# rastro, sin cancelar ordenes, sin cerrar posiciones y sin enviar avisos.
# Es lo que ejecuta la tarea programada `TradingLab-Drill` (domingo 03:00).
#
# El simulacro real (-Confirm) solo paper/demo y exige el operador ARMADO.
# NO registra la tarea: eso lo hace register_drill_task.ps1 y necesita
# autorizacion explicita del usuario.
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

Write-Log "INICIO simulacro mensual (modo: $(if ($Confirm) { 'real' } else { 'simulacion' }))"
if ($Confirm) {
    $output = & $lab drill --confirm 2>&1
} else {
    $output = & $lab drill --dry-run 2>&1
}
$code = $LASTEXITCODE
$output | ForEach-Object {
    Add-Content -Path $log -Value ([string]$_) -Encoding utf8
    Write-Output $_
}
Write-Log "FIN simulacro exit=$code"
exit $code
