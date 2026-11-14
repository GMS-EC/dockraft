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

Write-Host "[2/3] Building dist\Dockraft v$Version with PyInstaller..." -ForegroundColor Cyan
$runningProcs = Get-Process -Name "Dockraft" -ErrorAction SilentlyContinue
if ($runningProcs) {
    Write-Host "      Closing running Dockraft.exe process(es) before rebuilding..." -ForegroundColor Yellow
    Stop-Process -Name "Dockraft" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
}
& $PyExe -m PyInstaller --noconfirm --clean "$PSScriptRoot\dockraft.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

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
        Write-Host "[3/3] Building Windows Installer v$Version with Inno Setup..." -ForegroundColor Cyan
        & $iscc "/DMyAppVersion=$Version" "$PSScriptRoot\installer.iss"
    } else {
        Write-Host "[3/3] Inno Setup (ISCC.exe) not found; skipping Setup.exe build." -ForegroundColor Yellow
        Write-Host "      Executable ready at: $RepoRoot\dist\Dockraft\Dockraft.exe" -ForegroundColor Green
    }
}
