# SteamCMD is obtained directly from Valve at setup time, never distributed with this project.
# The official bootstrap executable downloads updates from Valve on its first run.
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$destination = Join-Path $root 'tools/steamcmd'
$binary = Join-Path $destination 'steamcmd.exe'
$downloadUrl = 'https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip'

if (Test-Path -LiteralPath $binary -PathType Leaf) {
    if ((Get-Item -LiteralPath $binary).Length -le 0) {
        throw "The existing SteamCMD executable is empty: $binary. Remove it and rerun setup."
    }
    Write-Host "SteamCMD is already installed: $binary"
    exit 0
}

$tempFolder = Join-Path ([IO.Path]::GetTempPath()) ('steamcmd-install-' + [guid]::NewGuid().ToString('N'))
$tempZip = Join-Path $tempFolder 'steamcmd.zip'
$extracted = Join-Path $tempFolder 'extracted'

New-Item -ItemType Directory -Path $tempFolder -Force | Out-Null
try {
    Write-Host "Downloading SteamCMD directly from Valve:"
    Write-Host "  $downloadUrl"
    Invoke-WebRequest -Uri $downloadUrl -OutFile $tempZip -UseBasicParsing -ErrorAction Stop

    if (-not (Test-Path -LiteralPath $tempZip -PathType Leaf) -or (Get-Item -LiteralPath $tempZip).Length -le 0) {
        throw 'Valve SteamCMD download was empty or missing.'
    }

    # Extract in temporary storage, then install only Valve's bootstrap executable.
    Expand-Archive -LiteralPath $tempZip -DestinationPath $extracted -Force -ErrorAction Stop
    $executable = Join-Path $extracted 'steamcmd.exe'
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        throw 'SteamCMD executable was not found in the downloaded Valve archive.'
    }

    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    Copy-Item -LiteralPath $executable -Destination $binary -ErrorAction Stop
    if (-not (Test-Path -LiteralPath $binary -PathType Leaf) -or (Get-Item -LiteralPath $binary).Length -le 0) {
        throw 'SteamCMD installation failed: executable missing or empty.'
    }

    Write-Host "SteamCMD installed at: $binary" -ForegroundColor Green
    Write-Host 'SteamCMD will self-update from Valve when the updater first runs.'
} finally {
    Remove-Item -LiteralPath $tempFolder -Recurse -Force -ErrorAction SilentlyContinue
}
