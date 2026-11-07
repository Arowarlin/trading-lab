# Análisis lite diario de una watchlist. No envía órdenes: solo guarda
# decisiones y alimenta el panel/Sala. Un fallo no detiene al resto.
$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"

$root = "E:\trading-lab"
Set-Location $root

$logDir = Join-Path $root "logs\agents"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("agents_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

$tickers = @("SPY", "QQQ", "NVDA")
$failed = @()
foreach ($ticker in $tickers) {
    Add-Content -Path $log -Value "=== $ticker $(Get-Date -Format o) ==="
    & ".\.venv\Scripts\lab.exe" agent $ticker --mode lite *>> $log
    if ($LASTEXITCODE -ne 0) { $failed += $ticker }
}

if ($failed.Count -gt 0) {
    & ".\.venv\Scripts\lab.exe" alerts send agents_failed -m ("Fallaron: " + ($failed -join ", ")) --severity warning *>> $log
    exit 1
}
& ".\.venv\Scripts\lab.exe" alerts heartbeat *>> $log
exit 0
