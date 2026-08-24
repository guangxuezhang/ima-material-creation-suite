param(
    [string]$CodexHome = $(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' })
)

$ErrorActionPreference = 'Stop'
$suiteRoot = Split-Path -Parent $PSScriptRoot
$skillsRoot = Join-Path $CodexHome 'skills'
New-Item -ItemType Directory -Force -Path $skillsRoot | Out-Null

foreach ($name in @('ima-material-creation', 'external-image-channel')) {
    $source = Join-Path $suiteRoot "skills\$name"
    $target = Join-Path $skillsRoot $name
    if (-not (Test-Path -LiteralPath $source)) { throw "Missing packaged skill: $source" }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -Recurse -Force -Path (Join-Path $source '*') -Destination $target
    Write-Host "Installed $name -> $target"
}

$secretsRoot = Join-Path $CodexHome 'secrets'
New-Item -ItemType Directory -Force -Path $secretsRoot | Out-Null
$example = Join-Path $suiteRoot 'config\.env.example'
$localEnv = Join-Path $secretsRoot 'ima-material-creation.env'
if (-not (Test-Path -LiteralPath $localEnv)) {
    Copy-Item -LiteralPath $example -Destination $localEnv
    Write-Host "Created local configuration template: $localEnv"
} else {
    Write-Host "Kept existing local configuration: $localEnv"
}

Write-Host 'Installation complete. Fill the local configuration, connect ima-skill, then run scripts\verify.ps1.'
