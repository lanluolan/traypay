# Generates local configuration only. Does not start Docker or install anything.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$dockerEnvPath = Join-Path $projectRoot '.env'
$backendEnvPath = Join-Path $projectRoot 'backend/.env'
$templatePath = Join-Path $projectRoot 'backend/.env.example'

foreach ($target in @($dockerEnvPath, $backendEnvPath)) {
    if (Test-Path -LiteralPath $target) {
        throw "Configuration already exists: $target. No files were changed."
    }
}

function New-LocalSecret {
    $bytes = New-Object byte[] 32
    $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $random.GetBytes($bytes) } finally { $random.Dispose() }
    return ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
}

$appPassword = New-LocalSecret
$rootPassword = New-LocalSecret
$testPassword = New-LocalSecret
$testRootPassword = New-LocalSecret
$signingKey = New-LocalSecret
$dockerConfig = @(
    '# Generated local credentials. Do not commit.'
    "MYSQL_ROOT_PASSWORD=$rootPassword"
    "MYSQL_PASSWORD=$appPassword"
    "MYSQL_TEST_ROOT_PASSWORD=$testRootPassword"
    "MYSQL_TEST_PASSWORD=$testPassword"
) -join "`n"

$backendConfig = [IO.File]::ReadAllText($templatePath)
$backendConfig = $backendConfig.Replace('DB_PASSWORD=change-me', "DB_PASSWORD=$appPassword")
$backendConfig = $backendConfig.Replace('DB_PORT=3306', 'DB_PORT=3307')
$backendConfig = $backendConfig.Replace('SECRET_KEY=change-me-generate-a-real-one', "SECRET_KEY=$signingKey")
$encoding = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($dockerEnvPath, $dockerConfig + "`n", $encoding)
[IO.File]::WriteAllText($backendEnvPath, $backendConfig, $encoding)
Write-Output 'Created .env and backend/.env. Passwords were not printed.'
Write-Output 'Development database: 127.0.0.1:3307/payment (user checkout).'
Write-Output 'Optional test database: 127.0.0.1:3308/payment_test (user checkout_test).'
