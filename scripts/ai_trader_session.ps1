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
$check = "ai-$Session"
function Send-Heartbeat([string]$Status) {
    try {
        & $lab heartbeat ping $check --status $Status 2>$null | Out-Null
    } catch {}
}
Send-Heartbeat "start"
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
    Send-Heartbeat "ok"
    exit 0
}

try {
    $pre = Invoke-AiPreflight -Root $root -Session $Session
    if (-not $pre.ok) {
        $skippedStages = @("window", "killswitch", "account_stop", "global_stop", "market")
        $status = if ($skippedStages -contains $pre.stage) { "skipped" } else { "failed" }
        Write-AiLog -Log $log -Message ("salida temprana [{0}]: {1}" -f $pre.stage, $pre.reason)
        Write-AiStatus -Root $root -Session $Session -Status $status -Stage $pre.stage -Reason $pre.reason -Started $started -Log $log
        $summary = Format-AiSummary -Root $root -Session $Session -Status $status -Reason $pre.reason
        Send-AiSummary -Root $root -Subject "TradingLab AI $Session" -Body $summary
        if ($status -eq "failed") { Send-Heartbeat "fail"; exit 2 } else { Send-Heartbeat "ok"; exit 0 }
    }

    if ($Session -eq "ny") {
        $plansRaw = & $lab ai-trader plans 2>$null
        $plans = @()
        try { $plans = @($plansRaw | ConvertFrom-Json) } catch { $plans = @() }
        $defaults = @(
            @{
                symbol = "US100.cash"
                setups = @("ema_ribbon_pullback", "vwap_bounce", "orb_5m", "momentum_burst")
                bias = "both"
                forbidden_hours = @("09:30-09:45", "11:30-12:00")
                reason = "plan NY automatico US100"
            },
            @{
                symbol = "XAUUSD"
                setups = @("ema_ribbon_pullback", "vwap_bounce", "orb_5m", "momentum_burst")
                bias = "both"
                forbidden_hours = @("09:30-09:45", "11:30-12:00")
                reason = "plan NY automatico XAUUSD"
            }
        )
        foreach ($item in $defaults) {
            $already = @($plans | Where-Object { $_.symbol -eq $item.symbol })
            if ($already.Count -gt 0) { continue }
            $tmp = Join-Path $env:TEMP ("tradinglab-plan-{0}-{1}.json" -f $item.symbol, [guid]::NewGuid().ToString("N"))
            try {
                $json = $item | ConvertTo-Json -Compress -Depth 6
                [System.IO.File]::WriteAllText($tmp, $json, [System.Text.UTF8Encoding]::new($false))
                $planOut = & $lab ai-trader plan --json-file $tmp 2>&1
                Write-AiLog -Log $log -Message (($planOut | Out-String).Trim())
            } catch {
                Write-AiLog -Log $log -Message ("plan automatico fallo: {0}" -f $_.Exception.Message)
            } finally {
                Remove-Item $tmp -Force -ErrorAction SilentlyContinue
            }
        }
    }

    $model = "opencode-go/deepseek-v4.1-flash"
    $env:TRADINGLAB_AI_MODEL = $model
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
    if ($status -eq "ok") { Send-Heartbeat "ok"; exit 0 } else { Send-Heartbeat "fail"; exit 2 }
}
finally {
    & $python -m tradinglab.ai_session lock-release --path $lockPath --pid $PID 2>$null | Out-Null
}
