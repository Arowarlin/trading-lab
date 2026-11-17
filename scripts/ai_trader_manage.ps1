# Trailing y sincronización de cierres del carril IA, sin LLM.
# No usa el candado de las sesiones: manage solo lee posiciones y mueve SLs,
# y debe correr aunque el scalp esté ocupado. Solo demo.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "ai_trader_task_common.ps1")
$lab = Join-Path $root ".venv\Scripts\lab.exe"
. (Join-Path $PSScriptRoot "heartbeat_task.ps1")
Send-TaskHeartbeat -Root $root -Check "ai-manage" -Status "start"
$session = "manage"
$started = Get-Date
$log = Get-AiLogPath -Root $root -Session $session

Write-AiLog -Log $log -Message "inicio manage"
$pre = Invoke-AiPreflight -Root $root -Session $session
if (-not $pre.ok) {
    $skippedStages = @("window", "killswitch", "account_stop", "global_stop", "market")
    $status = if ($skippedStages -contains $pre.stage) { "skipped" } else { "failed" }
    Write-AiLog -Log $log -Message ("salida temprana [{0}]: {1}" -f $pre.stage, $pre.reason)
    Write-AiStatus -Root $root -Session $session -Status $status -Stage $pre.stage -Reason $pre.reason -Started $started -Log $log
    if ($status -eq "failed") { Send-TaskHeartbeat -Root $root -Check "ai-manage" -Status "fail"; exit 2 } else { Send-TaskHeartbeat -Root $root -Check "ai-manage" -Status "ok"; exit 0 }
}

$job = Start-Job -ScriptBlock {
    param($lab)
    $out = & $lab ai-trader manage 2>&1
    $code = if ($null -eq $LASTEXITCODE) { 1 } else { $LASTEXITCODE }
    [pscustomobject]@{ code = $code; lines = @($out) }
} -ArgumentList $lab
$done = Wait-Job $job -Timeout 300
if ($null -eq $done) {
    Stop-Job $job -ErrorAction SilentlyContinue
    $result = [pscustomobject]@{ code = 124; lines = @("timeout de 5 minutos") }
} else {
    $result = Receive-Job $job -Keep
}
Remove-Job $job -Force -ErrorAction SilentlyContinue

$text = ($result.lines | Out-String)
Write-AiLog -Log $log -Message $text
if ($result.code -eq 0) {
    $status = "ok"; $stage = "manage"; $reason = "manage completado"
} elseif ($result.code -eq 124) {
    $status = "failed"; $stage = "timeout"; $reason = "timeout de 5 minutos"
} else {
    $status = "failed"; $stage = "manage"; $reason = "lab ai-trader manage terminó con código $($result.code)"
}
Write-AiStatus -Root $root -Session $session -Status $status -Stage $stage -Reason $reason -Started $started -Log $log
$summary = Format-AiSummary -Root $root -Session $session -Status $status -Reason $reason -OutputLines $result.lines
Send-AiSummary -Root $root -Subject "TradingLab AI manage" -Body $summary
if ($status -eq "ok") { Send-TaskHeartbeat -Root $root -Check "ai-manage" -Status "ok"; exit 0 } else { Send-TaskHeartbeat -Root $root -Check "ai-manage" -Status "fail"; exit 2 }
