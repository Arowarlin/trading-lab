# Panel web local de TradingLab.
# Uso:  .\scripts\web.ps1 [-Port 8420] [-NoOpen]
param(
    [int]$Port = 8420,
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
Set-Location "E:\trading-lab"

$labArgs = @("web", "--port", "$Port")
if (-not $NoOpen) { $labArgs += "--open" } else { $labArgs += "--no-open" }

& ".\.venv\Scripts\lab.exe" @labArgs
exit $LASTEXITCODE
