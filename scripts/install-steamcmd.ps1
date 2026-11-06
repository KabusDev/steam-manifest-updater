# Downloads the official SteamCMD ZIP. Run only after reviewing Valve's licensing and requirements.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$destination = Join-Path $root 'tools/steamcmd'
$binary = Join-Path $destination 'steamcmd.exe'
if (Test-Path $binary) {
    Write-Host "SteamCMD already exists at: $binary"
    exit 0
}
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$tempZip = Join-Path $env:TEMP ('steamcmd-' + [guid]::NewGuid().ToString('N') + '.zip')
try {
    Write-Host 'Downloading SteamCMD directly from Valve...'
    Invoke-WebRequest -Uri 'https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip' -OutFile $tempZip -UseBasicParsing
    Expand-Archive -Path $tempZip -DestinationPath $destination -Force
    if (-not (Test-Path $binary)) { throw 'SteamCMD executable not found after extraction.' }
    Write-Host "Installed SteamCMD to $binary" -ForegroundColor Green
} finally {
    Remove-Item -Path $tempZip -ErrorAction SilentlyContinue
}
