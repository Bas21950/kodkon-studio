param(
    [Parameter(Mandatory = $true)][string]$ArchivePath,
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [Parameter(Mandatory = $true)][int]$ProcessId,
    [Parameter(Mandatory = $true)][string]$Version
)

$ErrorActionPreference = 'Stop'
$install = [System.IO.Path]::GetFullPath($InstallRoot)
$project = [System.IO.Path]::GetFullPath((Join-Path $install 'App\KodKon Studio'))
$archive = [System.IO.Path]::GetFullPath($ArchivePath)
$tempRoot = [System.IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
$work = Join-Path $env:TEMP ('kodkon-update-' + [guid]::NewGuid().ToString('N'))
$stage = Join-Path $work 'stage'
$backup = Join-Path $work 'backup'
$approvedRoots = @('App\KodKon Studio\backend\app\', 'App\KodKon Studio\backend\alembic\', 'App\KodKon Studio\frontend\dist\', 'App\KodKon Studio\frontend\public\', 'App\KodKon Studio\frontend\src\', 'App\KodKon Studio\scripts\', 'App\KodKon Studio\docs\')
$approvedFiles = @('App\KodKon Studio\README.md', 'App\KodKon Studio\backend\alembic.ini', 'App\KodKon Studio\backend\pyproject.toml', 'App\KodKon Studio\backend\requirements.txt', 'App\KodKon Studio\frontend\index.html', 'App\KodKon Studio\frontend\package.json', 'App\KodKon Studio\frontend\package-lock.json', 'App\KodKon Studio\frontend\tsconfig.app.json', 'App\KodKon Studio\frontend\tsconfig.json', 'App\KodKon Studio\frontend\tsconfig.node.json', 'App\KodKon Studio\frontend\vite.config.ts', 'Start Studio.bat', 'Start Studio.vbs', 'Start Studio.ps1', 'README.txt')
$copiedPaths = [System.Collections.Generic.List[string]]::new()
$originalPaths = [System.Collections.Generic.List[string]]::new()
$newPaths = [System.Collections.Generic.List[string]]::new()
$serverStopped = $false

function Show-UpdateError([string]$Message) {
    try {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($Message, 'อัปเดต กดก่อนคิดทีหลัง Studio ไม่สำเร็จ', 'OK', 'Error') | Out-Null
    } catch { }
}

function Remove-OwnedTempDirectory([string]$Path) {
    $resolved = [System.IO.Path]::GetFullPath($Path)
    $leaf = Split-Path -Leaf $resolved
    if (-not $resolved.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -or -not $leaf.StartsWith('kodkon-update-', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'ปฏิเสธการลบโฟลเดอร์ชั่วคราวที่อยู่นอกขอบเขต'
    }
    if (Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved -Recurse -Force }
}

try {
    if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) { throw 'ไม่พบไฟล์อัปเดตที่ดาวน์โหลดมา' }
    if (-not (Test-Path -LiteralPath (Join-Path $install 'Start Studio.vbs') -PathType Leaf)) { throw 'ไม่พบ Start Studio.vbs ในโฟลเดอร์ติดตั้ง' }
    if (-not (Test-Path -LiteralPath $project -PathType Container)) { throw 'ไม่พบโฟลเดอร์โปรแกรมในตำแหน่งติดตั้ง' }
    New-Item -ItemType Directory -Path $stage -Force | Out-Null
    New-Item -ItemType Directory -Path $backup -Force | Out-Null

    # Allow only the files produced by package.py. This keeps the installer from
    # writing into Data, backups, .git, or arbitrary paths listed in a bad ZIP.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $manifestEntry = $zip.GetEntry('package-manifest.json')
        if (-not $manifestEntry) { throw 'แพ็กเกจไม่มี package-manifest.json' }
        $reader = [System.IO.StreamReader]::new($manifestEntry.Open())
        try { $manifest = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
        if ($manifest.version -ne $Version) { throw 'เวอร์ชันในแพ็กเกจไม่ตรงกับ Release ที่ตรวจสอบไว้' }
        if ($manifest.secrets_included -ne $false -or $manifest.data_included -ne $false) { throw 'แพ็กเกจระบุว่ามีข้อมูลส่วนตัวหรือ secret · ยกเลิกการติดตั้ง' }
        if (-not $manifest.includes -or -not ($manifest.includes -contains 'App/KodKon Studio/frontend/dist/index.html')) { throw 'แพ็กเกจไม่มีไฟล์หน้าจอที่ build แล้ว' }

        foreach ($entryPath in $manifest.includes) {
            if (-not ($entryPath -is [string])) { throw 'รายการไฟล์ใน manifest ไม่ถูกต้อง' }
            $relative = $entryPath.Replace('/', '\')
            if ([System.IO.Path]::IsPathRooted($relative) -or $relative.Contains(':') -or ($relative -split '\\' | Where-Object { $_ -in @('', '.', '..') }).Count -gt 0) {
                throw "พบ path ที่ไม่ปลอดภัยในแพ็กเกจ: $entryPath"
            }
            $allowed = $approvedFiles -contains $relative
            if (-not $allowed) { foreach ($root in $approvedRoots) { if ($relative.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) { $allowed = $true; break } } }
            if (-not $allowed) { throw "แพ็กเกจมีไฟล์นอกขอบเขตโปรแกรม: $entryPath" }

            $zipEntry = $zip.GetEntry($entryPath.Replace('\', '/'))
            if (-not $zipEntry -or $zipEntry.FullName.EndsWith('/')) { throw "แพ็กเกจขาดไฟล์: $entryPath" }
            $target = [System.IO.Path]::GetFullPath((Join-Path $stage $relative))
            $stagePrefix = [System.IO.Path]::GetFullPath($stage).TrimEnd('\') + '\'
            if (-not $target.StartsWith($stagePrefix, [System.StringComparison]::OrdinalIgnoreCase)) { throw "path หลุดออกจากโฟลเดอร์เตรียมอัปเดต: $entryPath" }
            New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($zipEntry, $target, $true)
            $copiedPaths.Add($relative)
        }
    } finally { $zip.Dispose() }

    New-Item -ItemType Directory -Path (Join-Path $stage 'App\KodKon Studio\frontend') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $stage 'App\KodKon Studio\frontend\.portable-build') -Value 'Prebuilt frontend included in this portable package.' -Encoding utf8
    $copiedPaths.Add('App\KodKon Studio\frontend\.portable-build')

    # Wait for the API process to exit before replacing files it has loaded.
    Start-Sleep -Seconds 2
    $server = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($server) {
        $serverInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
        $expectedPython = [System.IO.Path]::GetFullPath((Join-Path $project 'backend\.venv\Scripts\pythonw.exe'))
        if ($server.ProcessName -notin @('pythonw', 'python') -or -not $serverInfo -or $serverInfo.CommandLine -notlike "*$expectedPython*") {
            throw 'ยืนยันโปรเซสของโปรแกรมไม่ได้ · ไม่ได้ปิดโปรเซสใด'
        }
        $launcherProcessId = 0
        $ancestorId = [int]$serverInfo.ParentProcessId
        for ($depth = 0; $depth -lt 8 -and $ancestorId -gt 0; $depth++) {
            $ancestor = Get-CimInstance Win32_Process -Filter "ProcessId = $ancestorId" -ErrorAction SilentlyContinue
            if (-not $ancestor) { break }
            if ($ancestor.Name -match '^powershell(\.exe)?$' -and $ancestor.CommandLine -like "*start-desktop.ps1*") {
                $launcherProcessId = [int]$ancestor.ProcessId
                break
            }
            $ancestorId = [int]$ancestor.ParentProcessId
        }
        Stop-Process -Id $ProcessId -Force
        $server.WaitForExit()
        $serverStopped = $true
        if ($launcherProcessId) { Wait-Process -Id $launcherProcessId -Timeout 30 -ErrorAction SilentlyContinue }
    }

    foreach ($relative in $copiedPaths) {
        $source = Join-Path $stage $relative
        $destination = [System.IO.Path]::GetFullPath((Join-Path $install $relative))
        $installPrefix = $install.TrimEnd('\') + '\'
        if (-not $destination.StartsWith($installPrefix, [System.StringComparison]::OrdinalIgnoreCase)) { throw "ไฟล์ปลายทางไม่ปลอดภัย: $relative" }
        if (Test-Path -LiteralPath $destination -PathType Leaf) {
            $backupPath = Join-Path $backup $relative
            New-Item -ItemType Directory -Path (Split-Path -Parent $backupPath) -Force | Out-Null
            Copy-Item -LiteralPath $destination -Destination $backupPath -Force
            $originalPaths.Add($relative)
        } else { $newPaths.Add($relative) }
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }

    if (-not (Test-Path -LiteralPath (Join-Path $project 'frontend\dist\index.html') -PathType Leaf)) { throw 'ตรวจสอบไฟล์หน้าจอหลังอัปเดตไม่ผ่าน' }
    Start-Process -FilePath (Join-Path $install 'Start Studio.vbs') -WorkingDirectory $install
} catch {
    foreach ($relative in $originalPaths) {
        $source = Join-Path $backup $relative
        $destination = Join-Path $install $relative
        if (Test-Path -LiteralPath $source -PathType Leaf) { Copy-Item -LiteralPath $source -Destination $destination -Force }
    }
    foreach ($relative in $newPaths) {
        $destination = Join-Path $install $relative
        if (Test-Path -LiteralPath $destination -PathType Leaf) { Remove-Item -LiteralPath $destination -Force }
    }
    Show-UpdateError $_.Exception.Message
    if ($serverStopped -and (Test-Path -LiteralPath (Join-Path $install 'Start Studio.vbs') -PathType Leaf)) {
        Start-Process -FilePath (Join-Path $install 'Start Studio.vbs') -WorkingDirectory $install
    }
} finally {
    if (Test-Path -LiteralPath $work) { Remove-OwnedTempDirectory $work }
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
}
