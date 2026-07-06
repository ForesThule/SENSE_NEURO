# check_bands.ps1 - one-screen status of all three bands.
# Run: powershell -ExecutionPolicy Bypass -File C:\SENSE_TECH\check_bands.ps1
# NOTE: keep this file ASCII-only — PowerShell 5.1 reads BOM-less .ps1 as ANSI.
$ErrorActionPreference = 'SilentlyContinue'
$now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

'=== readers (heartbeat age + last log line) ==='
foreach ($n in 1,2,3) {
    $hb = "C:\SENSE_TECH\logs\neiry_heartbeat_$n.txt"
    $age = '-'
    if (Test-Path $hb) { try { $age = $now - [long]((Get-Content $hb -Raw).Trim()) } catch {} }
    $last = if (Test-Path "C:\SENSE_TECH\_reader_$n.log") { Get-Content "C:\SENSE_TECH\_reader_$n.log" -Tail 1 } else { '(no log)' }
    "band $n | hb ${age}s | $last"
}

'=== reader python processes ==='
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*neiry_band_*' -or $_.CommandLine -like '*neiry_lan_node*' } |
  ForEach-Object { 'pid {0}  {1}' -f $_.ProcessId, ($_.CommandLine -replace '.*\\','') }

'=== Bluetooth (Windows PnP view) ==='
Get-PnpDevice -Class Bluetooth |
  Where-Object { $_.FriendlyName -like '*Headband*' -or $_.InstanceId -match 'F7140EFE9D20|C60D7C1844AA|EF21DE1CA367' } |
  ForEach-Object {
    $c = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName '{83DA6326-97A6-4088-9453-A1923F573B29} 15').Data
    '{0}  connected={1}  {2}' -f $_.FriendlyName, $c, $_.InstanceId
  }
