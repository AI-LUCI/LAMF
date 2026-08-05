param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "dist")
)

$ErrorActionPreference = "Stop"
$bundleRoot = $PSScriptRoot
$manifest = Join-Path $bundleRoot "manifest.json"

Get-Content -Raw -LiteralPath $manifest | ConvertFrom-Json | Out-Null
& node --check (Join-Path $bundleRoot "server\index.js")
& node (Join-Path $bundleRoot "tests\test-wrapper.js")

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
Push-Location $bundleRoot
try {
    & npx --yes @anthropic-ai/mcpb pack . (Join-Path $OutputDirectory "lamf.mcpb")
    if ($LASTEXITCODE -ne 0) { throw "mcpb pack failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}

Get-Item -LiteralPath (Join-Path $OutputDirectory "lamf.mcpb")
