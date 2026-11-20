# Briefing pre-Londres y pre-NY con Qwen local. NO usa Trading-R1 ni envia ordenes.
# Lee MT5 en modo adjunto; si no esta abierto, el informe sale "Sin datos".
# Genera Markdown y lo envia al chat autorizado de Telegram.
param(
    [switch]$PreflightOnly,
    [ValidateSet("auto", "pre_london", "pre_ny")]
    [string]$Session = "auto"
)

$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"

$root = "E:\trading-lab"
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$logDir = Join-Path $root "logs\briefing"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $logDir "briefing_$stamp.log"
$report = Join-Path $logDir "briefing_$stamp.md"

Set-Location $root
Add-Content -Path $log -Value ("{0} briefing start" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) -Encoding utf8

if (-not (Test-Path $lab)) {
    Add-Content -Path $log -Value "No existe $lab" -Encoding utf8
    exit 1
}

if ($PreflightOnly) {
    & $lab briefing --session $Session --no-llm --out $report *>> $log
    Add-Content -Path $log -Value "PreflightOnly: fin sin LLM ni Telegram." -Encoding utf8
    exit $LASTEXITCODE
}

# Preflight compartido: si LM Studio no esta listo en 90 s, el informe se
# genera igualmente sin LLM ("Sin datos") y se envia; no se bloquea la tarea.
. (Join-Path $root "scripts\llm_preflight.ps1")
if (Ensure-LMStudio -Log $log) {
    & $lab briefing --session $Session --send --out $report *>> $log
} else {
    Add-Content -Path $log -Value "Sin datos: LM Studio no disponible; briefing sin LLM." -Encoding utf8
    & $lab briefing --session $Session --no-llm --send --out $report *>> $log
}
$code = $LASTEXITCODE
if ($code -ne 0) {
    & $lab alerts send briefing_failed -m "El briefing fallo con codigo $code" --severity warning *>> $log
    exit $code
}

& $lab alerts heartbeat *>> $log
Add-Content -Path $log -Value "briefing OK" -Encoding utf8
exit 0
