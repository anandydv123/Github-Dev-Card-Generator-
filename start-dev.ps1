$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

function Test-HttpOk($Url) {
    try {
        Invoke-RestMethod -Uri $Url -TimeoutSec 3 | Out-Null
        return $true
    } catch {
        return $false
    }
}

if (-not (Test-HttpOk "http://127.0.0.1:8080/health")) {
    Start-Process `
        -FilePath "python" `
        -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8080" `
        -WorkingDirectory $Backend `
        -WindowStyle Hidden | Out-Null
}

if (-not (Test-HttpOk "http://127.0.0.1:3000/index.html")) {
    Start-Process `
        -FilePath "python" `
        -ArgumentList "-m", "http.server", "3000", "--bind", "127.0.0.1" `
        -WorkingDirectory $Frontend `
        -WindowStyle Hidden | Out-Null
}

Start-Sleep -Seconds 2

Write-Host "Frontend: http://127.0.0.1:3000"
Write-Host "Backend:  http://127.0.0.1:8080"
