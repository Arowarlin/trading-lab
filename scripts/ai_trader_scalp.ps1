# Scalper del carril IA, sin LLM. Una pasada; la tarea lo llama cada minuto
# dentro de la ventana de scalping. Candado y preflight compartidos. Solo demo.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "ai_trader_task_common.ps1")
$python = Join-Path $root ".venv\Scripts\python.exe"
$lab = Join-Path $root ".venv\Scripts\lab.exe"
. (Join-Path $PSScriptRoot "heartbeat_task.ps1")
Send-TaskHeartbeat -Root $root -Check "ai-scalp" -Status "start"
$session = "scalp"
$started = Get-Date
$log = Get-AiLogPath -Root $root -Session $session
$lockPath = Join-Path $root "logs\ai_trader\ai_trader.lock"

Write-AiLog -Log $log -Message "inicio scalp"
$lockRaw = & $python -m tradinglab.ai_session lock-acquire --path $lockPath --session $session --pid $PID 2>$null
$lock = $null
try { $lock = $lockRaw | ConvertFrom-Json } catch { $lock = $null }
if (-not $lock -or -not $lock.ok) {
    $reason = if ($lock) { $lock.reason } else { "candado no disponible" }
    Write-AiLog -Log $log -Message "salida temprana: $reason"
    Write-AiStatus -Root $root -Session $session -Status "skipped" -Stage "lock" -Reason $reason -Started $started -Log $log
    Send-TaskHeartbeat -Root $root -Check "ai-scalp" -Status "ok"
    exit 0
}

try {
    $pre = Invoke-AiPreflight -Root $root -Session $session
    if (-not $pre.ok) {
        $skippedStages = @("window", "killswitch", "account_stop", "global_stop", "market")
        $status = if ($skippedStages -contains $pre.stage) { "skipped" } else { "failed" }
        Write-AiLog -Log $log -Message ("salida temprana [{0}]: {1}" -f $pre.stage, $pre.reason)
        Write-AiStatus -Root $root -Session $session -Status $status -Stage $pre.stage -Reason $pre.reason -Started $started -Log $log
        if ($status -eq "failed") { Send-TaskHeartbeat -Root $root -Check "ai-scalp" -Status "fail"; exit 2 } else { Send-TaskHeartbeat -Root $root -Check "ai-scalp" -Status "ok"; exit 0 }
    }

    $job = Start-Job -ScriptBlock {
        param($lab)
        $out = & $lab ai-trader scalp 2>&1
        $code = if ($null -eq $LASTEXITCODE) { 1 } else { $LASTEXITCODE }
        [pscustomobject]@{ code = $code; lines = @($out) }
    } -ArgumentList $lab
    $done = Wait-Job $job -Timeout 120
    if ($null -eq $done) {
        Stop-Job $job -ErrorAction SilentlyContinue
        $result = [pscustomobject]@{ code = 124; lines = @("timeout de 2 minutos") }
    } else {
        $result = Receive-Job $job -Keep
    }
    Remove-Job $job -Force -ErrorAction SilentlyContinue

    $text = ($result.lines | Out-String)
    Write-AiLog -Log $log -Message $text
    if ($result.code -eq 0) {
        $status = "ok"; $stage = "scalp"; $reason = "scalp completado"
    } elseif ($result.code -eq 124) {
        $status = "failed"; $stage = "timeout"; $reason = "timeout de 2 minutos"
    } else {
        $status = "failed"; $stage = "scalp"; $reason = "lab ai-trader scalp terminó con código $($result.code)"
    }
    Write-AiStatus -Root $root -Session $session -Status $status -Stage $stage -Reason $reason -Started $started -Log $log
    $summary = Format-AiSummary -Root $root -Session $session -Status $status -Reason $reason -OutputLines $result.lines
    Send-AiSummary -Root $root -Subject "TradingLab AI scalp" -Body $summary
    if ($status -eq "ok") { Send-TaskHeartbeat -Root $root -Check "ai-scalp" -Status "ok"; exit 0 } else { Send-TaskHeartbeat -Root $root -Check "ai-scalp" -Status "fail"; exit 2 }
}
finally {
    & $python -m tradinglab.ai_session lock-release --path $lockPath --pid $PID 2>$null | Out-Null
}
