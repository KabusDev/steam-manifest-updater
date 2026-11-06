$ErrorActionPreference = 'Stop'
$taskName = 'Steam Manifest Auto-Updater'
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Removed scheduled task: $taskName" -ForegroundColor Green
} else {
    Write-Host 'No scheduled task was found.'
}
Write-Host 'Your configuration, files and logs have not been deleted.'
