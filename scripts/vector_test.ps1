# Ejecuta los unit tests nativos de Vector (sección `tests` del YAML).
# Falla si Vector no está instalado o si algún caso no pasa.
$ErrorActionPreference = "Stop"
$root = "E:\trading-lab"
$config = Join-Path $root "config\vector\vector.yaml"

$candidates = @(
    "C:\Program Files\Vector\bin\vector.exe",
    (Join-Path $root "data\vector\bin\vector.exe")
)
$vector = $null
foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
        $vector = $candidate
        break
    }
}
if (-not $vector) {
    $cmd = Get-Command vector.exe -ErrorAction SilentlyContinue
    if ($cmd) { $vector = $cmd.Source }
}
if (-not $vector) {
    Write-Error "Vector no está instalado. Ejecuta scripts\vector_install.ps1."
    exit 1
}

& $vector test $config
exit $LASTEXITCODE
