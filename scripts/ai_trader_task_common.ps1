# Funciones comunes de las tareas del carril IA. Solo orquestación; la lógica
# de ventanas, preflight y candado vive en tradinglab.ai_session.
$ErrorActionPreference = "Stop"

function Get-AiLogPath {
    param([string]$Root, [string]$Session)
    $dir = Join-Path $Root "logs\ai_trader"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return (Join-Path $dir ("{0}_{1}.log" -f (Get-Date -Format "yyyy-MM-dd"), $Session))
}

function Write-AiLog {
    param([string]$Log, [string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::AppendAllText($Log, ("[{0}] {1}`r`n" -f $stamp, $Message), $utf8)
    Write-Output $Message
}

function Write-AiStatus {
    param(
        [string]$Root,
        [string]$Session,
        [string]$Status,
        [string]$Stage,
        [string]$Reason,
        [datetime]$Started,
        [string]$Log,
        $Extra = $null
    )
    $dir = Join-Path $Root "logs\ai_trader\status"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $now = (Get-Date).ToUniversalTime()
    $file = Join-Path $dir ("{0}_{1}_{2}.json" -f (Get-Date -Format "yyyy-MM-dd"), $Session, (Get-Date -Format "HHmmss"))
    $obj = [ordered]@{
        ts         = $now.ToString("o")
        session    = $Session
        status     = $Status
        stage      = $Stage
        reason     = $Reason
        started_at = $Started.ToUniversalTime().ToString("o")
        finished_at = $now.ToString("o")
        log        = $Log
        pid        = $PID
    }
    if ($Extra) {
        foreach ($key in $Extra.Keys) { $obj[$key] = $Extra[$key] }
    }
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($file, ($obj | ConvertTo-Json -Depth 5), $utf8)
}

function Invoke-AiPreflight {
    param([string]$Root, [string]$Session)
    $python = Join-Path $Root ".venv\Scripts\python.exe"
    $raw = & $python -m tradinglab.ai_session preflight --session $Session 2>$null
    if (-not $raw) {
        return [pscustomobject]@{ ok = $false; stage = "preflight"; reason = "preflight sin salida" }
    }
    try {
        return ($raw | ConvertFrom-Json)
    } catch {
        return [pscustomobject]@{ ok = $false; stage = "preflight"; reason = ($raw -join " ") }
    }
}

function Get-AiRecentDecisions {
    param([string]$Root, [int]$Limit = 8)
    $python = Join-Path $Root ".venv\Scripts\python.exe"
    $raw = & $python -m tradinglab.ai_session decisions --limit $Limit 2>$null
    if (-not $raw) { return @() }
    try { return @($raw | ConvertFrom-Json) } catch { return @() }
}

function Get-AiStatusJson {
    param([string]$Root)
    $lab = Join-Path $Root ".venv\Scripts\lab.exe"
    $raw = & $lab ai-trader status --json 2>$null
    if (-not $raw) { return $null }
    try { return ($raw | ConvertFrom-Json) } catch { return $null }
}

function Format-AiSummary {
    param(
        [string]$Root,
        [string]$Session,
        [string]$Status,
        [string]$Reason,
        $OutputLines = $null
    )
    $lines = @("IA discrecional · $Session · $Status")
    if ($Reason) { $lines += "Motivo: $Reason" }

    $decisions = Get-AiRecentDecisions -Root $Root -Limit 8
    if ($decisions.Count -gt 0) {
        $lines += "Decisiones:"
        foreach ($item in $decisions) {
            $lines += ("- {0} {1}/{2} {3}: {4} · {5}" -f $item.ts, $item.style, $item.symbol, $item.strategy, $item.decision, $item.reason)
        }
    } else {
        $lines += "Decisiones: Sin datos"
    }

    $statusData = Get-AiStatusJson -Root $Root
    if ($statusData) {
        $lines += ("Abiertas: {0}/{1}" -f $statusData.global.open_count, $statusData.global.max_open_total)
        foreach ($name in $statusData.styles.PSObject.Properties.Name) {
            $style = $statusData.styles.$name
            $hit = if ($style.stop_hit) { " · TOCADO" } else { "" }
            $lines += ("PnL {0}: {1:N2} USD · stop restante {2:N2} USD{3}" -f $name, $style.pnl_today, $style.stop_remaining_usd, $hit)
        }
        $globalHit = if ($statusData.global.stop_hit) { " · TOCADO" } else { "" }
        $lines += ("Global: stop restante {0:N2} USD{1}" -f $statusData.global.stop_remaining_usd, $globalHit)
        foreach ($position in $statusData.global.positions) {
            $lines += ("- {0} {1} {2} {3} · {4:N2} USD" -f $position.ticket, $position.symbol, $position.side, $position.volume, $position.profit)
        }
    } else {
        $lines += "Posiciones/PnL: Sin datos"
    }
    if ($OutputLines) {
        $lines += "Salida:"
        $lines += @($OutputLines | Select-Object -Last 8)
    }
    return ($lines -join "`n")
}

function Send-AiSummary {
    param([string]$Root, [string]$Subject, [string]$Body)
    $lab = Join-Path $Root ".venv\Scripts\lab.exe"
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        Set-Content -Path $tmp -Value $Body -Encoding utf8
        & $lab telegram send --file $tmp | Out-Null
        if ($LASTEXITCODE -ne 0) {
            & $lab alerts send ai_trader_task --message $Body --severity info | Out-Null
        }
    } catch {
        try { & $lab alerts send ai_trader_task --message $Body --severity info | Out-Null } catch { }
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
}
