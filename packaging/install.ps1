# Install Vigil for the current Windows user: venv, PATH, Start Menu, then point at setup.
# Run from a clone:  powershell -ExecutionPolicy Bypass -File .\packaging\install.ps1
# Or double-click packaging\install.bat
param(
    [switch]$Setup
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Venv = Join-Path $env:LOCALAPPDATA "vigil\venv"
$Scripts = Join-Path $Venv "Scripts"
$Python = $null

foreach ($candidate in @("py", "python", "python3")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($null -ne $cmd) {
        if ($candidate -eq "py") {
            & py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $Python = "py -3"
                break
            }
        } else {
            & $cmd.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $Python = $cmd.Source
                break
            }
        }
    }
}

if ($null -eq $Python) {
    Write-Host "Python 3.11+ not found. Install it from https://www.python.org/downloads/"
    Write-Host "During setup, enable 'Add python.exe to PATH'."
    exit 1
}

Write-Host "Using Python: $Python"
Write-Host "Installing into $Venv"

New-Item -ItemType Directory -Force -Path $Venv | Out-Null
if ($Python -eq "py -3") {
    py -3 -m venv $Venv
} else {
    & $Python -m venv $Venv
}

& (Join-Path $Scripts "python.exe") -m pip install --upgrade pip
& (Join-Path $Scripts "pip.exe") install $Root

$VigilExe = Join-Path $Scripts "vigil.exe"
if (-not (Test-Path $VigilExe)) {
    Write-Host "Install finished but vigil.exe is missing under $Scripts" -ForegroundColor Red
    exit 1
}

# User PATH
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ([string]::IsNullOrEmpty($userPath)) { $userPath = "" }
$parts = $userPath.Split(";", [System.StringSplitOptions]::RemoveEmptyEntries)
$normalized = $Scripts.TrimEnd("\")
$already = $false
foreach ($part in $parts) {
    if ($part.TrimEnd("\").ToLowerInvariant() -eq $normalized.ToLowerInvariant()) {
        $already = $true
        break
    }
}
if (-not $already) {
    $newPath = if ($userPath.Trim().Length -eq 0) { $Scripts } else { "$userPath;$Scripts" }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    $env:Path = "$Scripts;$env:Path"
    Write-Host "Added to user PATH: $Scripts"
} else {
    Write-Host "User PATH already includes: $Scripts"
}

# Start Menu + monthly task via Vigil itself
& $VigilExe desktop

Write-Host ""
Write-Host "Install complete."
Write-Host "Next: open a NEW terminal (so PATH updates), then run:"
Write-Host "  vigil setup"
Write-Host "Or:  python -m vigil setup"
Write-Host "Start Menu also has Vigil, Vigil Setup, and Vigil Tray."

if ($Setup) {
    Write-Host ""
    Write-Host "Launching first-run wizard..."
    & $VigilExe setup
}
