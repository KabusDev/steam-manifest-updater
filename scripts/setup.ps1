# First-time setup: no administrator rights required for a current-user task.
[CmdletBinding()]
param(
    [ValidatePattern('^([01][0-9]|2[0-3]):[0-5][0-9]$')]
    [string]$Time = '03:00',
    [switch]$NoSchedule,
    [switch]$InstallSteamCMD
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'This guided setup currently supports Windows only.' }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

# Locate a working Python 3.10+ rather than assuming the Microsoft Store alias works.
$python = $null
foreach ($candidate in @(@{ Command='py'; Prefix='-3' }, @{ Command='python'; Prefix='' })) {
    $cmd = Get-Command $candidate.Command -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    try {
        $version = if ($candidate.Prefix) { & $cmd.Source $candidate.Prefix --version 2>&1 } else { & $cmd.Source --version 2>&1 }
        if ($LASTEXITCODE -eq 0 -and $version -match 'Python 3\.(1[0-9]|[2-9][0-9])\.') {
            $python = @{ Command = $cmd.Source; Prefix = $candidate.Prefix }
            break
        }
    } catch { }
}
if (-not $python) {
    Write-Host 'Python 3.10 or later is required. Install it from https://www.python.org/downloads/windows/' -ForegroundColor Yellow
    throw 'Python not detected. Install Python, then rerun this script.'
}
Write-Host "Using $($python.Command) $($python.Prefix)"
$pythonArgs = @()
if ($python.Prefix) { $pythonArgs += $python.Prefix }
& $python.Command @pythonArgs -m steam_manifest_updater init
if ($LASTEXITCODE -ne 0) { throw 'Failed to create config.json' }

if ($InstallSteamCMD) {
    & (Join-Path $PSScriptRoot 'install-steamcmd.ps1')
}
& $python.Command @pythonArgs -m steam_manifest_updater discover
if ($LASTEXITCODE -ne 0) { throw 'Steam discovery failed.' }

if (-not $NoSchedule) {
    $taskName = 'Steam Manifest Auto-Updater'
    $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    $arguments = if ($python.Prefix) { "$($python.Prefix) -m steam_manifest_updater run" } else { '-m steam_manifest_updater run' }
    $action = New-ScheduledTaskAction -Execute $python.Command -Argument $arguments -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -Daily -At $Time
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 10) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Write-Host "Scheduled '$taskName' every day at $Time (only while this Windows user is logged in)." -ForegroundColor Green
}
Write-Host ''
Write-Host 'NEXT: Edit config.json and enable only supported SteamCMD jobs.' -ForegroundColor Yellow
Write-Host 'TEST: py -3 -m steam_manifest_updater run --dry-run'
Write-Host 'Docs: README.md and docs/CONFIGURATION.md'
