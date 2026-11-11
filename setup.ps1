# setup.ps1 — One-command environment setup for Windows PowerShell
# Usage:
#   .\setup.ps1
#   .\setup.ps1 -InstallSkill
#   OR: powershell -ExecutionPolicy Bypass -File setup.ps1

param(
    [switch]$InstallSkill,
    [switch]$PrintMcp
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($ver) {
            $parts = $ver.Split('.')
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 11) {
                $python = $cmd
                break
            }
        }
    }
}
if (-not $python) {
    Write-Host "[FAIL] Python 3.11+ is required. Install from https://python.org/downloads/" -ForegroundColor Red
    exit 1
}

$bootArgs = @("bootstrap.py")
if ($InstallSkill) { $bootArgs += "--install-skill" }
if ($PrintMcp) { $bootArgs += "--print-mcp" }

& $python @bootArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
