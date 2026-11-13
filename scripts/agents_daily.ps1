# Análisis lite diario de una watchlist. No envía órdenes: solo guarda
# decisiones y alimenta el panel/Sala. Un fallo no detiene al resto.
$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"

$root = "E:\trading-lab"
. (Join-Path $PSScriptRoot "heartbeat_task.ps1")
Send-TaskHeartbeat -Root $root -Check "agents" -Status "start"
Set-Location $root

$logDir = Join-Path $root "logs\agents"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("agents_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

# Tras dormir o reiniciar, LM Studio puede haber descargado el modelo: sin
# esto los tres tickers fallan con "modelo no cargado".
& (Join-Path $root "scripts\lmstudio_start.ps1") -Quick *>> $log

$tickers = @("SPY", "QQQ", "NVDA")
$failed = @()
foreach ($ticker in $tickers) {
    Add-Content -Path $log -Value "=== $ticker $(Get-Date -Format o) ==="
    & ".\.venv\Scripts\lab.exe" agent $ticker --mode lite *>> $log
    if ($LASTEXITCODE -ne 0) { $failed += $ticker }
}

# Rellena retornos 1/5/20d de decisiones antiguas con la misma cadencia diaria.
Add-Content -Path $log -Value "=== decisions update $(Get-Date -Format o) ==="
& ".\.venv\Scripts\lab.exe" decisions update *>> $log
if ($LASTEXITCODE -ne 0) { $failed += "decisions-update" }

if ($failed.Count -gt 0) {
    & ".\.venv\Scripts\lab.exe" alerts send agents_failed -m ("Fallaron: " + ($failed -join ", ")) --severity warning *>> $log
    Send-TaskHeartbeat -Root $root -Check "agents" -Status "fail"
    exit 1
}
Send-TaskHeartbeat -Root $root -Check "agents" -Status "ok"
exit 0
