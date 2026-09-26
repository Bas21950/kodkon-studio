$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$appRoot = Join-Path $root 'App\KodKon Studio'
$dataRoot = Join-Path $root 'Data'
$env:KODKON_DATA_DIR = $dataRoot
$env:KODKON_INSTALL_ROOT = $root
& (Join-Path $appRoot 'scripts\start-desktop.ps1') -InstallRoot $root
