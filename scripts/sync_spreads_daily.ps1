# Medición diaria de spreads (attach-only, sin login ni shutdown).
# No registra la tarea: el operador la crea con schtasks (ver docs/PLAN).
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$Lab = Join-Path $Root ".venv\Scripts\lab.exe"
$LogDir = Join-Path $Root "logs"
$Log = Join-Path $LogDir "sync_spreads_daily.log"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log([string]$Message) {
    $line = "$(Get-Date -Format o) $Message"
    Add-Content -Path $Log -Value $line -Encoding utf8
    Write-Host $line
}

foreach ($Account in @("CFD-001", "CFD-006")) {
    Write-Log "sync-spreads $Account: inicio"
    try {
        $output = & $Lab propfund sync-spreads --account $Account --measure --days 1 --write 2>&1
        $code = $LASTEXITCODE
        $output | ForEach-Object { Write-Log "sync-spreads $Account: $_" }
        if ($code -ne 0) {
            Write-Log "sync-spreads $Account: Sin datos (exit $code); se continúa"
        } else {
            Write-Log "sync-spreads $Account: ok"
        }
    } catch {
        Write-Log "sync-spreads $Account: Sin datos ($($_.Exception.Message)); se continúa"
    }
}
Write-Log "sync-spreads diario: fin"
exit 0
