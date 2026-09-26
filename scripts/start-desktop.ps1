param(
    [string]$InstallRoot = (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)))
)

$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath($InstallRoot)
$appRoot = Join-Path $root 'App\KodKon Studio'
$backendRoot = Join-Path $appRoot 'backend'
$frontendRoot = Join-Path $appRoot 'frontend'
$dataRoot = if ($env:KODKON_DATA_DIR) { $env:KODKON_DATA_DIR } else { Join-Path $root 'Data' }
$logsRoot = Join-Path $dataRoot 'logs'
$startupLog = Join-Path $logsRoot 'startup.log'
$mutex = $null
$ownsMutex = $false

function Write-StartupLog([string]$Message) {
    Add-Content -LiteralPath $startupLog -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message" -Encoding utf8
}

function Show-StartupError([string]$Message) {
    try {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($Message, 'KodKon Studio', 'OK', 'Error') | Out-Null
    } catch { }
}

try {
    New-Item -ItemType Directory -Path $logsRoot -Force | Out-Null
    $mutex = [System.Threading.Mutex]::new($false, 'Local\KodKonStudioLauncher')
    try { $ownsMutex = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $ownsMutex = $true }
    if (-not $ownsMutex) { exit 0 }

    $env:KODKON_DATA_DIR = $dataRoot
    $env:KODKON_INSTALL_ROOT = $root

    $runtimeKeys = @(
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
        'HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
        'HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    )
    $webViewInstalled = $false
    foreach ($key in $runtimeKeys) {
        if (Test-Path -LiteralPath $key) {
            $version = (Get-ItemProperty -LiteralPath $key -Name pv -ErrorAction SilentlyContinue).pv
            if ($version -and $version -ne '0.0.0.0') { $webViewInstalled = $true; break }
        }
    }
    if (-not $webViewInstalled) {
        Add-Type -AssemblyName System.Windows.Forms
        $runtimeMessage = 'Microsoft Edge WebView2 Runtime is required to open the desktop app. Select Yes to open the download page, install it, and then start the app again.'
        $choice = [System.Windows.Forms.MessageBox]::Show($runtimeMessage, 'Additional component required', 'YesNo', 'Information')
        if ($choice -eq 'Yes') { Start-Process 'https://developer.microsoft.com/microsoft-edge/webview2/' }
        exit 1
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw 'Python 3.11 or newer was not found. Install Python and try again.' }
    $pythonVersion = (& $pythonCommand.Source --version 2>&1 | Out-String).Trim()
    if ($pythonVersion -notmatch 'Python\s+(\d+)\.(\d+)' -or ([int]$Matches[1] -lt 3 -or ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -lt 11))) {
        throw 'Python 3.11 or newer is required. Install a current Python release and try again.'
    }
    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
        throw 'FFmpeg/FFprobe were not found in PATH. Install FFmpeg and try again.'
    }

    $venvRoot = Join-Path $backendRoot '.venv'
    $venvPython = Join-Path $venvRoot 'Scripts\python.exe'
    $venvPythonW = Join-Path $venvRoot 'Scripts\pythonw.exe'
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-StartupLog 'Creating Python environment.'
        & $pythonCommand.Source -m venv $venvRoot *>> $startupLog
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment. See startup.log.' }
    }

    $requirements = Join-Path $backendRoot 'requirements.txt'
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $requirementsHash = [System.Convert]::ToBase64String($hasher.ComputeHash([System.IO.File]::ReadAllBytes($requirements)))
    } finally { $hasher.Dispose() }
    $stamp = Join-Path $venvRoot '.requirements.sha256'
    $installedHash = if (Test-Path -LiteralPath $stamp) { (Get-Content -LiteralPath $stamp -Raw).Trim() } else { '' }
    if ($installedHash -ne $requirementsHash) {
        Write-StartupLog 'Installing application dependencies.'
        & $venvPython -m pip install --disable-pip-version-check -r $requirements *>> $startupLog
        if ($LASTEXITCODE -ne 0) { throw 'Could not install application dependencies. See startup.log.' }
        Set-Content -LiteralPath $stamp -Value $requirementsHash -Encoding ascii
    }

    $frontendDist = Join-Path $frontendRoot 'dist\index.html'
    $portableMarker = Join-Path $frontendRoot '.portable-build'
    $needsBuild = -not (Test-Path -LiteralPath $frontendDist)
    if ((Test-Path -LiteralPath $portableMarker) -and (Test-Path -LiteralPath $frontendDist)) { $needsBuild = $false }
    if ($needsBuild) {
        if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm -ErrorAction SilentlyContinue)) {
            throw 'Node.js and npm are required to build the app interface.'
        }
        Push-Location $frontendRoot
        try {
            if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules'))) {
                npm ci *>> $startupLog
                if ($LASTEXITCODE -ne 0) { throw 'Could not install interface dependencies. See startup.log.' }
            }
            npm run build *>> $startupLog
            if ($LASTEXITCODE -ne 0) { throw 'Could not build the app interface. See startup.log.' }
        } finally { Pop-Location }
    }

    if (-not (Test-Path -LiteralPath $venvPythonW)) { throw 'Could not find pythonw.exe in the application environment.' }
    Write-StartupLog 'Starting native desktop window.'
    $desktopProcess = Start-Process -FilePath $venvPythonW -ArgumentList @('-m', 'app.desktop') -WorkingDirectory $backendRoot -PassThru -Wait
    if ($desktopProcess.ExitCode -ne 0) { Write-StartupLog "Desktop process exited with code $($desktopProcess.ExitCode)." }
} catch {
    Write-StartupLog ("ERROR: " + $_.Exception.Message)
    Show-StartupError ($_.Exception.Message + "`n`nDetails: $startupLog")
} finally {
    if ($ownsMutex -and $mutex) { try { $mutex.ReleaseMutex() } catch { } }
    if ($mutex) { $mutex.Dispose() }
}
