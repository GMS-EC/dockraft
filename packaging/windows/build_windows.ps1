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

Write-Host "[2/4] Building portable Dockraft-Windows-Portable-$Version.exe with PyInstaller..." -ForegroundColor Cyan
$runningProcs = Get-Process -Name "Dockraft*" -ErrorAction SilentlyContinue
if ($runningProcs) {
    Write-Host "      Closing running Dockraft process(es) before rebuilding..." -ForegroundColor Yellow
    $runningProcs | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
}
& $PyExe -m PyInstaller --noconfirm --clean "$PSScriptRoot\dockraft.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller portable build failed." }

$BuiltExe = Join-Path $RepoRoot "dist\Dockraft.exe"
$PortableExe = Join-Path $RepoRoot "dist\Dockraft-Windows-Portable-$Version.exe"
if (-not (Test-Path $BuiltExe)) { throw "Expected executable not found at $BuiltExe" }
Move-Item -Path $BuiltExe -Destination $PortableExe -Force
Write-Host "      Portable executable ready at: $PortableExe" -ForegroundColor Green

if (-not $SkipInstaller) {
    $iscc = (Get-Command "ISCC.exe" -ErrorAction SilentlyContinue).Source
    if (-not $iscc) {
        $candidatePaths = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
        )
        foreach ($cand in $candidatePaths) {
            if (Test-Path $cand) {
                $iscc = $cand
                break
            }
        }
    }
    if ($iscc) {
        Write-Host "[3/4] Building onedir bundle for Windows Setup..." -ForegroundColor Cyan
        & $PyExe -m PyInstaller --noconfirm --clean "$PSScriptRoot\dockraft_setup.spec"
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller setup bundle build failed." }

        Write-Host "[4/4] Building Dockraft-Windows-Setup-$Version.exe with Inno Setup..." -ForegroundColor Cyan
        & $iscc "/DMyAppVersion=$Version" "$PSScriptRoot\installer.iss"
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed." }
    } else {
        Write-Host "[3/4] Inno Setup (ISCC.exe) not found; skipping Setup.exe build." -ForegroundColor Yellow
    }
}
