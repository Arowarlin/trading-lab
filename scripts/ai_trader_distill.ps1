# Destilación semanal del carril IA, sin LLM.
# Aprende filtros, valida con el embudo y deja candidatos enabled:false.
# No registra ni activa nada: la promoción es del operador.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "ai_trader_task_common.ps1")
$python = Join-Path $root ".venv\Scripts\python.exe"
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$session = "distill"
$started = Get-Date
$log = Get-AiLogPath -Root $root -Session $session
$lockPath = Join-Path $root "logs\ai_trader\ai_trader.lock"

Write-AiLog -Log $log -Message "inicio distill"
$lockRaw = & $python -m tradinglab.ai_session lock-acquire --path $lockPath --session $session --pid $PID 2>$null
$lock = $null
try { $lock = $lockRaw | ConvertFrom-Json } catch { $lock = $null }
if (-not $lock -or -not $lock.ok) {
    $reason = if ($lock) { $lock.reason } else { "candado no disponible" }
    Write-AiLog -Log $log -Message "salida temprana: $reason"
    Write-AiStatus -Root $root -Session $session -Status "skipped" -Stage "lock" -Reason $reason -Started $started -Log $log
    exit 0
}

try {
    $pre = Invoke-AiPreflight -Root $root -Session $session
    if (-not $pre.ok) {
        $skippedStages = @("window", "killswitch")
        $status = if ($skippedStages -contains $pre.stage) { "skipped" } else { "failed" }
        Write-AiLog -Log $log -Message ("salida temprana [{0}]: {1}" -f $pre.stage, $pre.reason)
        Write-AiStatus -Root $root -Session $session -Status $status -Stage $pre.stage -Reason $pre.reason -Started $started -Log $log
        if ($status -eq "failed") { exit 2 } else { exit 0 }
    }

    $job = Start-Job -ScriptBlock {
        param($lab)
        $out = & $lab ai-trader distill 2>&1
        $code = if ($null -eq $LASTEXITCODE) { 1 } else { $LASTEXITCODE }
        [pscustomobject]@{ code = $code; lines = @($out) }
    } -ArgumentList $lab
    $done = Wait-Job $job -Timeout 3600
    if ($null -eq $done) {
        Stop-Job $job -ErrorAction SilentlyContinue
        $result = [pscustomobject]@{ code = 124; lines = @("timeout de 60 minutos") }
    } else {
        $result = Receive-Job $job -Keep
    }
    Remove-Job $job -Force -ErrorAction SilentlyContinue

    $text = ($result.lines | Out-String)
    Write-AiLog -Log $log -Message $text
    if ($result.code -eq 0) {
        $status = "ok"; $stage = "distill"; $reason = "destilación completada"
    } elseif ($result.code -eq 124) {
        $status = "failed"; $stage = "timeout"; $reason = "timeout de 60 minutos"
    } else {
        $status = "failed"; $stage = "distill"; $reason = "lab ai-trader distill terminó con código $($result.code)"
    }
    Write-AiStatus -Root $root -Session $session -Status $status -Stage $stage -Reason $reason -Started $started -Log $log
    $summary = Format-AiSummary -Root $root -Session $session -Status $status -Reason $reason -OutputLines $result.lines
    Send-AiSummary -Root $root -Subject "TradingLab AI distill" -Body $summary
    if ($status -eq "ok") { exit 0 } else { exit 2 }
}
finally {
    & $python -m tradinglab.ai_session lock-release --path $lockPath --pid $PID 2>$null | Out-Null
}
