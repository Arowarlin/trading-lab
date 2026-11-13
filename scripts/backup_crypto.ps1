# Cifra/descifra un backup con AES-256-CBC y PBKDF2. Solo .NET de Windows.
# La contraseña se pasa por TRADINGLAB_BACKUP_PASSWORD, nunca por argumento.
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("encrypt", "decrypt")]
    [string]$Mode,
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Out
)

$ErrorActionPreference = "Stop"
$password = $env:TRADINGLAB_BACKUP_PASSWORD
if (-not $password) { throw "Falta TRADINGLAB_BACKUP_PASSWORD" }
if (-not (Test-Path $Path)) { throw "No existe $Path" }
$magic = [System.Text.Encoding]::ASCII.GetBytes("TLBK1")

function New-Aes([byte[]]$key, [byte[]]$iv) {
    $aes = [System.Security.Cryptography.Aes]::Create()
    $aes.KeySize = 256
    $aes.Mode = [System.Security.Cryptography.CipherMode]::CBC
    $aes.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
    $aes.Key = $key
    $aes.IV = $iv
    return $aes
}

if ($Mode -eq "encrypt") {
    $salt = New-Object byte[] 16
    $iv = New-Object byte[] 16
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($salt)
    $rng.GetBytes($iv)
    $rng.Dispose()
    $derive = New-Object System.Security.Cryptography.Rfc2898DeriveBytes($password, $salt, 200000)
    $key = $derive.GetBytes(32)
    $derive.Dispose()
    $aes = New-Aes $key $iv
    $plain = [System.IO.File]::ReadAllBytes($Path)
    $cipher = $aes.CreateEncryptor().TransformFinalBlock($plain, 0, $plain.Length)
    $aes.Dispose()
    $stream = New-Object System.IO.MemoryStream
    $stream.Write($magic, 0, $magic.Length)
    $stream.Write($salt, 0, $salt.Length)
    $stream.Write($iv, 0, $iv.Length)
    $stream.Write($cipher, 0, $cipher.Length)
    [System.IO.File]::WriteAllBytes($Out, $stream.ToArray())
    $stream.Dispose()
    Write-Output "Cifrado: $Out"
    exit 0
}

$blob = [System.IO.File]::ReadAllBytes($Path)
if ($blob.Length -lt (5 + 16 + 16 + 16)) { throw "Archivo cifrado inválido" }
for ($i = 0; $i -lt $magic.Length; $i++) {
    if ($blob[$i] -ne $magic[$i]) { throw "Cabecera de cifrado inválida" }
}
$salt = New-Object byte[] 16
$iv = New-Object byte[] 16
[Array]::Copy($blob, 5, $salt, 0, 16)
[Array]::Copy($blob, 21, $iv, 0, 16)
$cipher = New-Object byte[] ($blob.Length - 37)
[Array]::Copy($blob, 37, $cipher, 0, $cipher.Length)
$derive = New-Object System.Security.Cryptography.Rfc2898DeriveBytes($password, $salt, 200000)
$key = $derive.GetBytes(32)
$derive.Dispose()
$aes = New-Aes $key $iv
$plain = $aes.CreateDecryptor().TransformFinalBlock($cipher, 0, $cipher.Length)
$aes.Dispose()
[System.IO.File]::WriteAllBytes($Out, $plain)
Write-Output "Descifrado: $Out"
exit 0
