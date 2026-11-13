# Latido del PC: solo ping si MT5 responde y SQLite abre.
# No registra la tarea. La tarea TradingLab-Heartbeat la crea
# scripts\register_heartbeat_task.ps1 cuando el operador lo autorice.
$ErrorActionPreference = "Continue"
$root = "E:\trading-lab"
. (Join-Path $PSScriptRoot "heartbeat_task.ps1")
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$python = Join-Path $root ".venv\Scripts\python.exe"
$db = Join-Path $root "data\lab.db"

$dbOk = $false
if ((Test-Path $python) -and (Test-Path $db)) {
    $check = & $python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('PRAGMA quick_check').fetchone()[0]); c.close()" $db 2>$null
    $dbOk = (($check -join "").Trim() -eq "ok")
}

$mt5Ok = $false
if (Test-Path $lab) {
    & $lab mt5 status *> $null
    $mt5Ok = ($LASTEXITCODE -eq 0)
}

if ($dbOk -and $mt5Ok) {
    Send-TaskHeartbeat -Root $root -Check "pc" -Status "ok"
    exit 0
}
Send-TaskHeartbeat -Root $root -Check "pc" -Status "fail"
exit 1
