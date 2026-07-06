# check_bands.ps1 - состояние трёх бендов одним экраном.
# Запуск: powershell -ExecutionPolicy Bypass -File C:\SENSE_TECH\check_bands.ps1
$ErrorActionPreference = 'SilentlyContinue'
$now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

'=== ридеры (heartbeat + последняя строка лога) ==='
foreach ($n in 1,2,3) {
    $hb = "C:\SENSE_TECH\logs\neiry_heartbeat_$n.txt"
    $age = '-'
    if (Test-Path $hb) { try { $age = $now - [long]((Get-Content $hb -Raw).Trim()) } catch {} }
    $last = if (Test-Path "C:\SENSE_TECH\_reader_$n.log") { Get-Content "C:\SENSE_TECH\_reader_$n.log" -Tail 1 } else { '(нет лога)' }
    "band $n | hb ${age}s | $last"
}

'=== python-процессы ридеров ==='
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*neiry_band_*' -or $_.CommandLine -like '*neiry_lan_node*' } |
  ForEach-Object { 'pid {0}  {1}' -f $_.ProcessId, ($_.CommandLine -replace '.*\\','') }

'=== Bluetooth (Windows PnP) ==='
Get-PnpDevice -Class Bluetooth |
  Where-Object { $_.FriendlyName -like '*Headband*' -or $_.InstanceId -match 'F7140EFE9D20|C60D7C1844AA|EF21DE1CA367' } |
  ForEach-Object {
    $c = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName '{83DA6326-97A6-4088-9453-A1923F573B29} 15').Data
    '{0}  connected={1}  {2}' -f $_.FriendlyName, $c, $_.InstanceId
  }
