# Latido del PC: siempre avisa. Primero un `start`; después `ok` o `fail` con
# el motivo. La comprobación de MT5 tiene timeout para que la tarea no muera
# antes de hacer el ping (ExecutionTimeLimit = 2 min).
# No registra la tarea: la crea scripts\register_heartbeat_task.ps1.
$ErrorActionPreference = "Continue"
$root = "E:\trading-lab"
. (Join-Path $PSScriptRoot "heartbeat_task.ps1")
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$python = Join-Path $root ".venv\Scripts\python.exe"
$db = Join-Path $root "data\lab.db"

Send-TaskHeartbeat -Root $root -Check "pc" -Status "start"

$reasons = @()
$dbOk = $false
if ((Test-Path $python) -and (Test-Path $db)) {
    try {
        $check = & $python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('PRAGMA quick_check').fetchone()[0]); c.close()" $db 2>$null
        $dbOk = (($check -join "").Trim() -eq "ok")
    } catch {
        $reasons += "SQLite: $($_.Exception.Message)"
    }
} else {
    $reasons += "SQLite: falta python.exe o data/lab.db"
}
if (-not $dbOk -and $reasons.Count -eq 0) {
    $reasons += "SQLite: quick_check distinto de ok"
}

$mt5Ok = $false
$mt5Reason = "no se pudo lanzar"
if (Test-Path $lab) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $lab
    $psi.Arguments = "mt5 status"
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    try {
        $proc = [System.Diagnostics.Process]::Start($psi)
        if (-not $proc.WaitForExit(60000)) {
            try { $proc.Kill() } catch {}
            $mt5Reason = "timeout 60s"
        } else {
            $err = $proc.StandardError.ReadToEnd()
            if ($proc.ExitCode -eq 0) {
                $mt5Ok = $true
                $mt5Reason = "ok"
            } else {
                $mt5Reason = "exit=$($proc.ExitCode) $($err.Trim())"
            }
        }
    } catch {
        $mt5Reason = $_.Exception.Message
    }
} else {
    $mt5Reason = "lab.exe no encontrado"
}
if (-not $mt5Ok) {
    $reasons += "MT5: $mt5Reason"
}

# Relevo de Vector y retención de sus JSONL. Si no existe alerts.jsonl, el
# relevo no hace nada; nunca bloquea el latido.
try { & $lab alerts relay 2>$null | Out-Null } catch {}
$cleanup = Join-Path $PSScriptRoot "vector_cleanup.ps1"
if (Test-Path $cleanup) {
    try { & $cleanup -Root $root -Days 14 2>$null | Out-Null } catch {}
}

# Piloto automático de la tabla Healthchecks: si algún día aparece la API key
# en keyring, aplica los 12 cron una sola vez y deja la marca. Sin key sale 2
# y no escribe nada; no bloquea el latido.
$scheduleState = Join-Path $root "data\heartbeat_schedule_applied"
if (-not (Test-Path $scheduleState)) {
    try {
        & $lab heartbeat apply-schedule --apply 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Set-Content -Path $scheduleState -Value (Get-Date -Format "yyyy-MM-dd HH:mm:ss") -Encoding utf8
        }
    } catch {}
}

if ($dbOk -and $mt5Ok) {
    Send-TaskHeartbeat -Root $root -Check "pc" -Status "ok" -Message "db=ok mt5=ok"
    exit 0
}

$message = ($reasons -join "; ")
if (-not $message) {
    $message = "fallo sin detalle"
}
Send-TaskHeartbeat -Root $root -Check "pc" -Status "fail" -Message $message
exit 1
