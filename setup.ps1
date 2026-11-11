# setup.ps1 — One-command environment setup for Windows PowerShell
# Usage:
#   .\setup.ps1
#   OR from any agent: powershell -ExecutionPolicy Bypass -File setup.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   🎬  Video Guide Skill — setup.ps1          ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Python check ─────────────────────────────────────────────────────────────
$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        $version = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
        $major, $minor = $version.Split('.')[0,1]
        if ([int]$major -ge 3 -and [int]$minor -ge 11) {
            $python = $cmd
            Write-Host "  ✅  Python $version" -ForegroundColor Green
            break
        }
    }
}
if (-not $python) {
    Write-Host "  ❌  Python 3.11+ not found. Install from https://python.org/downloads/" -ForegroundColor Red
    exit 1
}

# ── Install uv ───────────────────────────────────────────────────────────────
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "  ℹ️   Installing uv..." -ForegroundColor Yellow
    # Try pip first
    $pipOk = & $python -m pip install --quiet uv 2>&1
    if ($LASTEXITCODE -ne 0) {
        # Fallback: official PowerShell installer
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    }
    # Refresh PATH
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" + $env:PATH
}
$uvVer = & uv --version
Write-Host "  ✅  $uvVer" -ForegroundColor Green

# ── Create venv + install ─────────────────────────────────────────────────────
if (-not (Test-Path ".venv")) {
    Write-Host "  ℹ️   Creating .venv..." -ForegroundColor Yellow
    & uv venv .venv
}
Write-Host "  ℹ️   Installing dependencies (first run may take ~1 min)..." -ForegroundColor Yellow
& uv pip install --quiet -e .
Write-Host "  ✅  Dependencies installed" -ForegroundColor Green

# ── Verify tools ─────────────────────────────────────────────────────────────
$verifyCode = @"
from tool_executor import TOOLS
from auto_recipe import scaffold_recipe
print('  ✅  Tools verified:', list(TOOLS.keys()))
"@
& .venv\Scripts\python.exe -c $verifyCode
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ❌  Tool verification failed. Check errors above." -ForegroundColor Red
    exit 1
}

# ── MCP server config snippet ─────────────────────────────────────────────────
$repoPath = $PSScriptRoot -replace '\\', '\\'
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  🎉  Setup complete!                                             ║" -ForegroundColor Cyan
Write-Host "╠══════════════════════════════════════════════════════════════════╣" -ForegroundColor Cyan
Write-Host "║                                                                  ║"
Write-Host "║  QUICKSTART:                                                     ║"
Write-Host "║  echo '{""tool"":""create_guide"",""video_path"":""C:/rec.mp4"",' |   ║"
Write-Host "║       python tool_executor.py                                    ║"
Write-Host "║                                                                  ║"
Write-Host "║  MCP SERVER: python mcp_server.py                                ║"
Write-Host "║                                                                  ║"
Write-Host "║  Add to Claude Desktop / Cursor mcp.json:                        ║"
Write-Host "║  { ""command"": "".venv\Scripts\python.exe"",                       ║"
Write-Host "║    ""args"": [""$PSScriptRoot\mcp_server.py""] }                     ║"
Write-Host "╚══════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
