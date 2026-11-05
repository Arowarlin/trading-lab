# Espera a que LM Studio termine la descarga de Qwen3.8-27B, verifica el SHA256,
# carga el modelo con ajustes para 16 GB de VRAM y ejecuta las pruebas del lab.

$ErrorActionPreference = "Continue"
$dir   = "$env:USERPROFILE\.lmstudio\models\lmstudio-community\Qwen3.8-27B-GGUF"
$final = Join-Path $dir "Qwen3.8-27B-Q4_K_M.gguf"
$part  = Join-Path $dir "downloading_Qwen3.8-27B-Q4_K_M.gguf.part"
$lms   = "$env:USERPROFILE\.lmstudio\bin\lms.exe"
$lab   = "E:\trading-lab\.venv\Scripts\lab.exe"
$expectedHash = "e00082f779fa385cee8c68a3ec8833a75778cc87272240b942f74e0b8243e520"
$expectedSize = 16810714336

$env:PYTHONUTF8 = "1"

Write-Output "[$(Get-Date -Format HH:mm:ss)] Vigilando la descarga..."

$deadline = (Get-Date).AddHours(5)
while ((Get-Date) -lt $deadline) {
    if (Test-Path $final) { break }
    if (Test-Path $part) {
        $mb = [math]::Round((Get-Item $part).Length / 1MB, 1)
        Write-Output "[$(Get-Date -Format HH:mm:ss)] parcial: $mb MB"
    } else {
        Write-Output "[$(Get-Date -Format HH:mm:ss)] sin archivo parcial todavia"
    }
    Start-Sleep -Seconds 60
}

if (-not (Test-Path $final)) {
    Write-Output "TIMEOUT: la descarga no termino en 5 horas."
    exit 1
}

Write-Output "[$(Get-Date -Format HH:mm:ss)] Descarga terminada. Esperando a que se libere el archivo..."
for ($i = 0; $i -lt 180; $i++) {
    try {
        $fs = [IO.File]::Open($final, 'Open', 'Read', 'None')
        $fs.Close()
        break
    } catch {
        Start-Sleep -Seconds 10
    }
}

$size = (Get-Item $final).Length
Write-Output "Tamano: $size bytes (esperado $expectedSize)"

Write-Output "Calculando SHA256 (puede tardar 1-3 min)..."
$hash = (Get-FileHash $final -Algorithm SHA256).Hash.ToLower()
Write-Output "SHA256: $hash"

if ($hash -ne $expectedHash) {
    Write-Output "ERROR: SHA256 no coincide. El archivo esta corrupto; hay que redescargarlo."
    exit 2
}
Write-Output "SHA256 OK"

Write-Output "[$(Get-Date -Format HH:mm:ss)] Cargando el modelo en LM Studio..."
& $lms load $final --identifier "qwen3.8-27b" --context-length 16384 --ttl 7200 -y 2>&1
& $lms server start --port 1234 2>&1
Start-Sleep -Seconds 3
& $lms ps 2>&1

Write-Output "[$(Get-Date -Format HH:mm:ss)] Prueba del servidor y modo JSON..."
& $lab llm-test 2>&1
Write-Output "[$(Get-Date -Format HH:mm:ss)] Diagnostico final:"
& $lab doctor 2>&1
