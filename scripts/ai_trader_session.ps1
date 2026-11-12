# Sesión discrecional del carril IA. NO la registra este script: el operador
# decide cuándo ejecutar register_ai_trader_tasks.ps1.
#
# Sale sin llamar al LLM si la ventana local no corresponde, el mercado está
# cerrado, el kill-switch/stop global está activo, MT5 no responde o la cuenta
# no es demo. Todo queda en logs/ai_trader/.
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("london", "ny", "daily")]
    [string]$Session
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "ai_trader_task_common.ps1")
$python = Join-Path $root ".venv\Scripts\python.exe"
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$started = Get-Date
$log = Get-AiLogPath -Root $root -Session $Session
$lockPath = Join-Path $root "logs\ai_trader\ai_trader.lock"

Write-AiLog -Log $log -Message "inicio sesión $Session"

$lockRaw = & $python -m tradinglab.ai_session lock-acquire --path $lockPath --session $Session --pid $PID 2>$null
$lock = $null
try { $lock = $lockRaw | ConvertFrom-Json } catch { $lock = $null }
if (-not $lock -or -not $lock.ok) {
    $reason = if ($lock) { $lock.reason } else { "candado no disponible" }
    Write-AiLog -Log $log -Message "salida temprana: $reason"
    Write-AiStatus -Root $root -Session $Session -Status "skipped" -Stage "lock" -Reason $reason -Started $started -Log $log
    $summary = Format-AiSummary -Root $root -Session $Session -Status "skipped" -Reason $reason
    Send-AiSummary -Root $root -Subject "TradingLab AI $Session" -Body $summary
    exit 0
}

try {
    $pre = Invoke-AiPreflight -Root $root -Session $Session
    if (-not $pre.ok) {
        $skippedStages = @("window", "killswitch", "global_stop", "market")
        $status = if ($skippedStages -contains $pre.stage) { "skipped" } else { "failed" }
        Write-AiLog -Log $log -Message ("salida temprana [{0}]: {1}" -f $pre.stage, $pre.reason)
        Write-AiStatus -Root $root -Session $Session -Status $status -Stage $pre.stage -Reason $pre.reason -Started $started -Log $log
        $summary = Format-AiSummary -Root $root -Session $Session -Status $status -Reason $pre.reason
        Send-AiSummary -Root $root -Subject "TradingLab AI $Session" -Body $summary
        if ($status -eq "failed") { exit 2 } else { exit 0 }
    }

    $model = "opencode-go/deepseek-v4.1-flash"
    $message = "Usa el skill trading-lab-operador. Sesión ${Session}: sigue el procedimiento del skill para esta sesión. Termina con una línea por decisión y el scoreboard."
    $job = Start-Job -ScriptBlock {
        param($root, $model, $message)
        Set-Location $root
        $env:PATH = "$root\.venv\Scripts;$env:PATH"
        $out = & opencode run --standalone --agent ai-operator --model $model --auto $message 2>&1
        $code = if ($null -eq $LASTEXITCODE) { 1 } else { $LASTEXITCODE }
        [pscustomobject]@{ code = $code; lines = @($out) }
    } -ArgumentList $root, $model, $message

    $done = Wait-Job $job -Timeout 600
    if ($null -eq $done) {
        Stop-Job $job -ErrorAction SilentlyContinue
        $result = [pscustomobject]@{ code = 124; lines = @("timeout de 10 minutos") }
    } else {
        $result = Receive-Job $job -Keep
    }
    Remove-Job $job -Force -ErrorAction SilentlyContinue

    $text = ($result.lines | Out-String)
    Write-AiLog -Log $log -Message $text

    if ($Session -eq "daily") {
        Write-AiLog -Log $log -Message "learn diario"
        $learnOut = & $lab ai-trader learn 2>&1
        Write-AiLog -Log $log -Message (($learnOut | Out-String).Trim())
        if ($LASTEXITCODE -ne 0) {
            Write-AiLog -Log $log -Message "learn falló con código $LASTEXITCODE"
        }
    }

    if ($result.code -eq 0) {
        $status = "ok"
        $stage = "llm"
        $reason = "sesión completada"
    } elseif ($result.code -eq 124) {
        $status = "failed"
        $stage = "timeout"
        $reason = "timeout de 10 minutos"
    } else {
        $status = "failed"
        $stage = "llm"
        $reason = "opencode run terminó con código $($result.code)"
    }
    Write-AiStatus -Root $root -Session $Session -Status $status -Stage $stage -Reason $reason -Started $started -Log $log
    $summary = Format-AiSummary -Root $root -Session $Session -Status $status -Reason $reason -OutputLines $result.lines
    Send-AiSummary -Root $root -Subject "TradingLab AI $Session" -Body $summary
    if ($status -eq "ok") { exit 0 } else { exit 2 }
}
finally {
    & $python -m tradinglab.ai_session lock-release --path $lockPath --pid $PID 2>$null | Out-Null
}
