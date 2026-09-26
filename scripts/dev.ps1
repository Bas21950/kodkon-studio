$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $appRoot 'backend'
$frontendRoot = Join-Path $appRoot 'frontend'

if (-not (Test-Path -LiteralPath (Join-Path $backendRoot '.venv\Scripts\python.exe'))) {
    throw 'ยังไม่มี backend environment กรุณารัน scripts/start.ps1 ครั้งแรกก่อน'
}

$apiJob = Start-Process -FilePath (Join-Path $backendRoot '.venv\Scripts\python.exe') `
    -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8765') `
    -WorkingDirectory $backendRoot -PassThru -WindowStyle Hidden

Push-Location $frontendRoot
try {
    Write-Host 'Frontend: http://127.0.0.1:5173 | API: http://127.0.0.1:8765'
    Write-Host 'กด Ctrl+C เพื่อปิด frontend; ปิดหน้าต่างนี้แล้ว API เบื้องหลังอาจยังทำงานอยู่'
    & npm run dev
}
finally {
    Pop-Location
    if ($apiJob -and -not $apiJob.HasExited) {
        Stop-Process -Id $apiJob.Id -Force -ErrorAction SilentlyContinue
    }
}
