# Barrido diario de investigación: ranking + propuestas (nunca activa bots).
# Programar con Task Scheduler (ver README, sección 9).
$ErrorActionPreference = "Stop"

$root = "E:\trading-lab"
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$logDir = Join-Path $root "logs\research"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$env:PYTHONUTF8 = "1"
$stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$log = Join-Path $logDir "research_$stamp.log"

Push-Location $root
try {
    & $lab research `
        --start 2015-01-01 `
        --exposures 1.0,0.5,0.35 `
        --paths 2000 `
        --horizon 120 `
        --top 25 *>&1 | Tee-Object -FilePath $log
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
