<#
  LAMF installer — Windows entry point.

  Thin wrapper: finds Python and hands off to install.py, which does all
  the real work (and explains itself as it goes).

  If Windows refuses to run this script ("running scripts is disabled on
  this system"), right-click it -> "Run with PowerShell" once, or run this
  exact line in PowerShell — it bypasses the policy for this script only:

      powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-LAMF.ps1
#>

$ErrorActionPreference = 'Stop'
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-Python {
  # Prefer the pylauncher (py -3), then python3, then python.
  if (Get-Command py -ErrorAction SilentlyContinue)       { return @('py', @('-3')) }
  if (Get-Command python3 -ErrorAction SilentlyContinue)  { return @('python3', @()) }
  if (Get-Command python -ErrorAction SilentlyContinue)   { return @('python', @()) }
  return $null
}

$found = Find-Python
if (-not $found) {
  Write-Host ""
  Write-Host "  LAMF needs Python 3.10 or newer, and we couldn't find it."
  Write-Host "  Install it with this one line (in PowerShell):"
  Write-Host "    winget install -e --id Python.Python.3.12"
  Write-Host ""
  Write-Host "  Then run this installer again."
  exit 1
}

$exe = $found[0]
$prefix = $found[1]
& $exe @prefix (Join-Path $Dir 'install.py') @args
exit $LASTEXITCODE
