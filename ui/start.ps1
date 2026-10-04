$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$php = Join-Path $PSScriptRoot 'runtime\php\php.exe'
if (-not (Test-Path -LiteralPath $php)) {
    throw "No se encontró PHP en: $php"
}

$secureKey = Read-Host 'Pega tu nueva clave API (entrada oculta)' -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $env:OPENAI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    & $php -S localhost:8000
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
}
