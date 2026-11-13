# Backup local del laboratorio (código, config, informes e historial git).
# Uso: backup.ps1 [-Offsite] [-Dest F:\TradingLabBackups]
# El zip NO contiene .env: los secretos viven en Windows Credential Manager
# (keyring) y .env queda solo como fallback local. No compartir este zip.
param(
    [string]$Dest = "F:\TradingLabBackups",
    [int]$Keep = 20,
    [switch]$Offsite
)

$ErrorActionPreference = "Stop"

$root = "E:\trading-lab"
. (Join-Path $PSScriptRoot "heartbeat_task.ps1")
Send-TaskHeartbeat -Root $root -Check "backup" -Status "start"
trap {
    try {
        & "$root\.venv\Scripts\lab.exe" alerts send backup_failed `
            -m "Backup falló: $($_.Exception.Message)" --severity error 2>$null
    } catch {
        # Si las alertas también fallan, no ocultar el error original.
    }
    Send-TaskHeartbeat -Root $root -Check "backup" -Status "fail"
    throw
}
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stage = Join-Path $env:TEMP "tradinglab-backup-$stamp"
$zip = Join-Path $Dest "trading-lab_$stamp.zip"
$enc = $null

function Remove-OldBackups([string]$Dir) {
    if (-not (Test-Path $Dir)) { return }
    $files = Get-ChildItem $Dir -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^trading-lab_\d{8}_\d{6}\.zip(\.enc)?$' } |
        Sort-Object LastWriteTime -Descending
    if ($files.Count -eq 0) { return }
    $daily = @($files | Group-Object { $_.LastWriteTime.Date } |
        Select-Object -First 14 | ForEach-Object { $_.Group } | ForEach-Object { $_.FullName })
    $weekly = @($files | Group-Object { $_.LastWriteTime.ToString("yyyy-ww") } |
        Select-Object -First 8 | ForEach-Object { $_.Group } | ForEach-Object { $_.FullName })
    $keep = @($daily + $weekly | Sort-Object -Unique)
    $files | Where-Object { $keep -notcontains $_.FullName } |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

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
    if (Test-Path "data\calendar") {
        Copy-Item "data\calendar" (Join-Path $dataStage "calendar") -Recurse -Force
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

# Retención: 14 diarias + 8 semanales (unión) en local y, si aplica, offsite.
Remove-OldBackups $Dest

if ($Offsite) {
    $python = Join-Path $root ".venv\Scripts\python.exe"
    $helper = Join-Path $root "scripts\backup_config.py"
    $offsiteDir = (& $python $helper "dir" 2>$null | Out-String).Trim()
    if (-not $offsiteDir) { throw "backup.offsite_dir no está configurado en config/lab.yaml" }
    $offsiteDir = [Environment]::ExpandEnvironmentVariables($offsiteDir)
    New-Item -ItemType Directory -Force -Path $offsiteDir | Out-Null
    $password = (& $python $helper "password" 2>$null | Out-String).Trim()
    if (-not $password) { throw "Falta BACKUP_PASSWORD en keyring" }
    $qualifier = Split-Path -Qualifier $offsiteDir
    $drive = Get-PSDrive -Name $qualifier.TrimEnd(":") -ErrorAction SilentlyContinue
    $sizeLocal = (Get-Item $zip).Length
    if ($drive -and $drive.Free -gt 0 -and $sizeLocal -gt (0.5 * $drive.Free)) {
        Write-Warning ("El backup ({0:N2} MB) supera el 50% del espacio libre ({1:N2} MB) en {2}" -f ($sizeLocal / 1MB), ($drive.Free / 1MB), $qualifier)
    }
    $enc = "$zip.enc"
    $env:TRADINGLAB_BACKUP_PASSWORD = $password
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "scripts\backup_crypto.ps1") -Mode encrypt -Path $zip -Out $enc
        if ($LASTEXITCODE -ne 0) { throw "backup_crypto.ps1 encrypt falló" }
        Copy-Item $enc (Join-Path $offsiteDir (Split-Path $enc -Leaf)) -Force
        Write-Host "Offsite cifrado: $(Join-Path $offsiteDir (Split-Path $enc -Leaf))"
    } finally {
        Remove-Item Env:\TRADINGLAB_BACKUP_PASSWORD -ErrorAction SilentlyContinue
    }
    Remove-OldBackups $offsiteDir
}

# Verificación de restauración y de que no haya secretos en claro.
$verifyZip = if ($Offsite -and $enc -and (Test-Path $enc)) { $enc } else { $zip }
$restoreTest = Join-Path $root "scripts\restore_test.ps1"
if (Test-Path $restoreTest) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $restoreTest -ZipPath $verifyZip
    if ($LASTEXITCODE -ne 0) {
        throw "restore_test.ps1 falló para $verifyZip"
    }
}
if ($Offsite -and $enc -and (Test-Path $enc)) { Remove-Item $enc -Force -ErrorAction SilentlyContinue }

# Latido externo: no bloquea el backup si no está configurado.
Send-TaskHeartbeat -Root $root -Check "backup" -Status "ok"

$size = [math]::Round((Get-Item $zip).Length / 1MB, 2)
Write-Host "Backup: $zip ($size MB)"
