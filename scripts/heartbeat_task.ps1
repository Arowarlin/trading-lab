# Latido Healthchecks.io para tareas programadas. Nunca falla la tarea.
function Send-TaskHeartbeat {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Check,
        [Parameter(Mandatory = $true)][string]$Status,
        [string]$Message = ""
    )
    try {
        $lab = Join-Path $Root ".venv\Scripts\lab.exe"
        if (Test-Path $lab) {
            $arguments = @("heartbeat", "ping", $Check, "--status", $Status)
            if ($Message) {
                $arguments += @("--message", $Message)
            }
            & $lab @arguments 2>$null | Out-Null
        }
    } catch {}
}
