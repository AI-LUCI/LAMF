<#
.SYNOPSIS
    Builds the one-file Windows GUI installer, dist\LAMF.exe.

.DESCRIPTION
    Creates an isolated build virtual environment (so PyInstaller is never
    installed into the user's Python or into runtime\.venv), runs PyInstaller
    against installer\LAMF.spec, and reports the resulting size and SHA-256.

    The GUI and packaging tests run first unless -SkipTests is given; a build
    that would ship a broken payload contract fails here instead of on a
    user's machine.

.PARAMETER Clean
    Delete the PyInstaller work directory and any previous LAMF.exe first.

.PARAMETER SkipTests
    Skip runtime\tests\installer_gui_test.py before building.

.PARAMETER Python
    Explicit interpreter to build with (default: py -3, then python3/python).

.PARAMETER BuildVenv
    Location of the build virtual environment (default: build\.pyinstaller-venv).

.PARAMETER OutputDir
    Where LAMF.exe is written (default: dist).

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\Build-LAMF-Exe.ps1 -Clean
#>
[CmdletBinding()]
param(
    [switch] $Clean,
    [switch] $SkipTests,
    [string] $Python,
    [string] $BuildVenv,
    [string] $OutputDir
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$InstallerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root         = Split-Path -Parent $InstallerDir
$SpecFile     = Join-Path $InstallerDir 'LAMF.spec'
$WorkDir      = Join-Path $Root 'build'
if (-not $BuildVenv) { $BuildVenv = Join-Path $WorkDir '.pyinstaller-venv' }
if (-not $OutputDir) { $OutputDir = Join-Path $Root 'dist' }
$ExePath      = Join-Path $OutputDir 'LAMF.exe'
$OptimizationVersion = '1.0.0'
$OptimizationName = "LAMF-Optimizations-$OptimizationVersion.zip"
$OptimizationSha256 = 'f9ef9b1f199b7d995c9f2ab27da0214e865b680e64afadc66093057f55fcdebd'
$VendorDir = Join-Path $Root 'vendor'
$OptimizationArchive = Join-Path $VendorDir $OptimizationName

function Write-Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "    [OK]   $text" -ForegroundColor Green }
function Write-Info($text) { Write-Host "    [..]   $text" }
function Fail($text) { Write-Host ""; Write-Host "    [FAIL] $text" -ForegroundColor Red; exit 1 }

# --------------------------------------------------------------------------
# 1. Find a build interpreter (3.10+). PyInstaller freezes THIS interpreter,
#    so its version is the version LAMF.exe carries.
# --------------------------------------------------------------------------
function Resolve-BuildPython {
    param([string] $Explicit)

    $candidates = @()
    if ($Explicit) {
        $candidates += , @($Explicit, @())
    } else {
        if (Get-Command py      -ErrorAction SilentlyContinue) { $candidates += , @('py', @('-3')) }
        if (Get-Command python3 -ErrorAction SilentlyContinue) { $candidates += , @('python3', @()) }
        if (Get-Command python  -ErrorAction SilentlyContinue) { $candidates += , @('python', @()) }
    }
    foreach ($candidate in $candidates) {
        $exe = $candidate[0]; $prefix = $candidate[1]
        try {
            $probe = & $exe @prefix -c "import sys;print('%d.%d' % sys.version_info[:2]);print(sys.executable)" 2>$null
        } catch { continue }
        if ($LASTEXITCODE -ne 0 -or -not $probe) { continue }
        $lines = @($probe | Where-Object { $_ -and $_.Trim() })
        if ($lines.Count -lt 2) { continue }
        $parts = $lines[0].Trim().Split('.')
        $major = [int]$parts[0]; $minor = [int]$parts[1]
        if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 10)) {
            return [pscustomobject]@{ Path = $lines[1].Trim(); Version = "$major.$minor" }
        }
    }
    return $null
}

Write-Step "Locating a build interpreter (Python 3.10+)"
$buildPython = Resolve-BuildPython -Explicit $Python
if (-not $buildPython) {
    Fail "No Python 3.10+ found. Install one with: winget install -e --id Python.Python.3.12"
}
Write-Ok "Python $($buildPython.Version) at $($buildPython.Path)"

# Tk must exist in the build interpreter or the frozen GUI cannot start.
& $buildPython.Path -c "import tkinter" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Fail "This Python has no tkinter. Reinstall it with the 'tcl/tk and IDLE' option enabled."
}
Write-Ok "tkinter is available"

# Bundle the separately released optimization pack so a clean-machine install
# does not depend on a second download. The pinned release digest is verified
# before PyInstaller is allowed to consume it.
Write-Step "Preparing pinned LAMF optimization pack"
New-Item -ItemType Directory -Force $VendorDir | Out-Null
if (-not (Test-Path $OptimizationArchive) -or
    (Get-FileHash $OptimizationArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $OptimizationSha256) {
    $optimizationUrl = "https://github.com/AI-LUCI/LAMF-Optimizations/releases/download/v$OptimizationVersion/$OptimizationName"
    Write-Info "downloading $optimizationUrl"
    Invoke-WebRequest -Uri $optimizationUrl -OutFile $OptimizationArchive
}
$optimizationHash = (Get-FileHash $OptimizationArchive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($optimizationHash -ne $OptimizationSha256) {
    Fail "optimization pack checksum mismatch (got $optimizationHash)"
}
Write-Ok "$OptimizationName verified"

# --------------------------------------------------------------------------
# 2. Optional clean
# --------------------------------------------------------------------------
if ($Clean) {
    Write-Step "Cleaning previous build output"
    foreach ($path in @((Join-Path $WorkDir 'LAMF'), $ExePath)) {
        if (Test-Path $path) { Remove-Item $path -Recurse -Force; Write-Info "removed $path" }
    }
    Write-Ok "Clean"
}

# --------------------------------------------------------------------------
# 3. Tests (payload contract + GUI logic)
# --------------------------------------------------------------------------
if (-not $SkipTests) {
    Write-Step "Running installer GUI and packaging tests"
    $guiTest = Join-Path $Root 'runtime\tests\installer_gui_test.py'
    if (Test-Path $guiTest) {
        & $buildPython.Path $guiTest
        if ($LASTEXITCODE -ne 0) { Fail "installer_gui_test.py failed; not building." }
        Write-Ok "installer_gui_test.py passed"
    } else {
        Write-Info "installer_gui_test.py not present; skipping"
    }
    $scopeTest = Join-Path $Root 'runtime\tests\installer_scope_test.py'
    if (Test-Path $scopeTest) {
        & $buildPython.Path $scopeTest
        if ($LASTEXITCODE -ne 0) { Fail "installer_scope_test.py failed; not building." }
        Write-Ok "installer_scope_test.py passed"
    }
} else {
    Write-Info "-SkipTests given; tests were not run"
}

# --------------------------------------------------------------------------
# 4. Isolated build venv with PyInstaller
# --------------------------------------------------------------------------
Write-Step "Preparing the build environment"
New-Item -ItemType Directory -Force $WorkDir | Out-Null
$venvPython = Join-Path $BuildVenv 'Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Info "creating $BuildVenv"
    & $buildPython.Path -m venv $BuildVenv
    if ($LASTEXITCODE -ne 0) { Fail "could not create the build virtual environment at $BuildVenv" }
}
Write-Ok "Build venv: $BuildVenv"

& $venvPython -m pip install --disable-pip-version-check --quiet --upgrade pip
& $venvPython -m pip install --disable-pip-version-check --quiet "pyinstaller>=6.0"
if ($LASTEXITCODE -ne 0) {
    Fail "pip could not install PyInstaller (usually a network problem). Retry, or install it manually into $BuildVenv."
}
$pyiVersion = (& $venvPython -c "import PyInstaller;print(PyInstaller.__version__)").Trim()
Write-Ok "PyInstaller $pyiVersion"

# --------------------------------------------------------------------------
# 5. Build
# --------------------------------------------------------------------------
Write-Step "Building LAMF.exe (one file, no console)"
if (-not (Test-Path $SpecFile)) { Fail "spec file not found: $SpecFile" }
# Only build-time options are passed: when a .spec file is given, PyInstaller
# rejects/ignores makespec options (--specpath, --name, --onefile, ...). The
# spec derives its own paths from SPECPATH, which PyInstaller sets for us.
& $venvPython -m PyInstaller --noconfirm --clean `
    --distpath $OutputDir --workpath $WorkDir $SpecFile
if ($LASTEXITCODE -ne 0) { Fail "PyInstaller build failed (see the output above)." }
if (-not (Test-Path $ExePath)) { Fail "PyInstaller reported success but $ExePath is missing." }

# --------------------------------------------------------------------------
# 6. Report + smoke check
# --------------------------------------------------------------------------
Write-Step "Result"
$item = Get-Item $ExePath
$hash = (Get-FileHash $ExePath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Ok "$ExePath"
Write-Info ("size   : {0:N2} MB" -f ($item.Length / 1MB))
Write-Info "sha256 : $hash"
Write-Info "built  : $($item.LastWriteTime)"

# A windowed EXE writes nothing to the console, so verify the subsystem flag
# instead: PE optional-header subsystem 2 == GUI, 3 == console.
$stream = [System.IO.File]::OpenRead($ExePath)
try {
    $reader = New-Object System.IO.BinaryReader($stream)
    $stream.Position = 0x3C
    $peOffset = $reader.ReadInt32()
    $stream.Position = $peOffset + 0x5C   # optional header + 0x44 (Subsystem)
    $subsystem = $reader.ReadUInt16()
} finally {
    $stream.Dispose()
}
if ($subsystem -eq 2) {
    Write-Ok "PE subsystem is WINDOWS_GUI - no console window will appear"
} else {
    Fail "PE subsystem is $subsystem (expected 2 = GUI). The EXE would show a console."
}

Write-Host ""
Write-Host "  Done. Double-click $ExePath to install LAMF." -ForegroundColor Green
Write-Host "  The build venv can be deleted at any time: $BuildVenv"
Write-Host ""
exit 0
