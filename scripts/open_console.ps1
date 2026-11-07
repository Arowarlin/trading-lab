# Abre TradingLab Console y la mantiene actualizada automaticamente.
# - Calcula el build actual de codigo/UI/config.
# - Si el panel esta viejo, lo reinicia.
# - Recrea el acceso directo en cada apertura.
# No activa bots, no arranca F13 y no envia ordenes.
param(
    [int]$Port = 8420,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$lab = Join-Path $root ".venv\Scripts\lab.exe"
$python = Join-Path $root ".venv\Scripts\python.exe"
$url = "http://127.0.0.1:$Port"
$creator = Join-Path $root "scripts\create_console_shortcut.ps1"
$shortcut = Join-Path $root "TradingLab Console.lnk"

function Get-CurrentBuild {
    if (-not (Test-Path $python)) { return $null }
    try {
        $output = & $python -c "from tradinglab.web import BUILD_ID; print(BUILD_ID)" 2>$null
        $line = @($output | Where-Object { $_ -and $_.Trim() } | Select-Object -Last 1)
        if (-not $line) { return $null }
        return $line.Trim()
    } catch {
        return $null
    }
}

function Get-Health {
    try {
        return Invoke-RestMethod -Uri "$url/api/health" -TimeoutSec 3
    } catch {
        return $null
    }
}

function Test-Current([string]$Build) {
    if (-not $Build) { return $false }
    $health = Get-Health
    return [bool]($health -and $health.ok -and $health.build -eq $Build)
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

# Actualiza el acceso directo (target, working dir, icon, description).
if (Test-Path $creator) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $creator *> $null
}

$build = Get-CurrentBuild
if (-not $build) {
    Show-Error "No se pudo calcular el build de TradingLab. Revisa la instalacion."
    exit 1
}

if (-not (Test-Current $build)) {
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

    for ($i = 0; $i -lt 50; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-Current $build) { break }
    }
}

if (-not (Test-Current $build)) {
    Show-Error "El panel no respondio o sigue desactualizado en $url. Revisa logs/web/server.log"
    exit 1
}

$openUrl = "$url/?v=$build"
if (-not $NoBrowser) {
    Start-Process $openUrl
} else {
    Write-Output "Console OK: $openUrl"
}
