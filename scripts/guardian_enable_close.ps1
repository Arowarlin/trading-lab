# Pasa el guardián de MQL5 de ALERT a CLOSE, pero solo si la puerta se cumple.
#
# La puerta son 5 sesiones de sesion en ALERT **sin falsos positivos**
# (ningun TRIGGER en el log del EA). Si no esta cumplida, el script NO toca
# nada y sale con codigo 1.
#
#   powershell -File scripts\guardian_enable_close.ps1            # aplica
#   powershell -File scripts\guardian_enable_close.ps1 -DryRun    # simula
#
# Cambios que aplica (solo con la puerta cumplida):
#   1. MQL5/Presets/TradingLabGuardian.set : Mode=ALERT -> Mode=CLOSE
#   2. chart del perfil : expertmode=0 -> expertmode=1 (el EA podra cerrar)
#   3. config/intraday_forward.yaml : defense: report -> defense: enforce
param(
    [switch]$DryRun,
    [int]$RequiredSessions = 5
)

$ErrorActionPreference = "Stop"
$root = "E:\trading-lab"
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$forwardConfig = Join-Path $root "config\intraday_forward.yaml"

$raw = & $lab guardian status --json --required-sessions $RequiredSessions 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Output "No se pudo leer el estado del guardián:"
    $raw | ForEach-Object { Write-Output $_ }
    exit 1
}
$status = ($raw -join "`n") | ConvertFrom-Json
$sessions = $status.sessions

Write-Output ("Sesiones ALERT: {0} de {1} · disparos: {2}" -f $sessions.sessions, $sessions.required, $sessions.triggers)
Write-Output ("Motivo: {0}" -f $sessions.reason)

if (-not $sessions.gate_ok) {
    Write-Output ""
    Write-Output "PUERTA NO CUMPLIDA: no se cambia nada."
    Write-Output "Hace falta 5 sesiones en ALERT sin falsos positivos antes de CLOSE y de enforce."
    exit 1
}

$terminal = [string]$sessions.terminal_path
if (-not $terminal) {
    Write-Output "No se conoce la ruta del terminal; no se cambia nada."
    exit 1
}
$preset = Join-Path $terminal "MQL5\Presets\TradingLabGuardian.set"
$chart = Join-Path $terminal "MQL5\Profiles\Charts\Default\chart01.chr"

Write-Output ""
Write-Output "PUERTA CUMPLIDA. Cambios:"
Write-Output "  1. preset  : $preset  (Mode=ALERT -> Mode=CLOSE)"
Write-Output "  2. chart   : $chart  (expertmode=0 -> 1)"
Write-Output "  3. forward : $forwardConfig  (defense: report -> enforce)"

if ($DryRun) {
    Write-Output ""
    Write-Output "Dry-run: no se modifica nada."
    exit 0
}

# 1. preset del EA
if (-not (Test-Path $preset)) { throw "No existe el preset: $preset" }
$presetText = Get-Content $preset -Raw -Encoding UTF8
if ($presetText -notmatch "Mode=ALERT") {
    Write-Output "El preset ya no esta en ALERT; se deja como esta."
} else {
    $presetText = $presetText -replace "Mode=ALERT", "Mode=CLOSE"
    Set-Content -Path $preset -Value $presetText -Encoding UTF8 -NoNewline
    Write-Output "  [ok] preset actualizado"
}

# 2. chart del perfil: expertmode del bloque TradingLabGuardian
if (-not (Test-Path $chart)) { throw "No existe el chart: $chart" }
$unicode = [System.Text.Encoding]::Unicode
$chartText = [System.IO.File]::ReadAllText($chart, $unicode)
if ($chartText -notmatch "name=TradingLabGuardian") {
    throw "El chart no tiene el bloque de TradingLabGuardian; revisa el perfil."
}
if ($chartText -match "name=TradingLabGuardian[\s\S]{0,200}?expertmode=1") {
    Write-Output "  [ok] el chart ya tenia expertmode=1"
} else {
    $chartText = [regex]::Replace(
        $chartText,
        "(name=TradingLabGuardian[\s\S]{0,200}?)expertmode=0",
        '${1}expertmode=1'
    )
    [System.IO.File]::WriteAllText($chart, $chartText, $unicode)
    Write-Output "  [ok] chart actualizado (expertmode=1)"
}

# 3. forward: defense enforce
$forwardText = Get-Content $forwardConfig -Raw -Encoding UTF8
if ($forwardText -match "defense:\s*enforce") {
    Write-Output "  [ok] el forward ya estaba en enforce"
} else {
    $forwardText = $forwardText -replace "defense:\s*report", "defense: enforce"
    Set-Content -Path $forwardConfig -Value $forwardText -Encoding UTF8 -NoNewline
    Write-Output "  [ok] forward actualizado (defense: enforce)"
}

Write-Output ""
Write-Output "Listo. El EA seguira en ALERT hasta que se recargue el chart en MT5."
