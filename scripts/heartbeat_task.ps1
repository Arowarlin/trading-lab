# Latido Healthchecks.io para tareas programadas. Nunca falla la tarea.
function Send-TaskHeartbeat {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Check,
        [Parameter(Mandatory = $true)][string]$Status
    )
    try {
        $lab = Join-Path $Root ".venv\Scripts\lab.exe"
        if (Test-Path $lab) {
            & $lab heartbeat ping $Check --status $Status 2>$null | Out-Null
        }
    } catch {}
}
