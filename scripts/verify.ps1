param(
    [string]$CodexHome = $(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }),
    [switch]$Live
)

$ErrorActionPreference = 'Stop'
$suiteRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $CodexHome 'secrets\ima-material-creation.env'

function Import-EnvFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $pair = $line -split '=', 2
        [Environment]::SetEnvironmentVariable($pair[0].Trim(), $pair[1].Trim(), 'Process')
    }
}

Import-EnvFile $envFile
$checks = @()
foreach ($name in @('ima-material-creation', 'external-image-channel', 'ima-skill')) {
    $path = Join-Path $CodexHome "skills\$name\SKILL.md"
    $checks += [pscustomobject]@{ Check = "skill:$name"; OK = Test-Path -LiteralPath $path; Detail = $path }
}

$keyPath = if ($env:EXTERNAL_IMAGE_KEYS_FILE) { $env:EXTERNAL_IMAGE_KEYS_FILE } else { Join-Path $CodexHome 'secrets\image_api_keys.txt' }
$checks += [pscustomobject]@{ Check = 'external-image-keys'; OK = (Test-Path -LiteralPath $keyPath); Detail = $keyPath }
foreach ($name in @('FEISHU_APP_ID', 'FEISHU_APP_SECRET', 'FEISHU_BASE_URL')) {
    $value = [Environment]::GetEnvironmentVariable($name, 'Process')
    $checks += [pscustomobject]@{ Check = $name; OK = -not [string]::IsNullOrWhiteSpace($value); Detail = $(if ($value) { 'configured' } else { 'missing' }) }
}

$checks | Format-Table -AutoSize
if ($checks.OK -contains $false) { throw 'Local validation failed. Fill missing items before live testing.' }

if ($Live) {
    & python (Join-Path $suiteRoot 'scripts\feishu_delivery.py') --check
    if ($LASTEXITCODE -ne 0) { throw 'Feishu live validation failed.' }
}

Write-Host 'Validation passed. IMA content access must also be confirmed inside Codex with ima-skill.'
