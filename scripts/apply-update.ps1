param(
    [Parameter(Mandatory = $true)][string]$ArchivePath,
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [Parameter(Mandatory = $true)][int]$ProcessId,
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$StatusPath = ''
)

$ErrorActionPreference = 'Stop'
$install = [System.IO.Path]::GetFullPath($InstallRoot)
$project = [System.IO.Path]::GetFullPath((Join-Path $install 'App\KodKon Studio'))
$archive = [System.IO.Path]::GetFullPath($ArchivePath)
$tempRoot = [System.IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
if (-not $StatusPath) { $StatusPath = Join-Path $env:TEMP ('kodkon-update-status-' + [guid]::NewGuid().ToString('N') + '.json') }
$statusFile = [System.IO.Path]::GetFullPath($StatusPath)
$work = Join-Path $env:TEMP ('kodkon-update-' + [guid]::NewGuid().ToString('N'))
$stage = Join-Path $work 'stage'
$backup = Join-Path $work 'backup'
$approvedRoots = @('App\KodKon Studio\backend\app\', 'App\KodKon Studio\backend\alembic\', 'App\KodKon Studio\frontend\dist\', 'App\KodKon Studio\frontend\public\', 'App\KodKon Studio\frontend\src\', 'App\KodKon Studio\scripts\', 'App\KodKon Studio\docs\')
$approvedFiles = @('App\KodKon Studio\README.md', 'App\KodKon Studio\backend\alembic.ini', 'App\KodKon Studio\backend\pyproject.toml', 'App\KodKon Studio\backend\requirements.txt', 'App\KodKon Studio\frontend\index.html', 'App\KodKon Studio\frontend\package.json', 'App\KodKon Studio\frontend\package-lock.json', 'App\KodKon Studio\frontend\tsconfig.app.json', 'App\KodKon Studio\frontend\tsconfig.json', 'App\KodKon Studio\frontend\tsconfig.node.json', 'App\KodKon Studio\frontend\vite.config.ts', 'Start Studio.bat', 'Start Studio.vbs', 'Start Studio.ps1', 'README.txt')
$copiedPaths = [System.Collections.Generic.List[string]]::new()
$originalPaths = [System.Collections.Generic.List[string]]::new()
$newPaths = [System.Collections.Generic.List[string]]::new()
$serverStopped = $false

function Write-UpdateStatus([string]$Status, [int]$Progress, [string]$Message) {
    $payload = @{
        update_id = [System.IO.Path]::GetFileNameWithoutExtension($statusFile).Replace('kodkon-update-status-', '')
        version = $Version
        status = $Status
        progress = [Math]::Max(0, [Math]::Min(100, $Progress))
        message = $Message
    } | ConvertTo-Json -Compress
    $temporaryStatus = $statusFile + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    $previousStatus = $statusFile + '.' + [guid]::NewGuid().ToString('N') + '.bak'
    try {
        Set-Content -LiteralPath $temporaryStatus -Value $payload -Encoding UTF8
        for ($attempt = 0; $attempt -lt 8; $attempt++) {
            try {
                if ([System.IO.File]::Exists($statusFile)) {
                    [System.IO.File]::Replace($temporaryStatus, $statusFile, $previousStatus)
                } else {
                    [System.IO.File]::Move($temporaryStatus, $statusFile)
                }
                return
            } catch {
                if ($attempt -eq 7) { throw }
                Start-Sleep -Milliseconds (50 * ($attempt + 1))
            }
        }
    } finally {
        if (Test-Path -LiteralPath $temporaryStatus) { Remove-Item -LiteralPath $temporaryStatus -Force }
        if (Test-Path -LiteralPath $previousStatus) { Remove-Item -LiteralPath $previousStatus -Force }
    }
}

function Start-InstalledApp {
    $launcher = Join-Path $install 'Start Studio.vbs'
    $wscript = Join-Path $env:WINDIR 'System32\wscript.exe'
    if (-not (Test-Path -LiteralPath $wscript -PathType Leaf)) { throw 'ไม่พบ Windows Script Host สำหรับเปิดโปรแกรมใหม่' }
    $env:KODKON_UPDATE_STATUS_PATH = $statusFile
    $env:KODKON_UPDATE_TARGET_VERSION = $Version
    Start-Process -FilePath $wscript -ArgumentList @('//B', ('"{0}"' -f $launcher)) -WorkingDirectory $install -WindowStyle Hidden
}

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
    if (-not $statusFile.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -or -not (Split-Path -Leaf $statusFile).StartsWith('kodkon-update-status-', [System.StringComparison]::OrdinalIgnoreCase) -or [System.IO.Path]::GetExtension($statusFile) -ne '.json') { throw 'ตำแหน่งไฟล์สถานะอัปเดตไม่ปลอดภัย' }
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

        $entryCount = @($manifest.includes).Count
        $entryIndex = 0
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
            $entryIndex++
            $extractProgress = 80 + [int](8 * $entryIndex / [Math]::Max(1, $entryCount))
            Write-UpdateStatus 'installing' $extractProgress "เตรียมไฟล์อัปเดต $entryIndex จาก $entryCount"
        }
    } finally { $zip.Dispose() }

    New-Item -ItemType Directory -Path (Join-Path $stage 'App\KodKon Studio\frontend') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $stage 'App\KodKon Studio\frontend\.portable-build') -Value 'Prebuilt frontend included in this portable package.' -Encoding utf8
    $copiedPaths.Add('App\KodKon Studio\frontend\.portable-build')

    Write-UpdateStatus 'installing' 88 'เตรียมไฟล์เสร็จ · กำลังปิดโปรแกรมเดิมอย่างปลอดภัย'
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
        $desktopProcessId = 0
        $ancestorId = [int]$serverInfo.ParentProcessId
        for ($depth = 0; $depth -lt 8 -and $ancestorId -gt 0; $depth++) {
            $ancestor = Get-CimInstance Win32_Process -Filter "ProcessId = $ancestorId" -ErrorAction SilentlyContinue
            if (-not $ancestor) { break }
            if ($ancestor.Name -in @('pythonw.exe', 'python.exe') -and $ancestor.CommandLine -like "*$expectedPython*" -and $ancestor.CommandLine -match '(?i)(?:^|\s)-m\s+app\.desktop(?:\s|$)') {
                $desktopProcessId = [int]$ancestor.ProcessId
            }
            if ($ancestor.Name -match '^powershell(\.exe)?$' -and $ancestor.CommandLine -like "*start-desktop.ps1*") {
                $launcherProcessId = [int]$ancestor.ProcessId
                break
            }
            $ancestorId = [int]$ancestor.ParentProcessId
        }
        Stop-Process -Id $ProcessId -Force
        $server.WaitForExit()
        $serverStopped = $true
        if ($desktopProcessId) {
            $desktopInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $desktopProcessId" -ErrorAction SilentlyContinue
            if ($desktopInfo) {
                if ($desktopInfo.Name -notin @('pythonw.exe', 'python.exe') -or $desktopInfo.CommandLine -notlike "*$expectedPython*" -or $desktopInfo.CommandLine -notmatch '(?i)(?:^|\s)-m\s+app\.desktop(?:\s|$)') {
                    throw 'ยืนยันหน้าต่างโปรแกรมเดิมไม่ได้ · ยังไม่ได้แทนที่ไฟล์'
                }
                Stop-Process -Id $desktopProcessId -Force
                Wait-Process -Id $desktopProcessId -Timeout 10 -ErrorAction SilentlyContinue
                if (Get-Process -Id $desktopProcessId -ErrorAction SilentlyContinue) { throw 'หน้าต่างโปรแกรมเดิมยังปิดไม่สมบูรณ์ · ยังไม่ได้แทนที่ไฟล์' }
            }
        }
        if ($launcherProcessId) {
            Wait-Process -Id $launcherProcessId -Timeout 10 -ErrorAction SilentlyContinue
            $launcherInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $launcherProcessId" -ErrorAction SilentlyContinue
            if ($launcherInfo) {
                if ($launcherInfo.Name -notmatch '^powershell(\.exe)?$' -or $launcherInfo.CommandLine -notlike '*start-desktop.ps1*') {
                    throw 'ยืนยันตัวเปิดโปรแกรมเดิมไม่ได้ · ยังไม่ได้แทนที่ไฟล์'
                }
                Stop-Process -Id $launcherProcessId -Force
                Wait-Process -Id $launcherProcessId -Timeout 10 -ErrorAction SilentlyContinue
                if (Get-Process -Id $launcherProcessId -ErrorAction SilentlyContinue) { throw 'ตัวเปิดโปรแกรมเดิมยังปิดไม่สมบูรณ์ · ยังไม่ได้แทนที่ไฟล์' }
            }
        }
    }

    $copyIndex = 0
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
        $copyIndex++
        $copyProgress = 88 + [int](8 * $copyIndex / [Math]::Max(1, $copiedPaths.Count))
        Write-UpdateStatus 'installing' $copyProgress "ติดตั้งไฟล์ $copyIndex จาก $($copiedPaths.Count)"
    }

    if (-not (Test-Path -LiteralPath (Join-Path $project 'frontend\dist\index.html') -PathType Leaf)) { throw 'ตรวจสอบไฟล์หน้าจอหลังอัปเดตไม่ผ่าน' }
    Write-UpdateStatus 'restarting' 97 'ติดตั้งเสร็จ · กำลังเปิดโปรแกรมเวอร์ชันใหม่'
    Start-Sleep -Milliseconds 800
    Start-InstalledApp
    $ready = $false
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        Start-Sleep -Milliseconds 500
        try {
            $capabilities = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/capabilities' -TimeoutSec 2
            if ($capabilities.version -eq $Version) { $ready = $true; break }
        } catch { }
    }
    if (-not $ready) { throw 'เปิดโปรแกรมเวอร์ชันใหม่ไม่สำเร็จ · ลองเปิดจากไอคอนโปรแกรมอีกครั้ง' }
    Write-UpdateStatus 'completed' 100 'อัปเดตเสร็จแล้ว · โปรแกรมพร้อมใช้งาน'
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
    try { Write-UpdateStatus 'failed' 0 $_.Exception.Message } catch { }
    Show-UpdateError $_.Exception.Message
    if ($serverStopped -and (Test-Path -LiteralPath (Join-Path $install 'Start Studio.vbs') -PathType Leaf)) {
        try { Start-InstalledApp } catch { Show-UpdateError $_.Exception.Message }
    }
} finally {
    if (Test-Path -LiteralPath $work) { Remove-OwnedTempDirectory $work }
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
}
