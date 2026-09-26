$ErrorActionPreference = 'Stop'

$appRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $appRoot 'backend'
$frontendRoot = Join-Path $appRoot 'frontend'
$venvPython = Join-Path $backendRoot '.venv\Scripts\python.exe'
$frontendDist = Join-Path $frontendRoot 'dist\index.html'
$portableBuildMarker = Join-Path $frontendRoot '.portable-build'
$needsFrontendBuild = -not (Test-Path -LiteralPath $frontendDist)
if (Test-Path -LiteralPath $portableBuildMarker) { $needsFrontendBuild = $false }
if (-not $needsFrontendBuild -and (Test-Path -LiteralPath (Join-Path $frontendRoot 'src'))) {
    $buildTime = (Get-Item -LiteralPath $frontendDist).LastWriteTimeUtc
    $latestSource = Get-ChildItem -LiteralPath (Join-Path $frontendRoot 'src') -Recurse -File | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    if ($latestSource -and $latestSource.LastWriteTimeUtc -gt $buildTime) { $needsFrontendBuild = $true }
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'ไม่พบ Python 3.11 ขึ้นไป กรุณาติดตั้ง Python แล้วเปิด PowerShell ใหม่'
}
if ($needsFrontendBuild -and -not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw 'ไม่พบ Node.js 22.12 ขึ้นไปสำหรับ build หน้าจอ กรุณาติดตั้ง Node.js แล้วเปิด PowerShell ใหม่'
}
if ($needsFrontendBuild -and -not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw 'ไม่พบ npm สำหรับ build หน้าจอ กรุณาติดตั้ง Node.js แล้วเปิด PowerShell ใหม่'
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    throw 'ไม่พบ FFmpeg/FFprobe ใน PATH กรุณาติดตั้ง FFmpeg แล้วเปิด PowerShell ใหม่'
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host 'กำลังเตรียม Python environment ครั้งแรก...'
    & python -m venv (Join-Path $backendRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'สร้าง Python environment ไม่สำเร็จ' }
}

Write-Host 'กำลังตรวจ Python packages...'
& $venvPython -m pip install -r (Join-Path $backendRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'ติดตั้ง Python packages ไม่สำเร็จ' }

if ($needsFrontendBuild) {
    Push-Location $frontendRoot
    try {
        if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules'))) {
            Write-Host 'กำลังติดตั้งหน้าจอ...'
            & npm ci
            if ($LASTEXITCODE -ne 0) { throw 'ติดตั้งหน้าจอไม่สำเร็จ' }
        }
        Write-Host 'กำลัง build หน้าจอ...'
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw 'build หน้าจอไม่สำเร็จ' }
    }
    finally {
        Pop-Location
    }
}

Write-Host 'กำลังเปิด กดก่อนคิดทีหลัง Studio ที่ http://127.0.0.1:8765'
Start-Process 'http://127.0.0.1:8765'
Push-Location $backendRoot
try {
    & $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8765
    if ($LASTEXITCODE -ne 0) { throw 'โปรแกรมหยุดทำงาน ตรวจข้อความด้านบนเพื่อดูสาเหตุ' }
}
finally {
    Pop-Location
}
