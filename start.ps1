<#
    Wreckognise -- one-command local start (Windows / PowerShell).

        .\start.ps1            first run: creates the venv, installs everything
        .\start.ps1 -SkipSetup subsequent runs: just launch both servers

    Opens the API on :8000 and the dashboard on :5173.
#>

param(
    [switch]$SkipSetup
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

function Write-Step($message) {
    Write-Host ""
    Write-Host "==> $message" -ForegroundColor Cyan
}

function Require-Command($name, $hint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        Write-Host "Missing '$name'. $hint" -ForegroundColor Red
        exit 1
    }
}

Write-Host "Wreckognise -- automated marine survey agent" -ForegroundColor Yellow

Require-Command 'python' 'Install Python 3.11+ from https://python.org and re-open your terminal.'
Require-Command 'npm'    'Install Node.js 18+ from https://nodejs.org and re-open your terminal.'

$pythonExe = Join-Path $backend '.venv\Scripts\python.exe'

if (-not $SkipSetup) {
    Write-Step 'Creating the Python virtual environment'
    if (-not (Test-Path $pythonExe)) {
        python -m venv (Join-Path $backend '.venv')
    } else {
        Write-Host '   already present, reusing it'
    }

    Write-Step 'Installing backend dependencies'
    # The pinned set targets Python 3.11. On newer interpreters those exact
    # versions have no wheels, so fall back to the floors file.
    $version = & $pythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($version -eq '3.11') {
        $reqs = Join-Path $backend 'requirements.txt'
    } else {
        Write-Host "   Python $version detected -- using requirements-latest.txt"
        $reqs = Join-Path $backend 'requirements-latest.txt'
    }
    & $pythonExe -m pip install --quiet --upgrade pip
    & $pythonExe -m pip install --quiet -r $reqs
    & $pythonExe -m pip install --quiet httpx

    Write-Step 'Installing frontend dependencies'
    Push-Location $frontend
    npm install --no-audit --no-fund
    Pop-Location
}

if (-not (Test-Path $pythonExe)) {
    Write-Host 'No virtual environment found. Run without -SkipSetup first.' -ForegroundColor Red
    exit 1
}

Write-Step 'Starting the FastAPI backend on http://localhost:8000'
Start-Process -FilePath $pythonExe `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--reload', '--port', '8000' `
    -WorkingDirectory $backend

Start-Sleep -Seconds 3

Write-Step 'Starting the Vite dashboard on http://localhost:5173'
Start-Process -FilePath 'npm.cmd' -ArgumentList 'run', 'dev' -WorkingDirectory $frontend

Start-Sleep -Seconds 4
Write-Host ""
Write-Host "Dashboard  http://localhost:5173" -ForegroundColor Green
Write-Host "API docs   http://localhost:8000/docs" -ForegroundColor Green
Write-Host ""
Write-Host "Both servers run in their own windows -- close them to stop." -ForegroundColor DarkGray

Start-Process 'http://localhost:5173'
