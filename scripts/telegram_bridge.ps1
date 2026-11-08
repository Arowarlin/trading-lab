# Puente Telegram persistente. Lo lanza la tarea TradingLab-Telegram al iniciar
# sesión. No abre puertos: hace long polling contra Telegram.
$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"

$root = "E:\trading-lab"
Set-Location $root

$config = Join-Path $root "config\telegram.yaml"
$logDir = Join-Path $root "logs\telegram"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("bridge_" + (Get-Date -Format "yyyyMMdd") + ".log")

if (-not (Test-Path $config)) {
    Add-Content -Path $log -Value "$(Get-Date -Format o) Falta config/telegram.yaml; ejecuta lab telegram setup."
    exit 1
}

while ($true) {
    Add-Content -Path $log -Value "$(Get-Date -Format o) Iniciando puente Telegram."
    & ".\.venv\Scripts\lab.exe" telegram bridge *>> $log
    $code = $LASTEXITCODE
    Add-Content -Path $log -Value "$(Get-Date -Format o) Puente terminó con código $code."
    if ($code -eq 2) {
        # Sin configuración válida: no tiene sentido reiniciar en bucle.
        exit 1
    }
    Start-Sleep -Seconds 10
}
