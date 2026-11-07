# Abre TradingLab Console en el navegador.
# Si el panel ya esta vivo, lo reutiliza; si no, lo arranca en segundo plano.
# No activa bots, no arranca F13 y no envia ordenes.
param(
    [int]$Port = 8420,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$url = "http://127.0.0.1:$Port"

function Test-Console {
    try {
        $health = Invoke-RestMethod -Uri "$url/api/health" -TimeoutSec 2
        return [bool]$health.ok
    } catch {
        return $false
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

if (-not (Test-Console)) {
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
        if (Test-Console) { break }
    }
}

if (-not (Test-Console)) {
    Show-Error "El panel no respondio en $url. Revisa logs o ejecuta: lab web --port $Port"
    exit 1
}

if (-not $NoBrowser) {
    Start-Process $url
} else {
    Write-Output "Console OK: $url"
}
