$ErrorActionPreference = 'Stop'
$url = $env:KODKON_DOWNLOAD_URL
$destination = $env:KODKON_DOWNLOAD_PATH
if (-not $url -or -not $destination) { throw 'Missing update download parameters' }
$uri = [uri]$url
if ($uri.Scheme -ne 'https' -or $uri.Host -ne 'github.com' -or $uri.AbsolutePath -notmatch '^/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/releases/download/') {
    throw 'Untrusted update URL'
}
$tempRoot = [System.IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
$resolved = [System.IO.Path]::GetFullPath($destination)
if (-not $resolved.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
    -not ([System.IO.Path]::GetFileName($resolved)).StartsWith('kodkon-update-') -or
    [System.IO.Path]::GetExtension($resolved) -ne '.zip') {
    throw 'Unsafe update download path'
}
Invoke-WebRequest -Uri $url -OutFile $resolved -UseBasicParsing -TimeoutSec 1200 -MaximumRedirection 5
