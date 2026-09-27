# Diagnose & clean pgserver postgres instances (no bash-quoting pitfalls).
Get-CimInstance Win32_Process -Filter "Name='postgres.exe'" | ForEach-Object {
    $cl = $_.CommandLine
    if ($null -eq $cl) { $cl = "<no cmdline>" }
    Write-Output ("PID " + $_.ProcessId + " : " + $cl.Substring(0, [Math]::Min(160, $cl.Length)))
}
Get-Process postgres -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.Id -Force
    Write-Output ("killed " + $_.Id)
}
