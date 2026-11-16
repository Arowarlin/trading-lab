# Restaura un backup en una carpeta temporal y comprueba que no contiene secretos.
# Uso:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\restore_test.ps1
#   powershell ... -File scripts\restore_test.ps1 -ZipPath "F:\TradingLabBackups\trading-lab_....zip" -Keep
param(
    [string]$ZipPath = "",
    [string]$Root = "E:\trading-lab",
    [string]$Dest = "",
    [switch]$Keep
)

$ErrorActionPreference = "Stop"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"

if (-not $ZipPath) {
    $backupDir = "F:\TradingLabBackups"
    $latest = Get-ChildItem $backupDir -Filter "trading-lab_*.zip" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) { throw "No hay backups en $backupDir" }
    $ZipPath = $latest.FullName
}
if (-not (Test-Path $ZipPath)) { throw "No existe el zip: $ZipPath" }
if (-not $Dest) { $Dest = Join-Path $env:TEMP "tradinglab-restore-test-$stamp" }

$failures = New-Object System.Collections.Generic.List[string]
$expanded = Join-Path $Dest "contenido"
$python = Join-Path $Root ".venv\Scripts\python.exe"

try {
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    if ($ZipPath.ToLower().EndsWith(".enc")) {
        if (-not (Test-Path $python)) { throw "Falta python para leer keyring" }
        $password = (& $python -c "import keyring; print(keyring.get_password('tradinglab','BACKUP_PASSWORD') or '')" 2>$null | Out-String).Trim()
        if (-not $password) { throw "Falta BACKUP_PASSWORD en keyring para descifrar" }
        $decrypted = Join-Path $Dest "backup_descifrado.zip"
        $env:TRADINGLAB_BACKUP_PASSWORD = $password
        try {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\backup_crypto.ps1") -Mode decrypt -Path $ZipPath -Out $decrypted
            if ($LASTEXITCODE -ne 0) { throw "backup_crypto.ps1 decrypt falló" }
        } finally {
            Remove-Item Env:\TRADINGLAB_BACKUP_PASSWORD -ErrorAction SilentlyContinue
        }
        $ZipPath = $decrypted
        Write-Host "Descifrado OK: $decrypted"
    }
    Expand-Archive -Path $ZipPath -DestinationPath $expanded -Force

    Write-Host "Backup: $ZipPath"
    Write-Host "Restaurado en: $expanded"

    # 1) Archivos mínimos para poder restaurar el laboratorio.
    $required = @(
        "README.md",
        "pyproject.toml",
        "config\lab.yaml",
        "src\tradinglab\web.py",
        "scripts\backup.ps1",
        "data\lab.db"
    )
    foreach ($rel in $required) {
        if (-not (Test-Path (Join-Path $expanded $rel))) {
            $failures.Add("Falta archivo requerido: $rel")
        }
    }
    if (Test-Path (Join-Path $expanded "PLAN.md")) {
        Write-Host "OK   PLAN.md incluido"
    } else {
        Write-Host "WARN PLAN.md no incluido (backup antiguo o pendiente)"
    }

    # 2) .env nunca debe estar dentro del backup.
    $envFiles = Get-ChildItem -Path $expanded -Recurse -File -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq ".env" -or $_.Name -like ".env.*" } |
        Where-Object { $_.Name -ne ".env.example" }
    foreach ($f in $envFiles) {
        $failures.Add("Archivo de secretos dentro del backup: $($f.FullName.Substring($expanded.Length + 1))")
    }
    if ($envFiles.Count -eq 0) { Write-Host "OK   sin .env dentro del zip" }

    # 3) Escaneo de valores reales de secretos (sin imprimirlos).
    $secretNames = @(
        "ALPACA_API_KEY", "ALPACA_SECRET_KEY", "MT5_PASSWORD", "PROJECTX_API_KEY",
        "FRED_API_KEY", "ALPHA_VANTAGE_API_KEY", "TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY"
    )
    $secrets = @()
    $liveEnv = Join-Path $Root ".env"
    if (Test-Path $liveEnv) {
        foreach ($line in Get-Content $liveEnv -ErrorAction SilentlyContinue) {
            if ($line -match '^\s*([A-Z0-9_]+)\s*=\s*(.+?)\s*$') {
                $name = $matches[1]
                $value = $matches[2].Trim().Trim('"').Trim("'")
                if (($secretNames -contains $name) -and $value.Length -ge 8) {
                    $secrets += [pscustomobject]@{ Name = $name; Value = $value }
                }
            }
        }
    }

    $textExtensions = @(".md", ".txt", ".py", ".ps1", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini", ".env")
    $textFiles = Get-ChildItem -Path $expanded -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $textExtensions -contains $_.Extension.ToLower() }

    foreach ($secret in $secrets) {
        foreach ($file in $textFiles) {
            try {
                if (Select-String -Path $file.FullName -Pattern $secret.Value -SimpleMatch -Quiet -ErrorAction Stop) {
                    $failures.Add("Secreto $($secret.Name) encontrado en $($file.FullName.Substring($expanded.Length + 1))")
                }
            } catch {
                # Un archivo binario o ilegible no debe romper el test.
            }
        }
    }
    if ($secrets.Count -eq 0) {
        Write-Host "WARN no se pudo leer .env local; se omite el escaneo por valor"
    } else {
        Write-Host "OK   escaneo de $($secrets.Count) secretos en $($textFiles.Count) archivos de texto"
    }

    # 4) Patrones de asignación con valor no vacío (solo código/config, no docs).
    $codeFiles = $textFiles | Where-Object {
        $rel = $_.FullName.Substring($expanded.Length + 1)
        $rel -match '^(src|config|scripts|tests)\\'
    }
    $patternHits = Select-String -Path $codeFiles.FullName -Pattern '^\s*(ALPACA_API_KEY|ALPACA_SECRET_KEY|MT5_PASSWORD|PROJECTX_API_KEY|FRED_API_KEY|ALPHA_VANTAGE_API_KEY|TELEGRAM_BOT_TOKEN|OPENAI_API_KEY)\s*=\s*\S+' -ErrorAction SilentlyContinue
    foreach ($hit in $patternHits) {
        $rel = $hit.Path.Substring($expanded.Length + 1)
        if ($rel -ne ".env.example") {
            $value = ($hit.Line -split "=", 2)[1].Trim()
            if ($value.Length -ge 12 -and $value -notmatch '^(\.\.\.|xxx|tu_|your_|cambia)') {
                $failures.Add("Asignación de secreto en claro: $rel")
            }
        }
    }

    # 5) Integridad de SQLite.
    $python = Join-Path $Root ".venv\Scripts\python.exe"
    $db = Join-Path $expanded "data\lab.db"
    if ((Test-Path $python) -and (Test-Path $db)) {
        $check = & $python -c "import sqlite3,sys; con=sqlite3.connect(sys.argv[1]); print(con.execute('PRAGMA integrity_check').fetchone()[0]); con.close()" $db
        if (($check -join "") -match "ok") {
            Write-Host "OK   SQLite integrity_check=ok"
        } else {
            $failures.Add("SQLite integrity_check falló: $check")
        }
    } else {
        Write-Host "WARN no se pudo comprobar SQLite (falta venv o lab.db)"
    }

    # 6) Manifiesto del backup: integrity_check y conteos deben coincidir
    # con la base restaurada. Un backup sin WAL puede ser valido pero viejo;
    # los conteos del manifiesto permiten detectarlo.
    $manifestPath = Join-Path $expanded "MANIFEST.json"
    if (-not (Test-Path $manifestPath)) {
        $failures.Add("Falta MANIFEST.json")
    } else {
        try {
            $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
            if ([string]$manifest.database.integrity_check -ne "ok") {
                $failures.Add("MANIFEST integrity_check != ok")
            }
            foreach ($table in @("fills", "strategy_trials", "ai_decisions")) {
                $expected = [int]$manifest.database.counts.$table
                $actual = & $python -c "import sqlite3,sys; con=sqlite3.connect(sys.argv[1]); print(con.execute('SELECT COUNT(*) FROM '+sys.argv[2]).fetchone()[0]); con.close()" $db $table
                if ([int]$actual -ne $expected) {
                    $failures.Add("Manifiesto $table=$expected, restaurado=$actual")
                }
            }
            Write-Host "OK   MANIFEST.json y conteos"
        } catch {
            $failures.Add("MANIFEST.json invalido: $($_.Exception.Message)")
        }
    }

    if ($failures.Count -gt 0) {
        Write-Host ""
        Write-Host "FALLOS ($($failures.Count)):" -ForegroundColor Red
        foreach ($f in $failures) { Write-Host " - $f" -ForegroundColor Red }
        exit 1
    }

    Write-Host ""
    Write-Host "PASS: backup restaurado y sin secretos en claro." -ForegroundColor Green
    exit 0
}
finally {
    if (-not $Keep) {
        Remove-Item $Dest -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "Conservado para inspección: $Dest"
    }
}
