# deploy.ps1 - Automates deployment of the Felicity ESS integration to Home Assistant server

param (
    [string]$DestDir = "\\192.168.100.5\config\custom_components\felicity_ess"
)

$ErrorActionPreference = "Stop"

$SourceDir = "$PSScriptRoot\custom_components\felicity_ess"

Write-Host "=== Starting Felicity ESS Integration Deployment ===" -ForegroundColor Cyan
Write-Host "Source: $SourceDir"
Write-Host "Destination: $DestDir"

# 1. Check destination folder accessibility
Write-Host "Checking accessibility of destination path: $DestDir..." -NoNewline
if (Test-Path $DestDir) {
    Write-Host " [EXISTS]" -ForegroundColor Green
} else {
    Write-Host " [CREATING DIRECTORY]" -ForegroundColor Yellow
    try {
        New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
        Write-Host "Successfully created $DestDir." -ForegroundColor Green
    } catch {
        Write-Error "Destination path $DestDir is not accessible. Error: $_"
    }
}

# 2. Synchronize files using robocopy
Write-Host "Synchronizing files..." -ForegroundColor Yellow
$exitCode = 0
try {
    robocopy $SourceDir $DestDir /MIR /XD __pycache__ /R:3 /W:5 /NDL /NFL | Out-Null
    $exitCode = $LASTEXITCODE
} catch {
    $exitCode = 8
}

if ($exitCode -ge 8) {
    Write-Error "Robocopy failed during synchronization (exit code: $exitCode)."
} else {
    Write-Host "Files synchronized successfully." -ForegroundColor Green
}

# 3. Clean remote __pycache__ directory
$RemoteCache = Join-Path $DestDir "__pycache__"
if (Test-Path $RemoteCache) {
    Write-Host "Cleaning remote __pycache__..." -ForegroundColor Yellow
    Remove-Item -Path $RemoteCache -Recurse -Force
    Write-Host "Remote __pycache__ directory deleted." -ForegroundColor Green
}

Write-Host "=== Deployment Completed Successfully ===" -ForegroundColor Green
