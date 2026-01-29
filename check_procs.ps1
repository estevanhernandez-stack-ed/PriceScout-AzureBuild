# Check processes on port 8000
$pids = @(6784, 39156, 30656)
foreach ($p in $pids) {
    $proc = Get-WmiObject Win32_Process -Filter "ProcessId=$p" -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "PID: $p"
        Write-Host "  Parent PID: $($proc.ParentProcessId)"
        Write-Host "  Name: $($proc.Name)"
        Write-Host "  Command: $($proc.CommandLine)"
        Write-Host ""
    }
}
