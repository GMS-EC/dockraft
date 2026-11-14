param(
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $RepoRoot

$PyExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PyExe)) { $PyExe = "python" }

$Version = $env:DOCKRAFT_VERSION
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = & $PyExe -c "import re; from pathlib import Path; t = Path('CHANGELOG.md').read_text(encoding='utf-8') if Path('CHANGELOG.md').is_file() else ''; m = re.search(r'^##\s+\[(\d+\.\d+\.\d+(?:-[A-Za-z0-9.\-]+)?)\]', t, re.MULTILINE); print(m.group(1) if m else '1.6.0')"
}
$Version = $Version.Trim().TrimStart('v', 'V')

Write-Host "[1/3] Checking PyInstaller ($PyExe)..." -ForegroundColor Cyan
& $PyExe -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "      Installing Windows packaging dependencies (PyInstaller, pystray, pillow)..." -ForegroundColor Yellow
    & $PyExe -m pip install -r "$RepoRoot\requirements.txt" -r "$PSScriptRoot\requirements-windows.txt"
    if ($LASTEXITCODE -ne 0) { throw "Failed to install packaging dependencies." }
}

Write-Host "[2/3] Building portable Dockraft.exe v$Version with PyInstaller..." -ForegroundColor Cyan
$runningProcs = Get-Process -Name "Dockraft*" -ErrorAction SilentlyContinue
if ($runningProcs) {
    Write-Host "      Closing running Dockraft process(es) before rebuilding..." -ForegroundColor Yellow
    $runningProcs | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
}
& $PyExe -m PyInstaller --noconfirm --clean "$PSScriptRoot\dockraft.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

$BuiltExe = Join-Path $RepoRoot "dist\Dockraft.exe"
$PortableExe = Join-Path $RepoRoot "dist\Dockraft-$Version.exe"
if (-not (Test-Path $BuiltExe)) { throw "Expected executable not found at $BuiltExe" }
Copy-Item -Path $BuiltExe -Destination $PortableExe -Force
Write-Host "[3/3] Portable executable ready at: $PortableExe" -ForegroundColor Green
