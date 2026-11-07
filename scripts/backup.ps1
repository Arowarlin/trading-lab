# Backup local del laboratorio (código, config, informes e historial git).
# El zip NO contiene .env: los secretos viven en Windows Credential Manager
# (keyring) y .env queda solo como fallback local. No compartir este zip.
param(
    [string]$Dest = "F:\TradingLabBackups",
    [int]$Keep = 20
)

$ErrorActionPreference = "Stop"

$root = "E:\trading-lab"
trap {
    try {
        & "$root\.venv\Scripts\lab.exe" alerts send backup_failed `
            -m "Backup falló: $($_.Exception.Message)" --severity error 2>$null
    } catch {
        # Si las alertas también fallan, no ocultar el error original.
    }
    throw
}
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stage = Join-Path $env:TEMP "tradinglab-backup-$stamp"
$zip = Join-Path $Dest "trading-lab_$stamp.zip"

New-Item -ItemType Directory -Force -Path $Dest | Out-Null
New-Item -ItemType Directory -Force -Path $stage | Out-Null

Push-Location $root
try {
    foreach ($item in @(
        "src", "config", "tests", "scripts", "docs", ".github",
        "README.md", "PLAN.md", "pyproject.toml", "uv.lock", ".gitignore", ".env.example"
    )) {
        if (Test-Path $item) {
            Copy-Item $item -Destination $stage -Recurse -Force
        }
    }

    # Estado útil, sin cachés ni modelos.
    $dataStage = Join-Path $stage "data"
    New-Item -ItemType Directory -Force -Path $dataStage | Out-Null
    if (Test-Path "data\lab.db") {
        Copy-Item "data\lab.db" (Join-Path $dataStage "lab.db") -Force
    }
    if (Test-Path "data\agent_runs") {
        Copy-Item "data\agent_runs" (Join-Path $dataStage "agent_runs") -Recurse -Force
    }
    if (Test-Path "data\tradingagents\memory.md") {
        New-Item -ItemType Directory -Force -Path (Join-Path $dataStage "tradingagents") | Out-Null
        Copy-Item "data\tradingagents\memory.md" (Join-Path $dataStage "tradingagents\memory.md") -Force
    }

    if (Test-Path "reports") {
        Copy-Item "reports" (Join-Path $stage "reports") -Recurse -Force
    }
    # Historial completo de git (.git es pequeño: los repos de vendor están ignorados).
    if (Test-Path ".git") {
        Copy-Item ".git" (Join-Path $stage ".git") -Recurse -Force
    }

    $info = @"
TradingLab backup $stamp
Origen: $root

Contenido: código, configuración, tests, scripts, docs, informes, lab.db,
historial git y .env.example.

IMPORTANTE: este zip NO incluye .env. Los secretos están en Windows
Credential Manager (servicio "tradinglab") y .env queda como fallback local.

Restaurar:
  1. Descomprimir en E:\trading-lab
  2. uv venv --python 3.13 .venv
  3. uv pip install -e .   (o uv sync --frozen)
  4. Revisar .env.example y reintroducir secretos con scripts\migrate_secrets.py
     o con .env local; en un PC nuevo no hay Credential Manager del usuario anterior.
  5. lab doctor

F: es un disco local. Mantén una segunda copia cifrada en un disco externo.
"@
    Set-Content -Path (Join-Path $stage "LEEME_BACKUP.txt") -Value $info -Encoding UTF8

    if (Test-Path $zip) { Remove-Item $zip -Force }
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -CompressionLevel Optimal
}
finally {
    Pop-Location
    Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
}

# Retención: conserva los últimos $Keep backups.
Get-ChildItem $Dest -Filter "trading-lab_*.zip" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $Keep |
    Remove-Item -Force -ErrorAction SilentlyContinue

# Verificación de restauración y de que no haya secretos en claro.
$restoreTest = Join-Path $root "scripts\restore_test.ps1"
if (Test-Path $restoreTest) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $restoreTest -ZipPath $zip
    if ($LASTEXITCODE -ne 0) {
        throw "restore_test.ps1 falló para $zip"
    }
}

# Latido opcional (healthchecks.io): no bloquea el backup si falla.
& "$root\.venv\Scripts\lab.exe" alerts heartbeat 2>$null | Out-Null

$size = [math]::Round((Get-Item $zip).Length / 1MB, 2)
Write-Host "Backup: $zip ($size MB)"
