# Crea (o repara) el acceso directo "TradingLab Console.lnk" en la raiz del repo.
# Es seguro ejecutarlo varias veces: sobrescribe el .lnk, no borra nada mas.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root "TradingLab Console.lnk"
$launcher = Join-Path $root "scripts\open_console.ps1"
$powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

if (-not (Test-Path $launcher)) {
    throw "No existe $launcher"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($target)
$shortcut.TargetPath = $powershell
$shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $launcher + '"'
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = "$env:SystemRoot\System32\SHELL32.dll,13"
$shortcut.Description = "Abrir TradingLab Console (paper, sin ordenes)"
$shortcut.Save()

Write-Output "Acceso directo: $target"
Write-Output "Destino: $powershell"
Write-Output "Script: $launcher"
