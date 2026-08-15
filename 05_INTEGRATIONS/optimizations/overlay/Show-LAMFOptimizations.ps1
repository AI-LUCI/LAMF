$controller = Join-Path $PSScriptRoot 'LamfOptimizationControls.exe'
if (-not (Test-Path -LiteralPath $controller)) {
    throw "LAMF optimization controller is not built: $controller"
}
Start-Process -FilePath $controller
