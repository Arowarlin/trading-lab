# Abre TradingLab Console en el navegador.
# Si el panel ya esta vivo y actualizado, lo reutiliza; si es un servidor
# viejo o no responde, lo reinicia en segundo plano.
# No activa bots, no arranca F13 y no envia ordenes.
param(
    [int]$Port = 8420,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$url = "http://127.0.0.1:$Port"

function Test-Health {
    try {
        $health = Invoke-RestMethod -Uri "$url/api/health" -TimeoutSec 2
        return [bool]$health.ok
    } catch {
        return $false
    }
}

function Test-Current {
    try {
        $overview = Invoke-RestMethod -Uri "$url/api/overview" -TimeoutSec 8
        $names = @($overview.research.PSObject.Properties.Name)
        return ($names -contains "portfolio") -and ($names -contains "costs")
    } catch {
        return $false
    }
}

function Stop-OldServer {
    $pattern = "web --no-open --port $Port"
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.ProcessId -ne $PID -and
            $_.CommandLine -and
            ($_.Name -eq "lab.exe" -or $_.Name -eq "python.exe") -and
            $_.CommandLine -match [regex]::Escape($pattern)
        } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

function Show-Error([string]$Message) {
    try {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show(
            $Message,
            "TradingLab Console",
            [System.Windows.MessageBoxButton]::OK,
            [System.Windows.MessageBoxImage]::Error
        ) | Out-Null
    } catch {
        Write-Error $Message
    }
}

if (-not (Test-Health) -or -not (Test-Current)) {
    Stop-OldServer
    Start-Sleep -Seconds 1
    if (-not (Test-Path $lab)) {
        Show-Error "No existe $lab. Revisa la instalacion de TradingLab."
        exit 1
    }
    Start-Process -FilePath $lab `
        -ArgumentList @("web", "--no-open", "--port", "$Port") `
        -WorkingDirectory $root `
        -WindowStyle Hidden | Out-Null

    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 500
        if ((Test-Health) -and (Test-Current)) { break }
    }
}

if (-not (Test-Health) -or -not (Test-Current)) {
    Show-Error "El panel no respondio o sigue desactualizado en $url. Revisa logs o ejecuta: lab web --port $Port"
    exit 1
}

$cacheBuster = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$openUrl = "$url/?v=$cacheBuster"
if (-not $NoBrowser) {
    Start-Process $openUrl
} else {
    Write-Output "Console OK: $openUrl"
}
