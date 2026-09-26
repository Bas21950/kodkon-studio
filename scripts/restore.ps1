param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [string]$DataDir
)

$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $appRoot 'backend\.venv\Scripts\python.exe'
$restoreScript = Join-Path $PSScriptRoot 'restore_data.py'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'ยังไม่มี Python environment ของโปรแกรม กรุณารัน scripts/start.ps1 อย่างน้อยหนึ่งครั้งก่อน'
}
if (-not (Test-Path -LiteralPath $BackupPath -PathType Leaf)) {
    throw 'ไม่พบไฟล์สำรองที่ระบุ'
}

$arguments = @($restoreScript, (Resolve-Path -LiteralPath $BackupPath).Path)
if ($DataDir) { $arguments += @('--data-dir', $DataDir) }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'การกู้คืนข้อมูลไม่สำเร็จ' }
