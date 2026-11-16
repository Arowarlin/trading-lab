# Preflight de LM Studio para las tareas que usan el LLM.
# Si el puerto 1234 no responde, llama a lmstudio_start.ps1 -Quick y espera
# hasta 90 s. El llamador decide qué hacer si devuelve $false: seguir sin LLM
# ("Sin datos"), nunca inventar una respuesta.
#
# Uso:
#   . (Join-Path $PSScriptRoot "llm_preflight.ps1")
#   if (Ensure-LMStudio -Log $log) { ... } else { "Sin datos" }

function Test-LMStudioPort {
    param([int]$TimeoutMs = 2000)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect("127.0.0.1", 1234, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs)) { return $false }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-LMStudio {
    param([int]$TimeoutSec = 3)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec $TimeoutSec `
            "http://127.0.0.1:1234/v1/models"
        return ($response.StatusCode -eq 200)
    } catch {
        # Un modelo en CPU puede tardar en contestar HTTP sin estar caído.
        # Si el puerto sigue abierto, no se reinicia LM Studio.
        return (Test-LMStudioPort)
    }
}

function Write-PreflightLog {
    param([string]$Log, [string]$Message)
    if (-not $Log) { return }
    try {
        Add-Content -Path $Log -Encoding utf8 -Value (
            "{0} [preflight] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
        )
    } catch {
        # El log nunca debe tumbar la tarea.
    }
}

function Ensure-LMStudio {
    param([string]$Log, [int]$WaitSeconds = 90)
    $started = Get-Date
    if (Test-LMStudio) {
        Write-PreflightLog -Log $Log -Message "LM Studio ya responde en 1234"
        return $true
    }

    $starter = Join-Path $PSScriptRoot "lmstudio_start.ps1"
    if (-not (Test-Path $starter)) {
        Write-PreflightLog -Log $Log -Message "Sin datos: no existe $starter"
        return $false
    }

    Write-PreflightLog -Log $Log -Message "LM Studio no responde; arrancando con lmstudio_start.ps1 -Quick"
    if ($Log) {
        & $starter -Quick *>> $Log
    } else {
        & $starter -Quick *> $null
    }

    $deadline = $started.AddSeconds([Math]::Max(1, $WaitSeconds))
    while ((Get-Date) -lt $deadline) {
        if (Test-LMStudio) {
            Write-PreflightLog -Log $Log -Message "LM Studio listo"
            return $true
        }
        Start-Sleep -Seconds 3
    }
    Write-PreflightLog -Log $Log -Message (
        "Sin datos: LM Studio no respondió en {0} s" -f $WaitSeconds
    )
    return $false
}
