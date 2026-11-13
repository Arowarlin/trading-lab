# Instala Vector 0.61.0 (versión fija) desde el release oficial.
# NO se ejecuta automáticamente: lo lanza el operador con permisos de admin.
# No instala dependencias de Python ni envía datos a la red.
param(
    [string]$Version = "0.61.0",
    [switch]$Portable,
    [switch]$StartService
)

$ErrorActionPreference = "Stop"
$root = "E:\trading-lab"
$installDir = Join-Path $root "data\vector\install"
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $root "logs\vector") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $root "data\vector") | Out-Null

$expected = @{
    "vector-$Version-x64.msi" = "3ac167f226204e141d164c6218ae54a2df77dda1b3322bef4b565d4066c4cfad"
    "vector-$Version-x86_64-pc-windows-msvc.zip" = "6a04e833f9a91f874688e8087d768f5cb35d40e3271c87df6258e271915d0f49"
}
$name = if ($Portable) {
    "vector-$Version-x86_64-pc-windows-msvc.zip"
} else {
    "vector-$Version-x64.msi"
}
$file = Join-Path $installDir $name
$url = "https://github.com/vectordotdev/vector/releases/download/v$Version/$name"

if (-not (Test-Path $file)) {
    Write-Output "Descargando $url"
    Invoke-WebRequest -Uri $url -OutFile $file -UseBasicParsing
}
$hash = (Get-FileHash $file -Algorithm SHA256).Hash.ToLower()
if ($hash -ne $expected[$name]) {
    throw "SHA256 no coincide para $name. Esperado $($expected[$name]), obtenido $hash"
}
Write-Output "SHA256 OK: $hash"

$configSource = Join-Path $root "config\vector\vector.yaml"
if ($Portable) {
    $binDir = Join-Path $root "data\vector\bin"
    if (Test-Path $binDir) { Remove-Item $binDir -Recurse -Force }
    Expand-Archive -Path $file -DestinationPath $binDir -Force
    $vector = Join-Path $binDir "vector.exe"
    $configTarget = Join-Path $root "data\vector\vector.yaml"
    Copy-Item $configSource $configTarget -Force
    & $vector validate $configTarget
    Write-Output "Portable instalado en $binDir"
    Write-Output "Arranque manual: `"$vector`" --config `"$configTarget`""
} else {
    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
    if (-not $isAdmin) {
        throw "El MSI requiere una consola elevada (Ejecutar como administrador)."
    }
    $msiArgs = "/i `"$file`" /qn /norestart"
    $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList $msiArgs -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        throw "msiexec terminó con código $($proc.ExitCode)"
    }
    $vector = "C:\Program Files\Vector\vector.exe"
    $configTarget = "C:\ProgramData\vector\vector.yaml"
    New-Item -ItemType Directory -Force -Path (Split-Path $configTarget) | Out-Null
    Copy-Item $configSource $configTarget -Force
    & $vector validate $configTarget
    Write-Output "MSI instalado. Configuración copiada a $configTarget"
    if ($StartService) {
        Start-Service -Name vector
        Write-Output "Servicio vector iniciado."
    } else {
        Write-Output "Para arrancar el servicio: Start-Service -Name vector"
    }
}
Write-Output "Siguiente: .\scripts\vector_test.ps1"
