# Force kill all processes on port 8000
Write-Host "Finding processes on port 8000..."
$output = netstat -ano | Select-String ":8000.*LISTENING"
$pids = $output | ForEach-Object {
    $parts = $_.Line -split '\s+'
    $parts[-1]
} | Where-Object { $_ -match '^\d+$' } | Sort-Object -Unique

if ($pids.Count -eq 0) {
    Write-Host "No processes found on port 8000"
} else {
    foreach ($procId in $pids) {
        Write-Host "Force killing PID $procId..."
        taskkill /F /PID $procId 2>&1 | Out-Host
    }
}

# Wait a moment
Start-Sleep -Seconds 2

# Verify
$checkOutput = netstat -ano | Select-String ":8000.*LISTENING"
if ($checkOutput) {
    Write-Host "WARNING: Some processes still running on port 8000:"
    Write-Host $checkOutput
} else {
    Write-Host "Port 8000 is now free"
}
