# unpair_bands.ps1 - force-remove the three Headbands from Windows Bluetooth.
# The usual reason they "won't delete": the watchdog respawns the readers,
# the reader reconnects, and the device reappears. So we STOP everything first,
# then remove, then you decide when to start readers again.
# Run AS ADMINISTRATOR:
#   powershell -ExecutionPolicy Bypass -File C:\SENSE_TECH\unpair_bands.ps1
# NOTE: keep this file ASCII-only - PowerShell 5.1 reads BOM-less .ps1 as ANSI.
$ErrorActionPreference = 'SilentlyContinue'
$MACS = 'F7140EFE9D20|C60D7C1844AA|EF21DE1CA367'

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { 'ERROR: run as Administrator.'; exit 1 }

'=== 1) disabling watchdog so it does not respawn readers mid-removal ==='
schtasks /end /tn NEURWATCH 2>$null | Out-Null
schtasks /change /tn NEURWATCH /disable 2>$null | Out-Null
foreach ($n in 1,2,3) { schtasks /end /tn "NEIRYSTART$n" 2>$null | Out-Null }

'=== 2) killing readers and launchers ==='
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*neiry_*' } |
  ForEach-Object { "kill python $($_.ProcessId)"; Stop-Process -Id $_.ProcessId -Force }
Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
  Where-Object { $_.CommandLine -like '*START_NEIRY*' } |
  ForEach-Object { "kill launcher $($_.ProcessId)"; Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 2

'=== 3) removing Headband devices (pnputil) ==='
$devs = Get-PnpDevice | Where-Object { $_.FriendlyName -like '*Headband*' -or $_.InstanceId -match $MACS }
if (-not $devs) { 'none found via PnP' }
foreach ($d in $devs) {
    "remove: $($d.FriendlyName)  $($d.InstanceId)"
    pnputil /remove-device "$($d.InstanceId)" 2>&1 | ForEach-Object { "  $_" }
}

'=== 4) restarting Bluetooth stack to drop stuck handles ==='
Restart-Service bthserv -Force
Start-Sleep -Seconds 2

'=== 5) removing paired entries from the Bluetooth registry ==='
# HKLM\SYSTEM\...\BTHPORT\Parameters\Devices\<mac> - the actual pairing store.
# Needs SYSTEM rights; if Remove-Item is denied, use the psexec line printed below.
$root = 'HKLM:\SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices'
Get-ChildItem $root -ErrorAction SilentlyContinue |
  Where-Object { $_.PSChildName -match '(?i)f7140efe9d20|c60d7c1844aa|ef21de1ca367' } |
  ForEach-Object {
    "registry pairing: $($_.PSChildName)"
    Remove-Item $_.PsPath -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $_.PsPath) { "  DENIED - run: psexec -s -i regedit  (then delete $($_.PSChildName) under BTHPORT\Parameters\Devices)" }
    else { "  removed" }
  }

'=== 6) audit: any Headband left? ==='
$left = Get-PnpDevice | Where-Object { $_.FriendlyName -like '*Headband*' -or $_.InstanceId -match $MACS }
if ($left) { $left | ForEach-Object { "STILL PRESENT: $($_.FriendlyName)  status=$($_.Status)  $($_.InstanceId)" } }
else { 'clean - no Headband devices remain' }

''
'NOTE: readers are stopped and NEURWATCH is DISABLED now.'
'When done, re-enable autostart:  schtasks /change /tn NEURWATCH /enable'
'  then start readers:  schtasks /run /tn NEIRYSTART1  (and 2,3)  or reboot.'
'The reader connects WITHOUT pairing - bands should NOT be paired in Windows.'
