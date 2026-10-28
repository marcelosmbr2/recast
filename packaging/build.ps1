# Builds dist\Recast (PyInstaller bundle) and dist\Recast-<version>-Setup.exe (Inno Setup).
# Usage: powershell -ExecutionPolicy Bypass -File packaging\build.ps1 [-SkipSelfTest]
param([switch]$SkipSelfTest)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

function Invoke-Checked([string]$what, [scriptblock]$cmd) {
    & $cmd
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" }
}

$version = (uv run python -c "import recast; print(recast.__version__)").Trim()
Write-Host "Building Recast $version"

Invoke-Checked "uv sync" { uv sync }
Invoke-Checked "icon" { uv run python packaging\make_icon.py build\recast.ico }
Invoke-Checked "PyInstaller" {
    uv run pyinstaller packaging\recast.spec --noconfirm --clean --distpath dist --workpath build\pyinstaller
}

if (-not $SkipSelfTest) {
    # The exe is windowed, so it reports into a file; Start-Process -Wait gives us its exit code.
    $report = Join-Path $root "build\selftest.txt"
    $proc = Start-Process -FilePath "dist\Recast\Recast.exe" -ArgumentList "--self-test", "`"$report`"" -Wait -PassThru
    Get-Content $report
    if ($proc.ExitCode -ne 0) { throw "Self-test of the bundled app failed" }
}

$iscc = @(
    $env:ISCC,
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { $iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source }
if (-not $iscc) { throw "Inno Setup 6 (ISCC.exe) not found; install it or set `$env:ISCC" }

Invoke-Checked "Inno Setup" { & $iscc "/DAppVersion=$version" packaging\recast.iss }
Write-Host "Installer: dist\Recast-$version-Setup.exe"
