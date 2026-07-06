# setup_autostart.ps1 - make ONLY the three band readers auto-start on this PC.
# Removes every legacy NEIRY autostart (old NEIRYSTART task, startup shortcuts,
# registry Run entries), registers NEIRYSTART1..3 + NEURWATCH, starts them,
# then prints an audit of what is left.
# Run AS ADMINISTRATOR:
#   powershell -ExecutionPolicy Bypass -File C:\SENSE_TECH\setup_autostart.ps1
# NOTE: keep this file ASCII-only - PowerShell 5.1 reads BOM-less .ps1 as ANSI.
$ErrorActionPreference = 'SilentlyContinue'
$BASE = 'C:\SENSE_TECH'

'=== 1) stopping running readers/launchers ==='
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*neiry_*' } |
  ForEach-Object { "kill python pid $($_.ProcessId)"; Stop-Process -Id $_.ProcessId -Force }
Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
  Where-Object { $_.CommandLine -like '*START_NEIRY*' } |
  ForEach-Object { "kill launcher pid $($_.ProcessId)"; Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 2

'=== 2) removing legacy autostart entries ==='
# legacy single-band task (multi-band PCs must not have it)
schtasks /delete /tn NEIRYSTART /f 2>$null | Out-Null
'removed task NEIRYSTART (if existed)'

# startup-folder shortcuts (per-user and all-users)
$startupDirs = @("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup",
                 "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Startup")
foreach ($d in $startupDirs) {
    Get-ChildItem $d -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -match 'NEIRY|SENSE' } |
      ForEach-Object { "removing startup shortcut: $($_.FullName)"; Remove-Item $_.FullName -Force }
}

# registry Run entries
foreach ($key in 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run',
                 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run') {
    $props = Get-ItemProperty $key -ErrorAction SilentlyContinue
    if ($props) {
        $props.PSObject.Properties |
          Where-Object { $_.Name -notmatch '^PS' -and ("$($_.Value)" -match 'NEIRY|SENSE_TECH' -or $_.Name -match 'NEIRY|SENSE') } |
          ForEach-Object { "removing Run entry: $key -> $($_.Name)"; Remove-ItemProperty -Path $key -Name $_.Name -Force }
    }
}

'=== 3) registering OUR tasks (the only allowed autostart) ==='
schtasks /create /tn NEIRYSTART1 /sc onlogon /tr "$BASE\START_NEIRY_BAND_1.bat" /f | Out-Null
schtasks /create /tn NEIRYSTART2 /sc onlogon /tr "$BASE\START_NEIRY_BAND_2.bat" /f | Out-Null
schtasks /create /tn NEIRYSTART3 /sc onlogon /tr "$BASE\START_NEIRY_BAND_3.bat" /f | Out-Null
schtasks /create /tn NEURWATCH /sc minute /mo 2 /tr "wscript.exe $BASE\watchdog_hidden.vbs" /f | Out-Null
'registered: NEIRYSTART1, NEIRYSTART2, NEIRYSTART3, NEURWATCH'

'=== 4) starting readers now ==='
foreach ($n in 1,2,3) { schtasks /run /tn "NEIRYSTART$n" | Out-Null }
'started NEIRYSTART1..3'

'=== 5) audit: NEIRY-related scheduled tasks ==='
Get-ScheduledTask | Where-Object { $_.TaskName -match 'NEIRY|NEURWATCH' } |
  ForEach-Object { '{0}  [{1}]' -f $_.TaskName, $_.State }

'=== 5) audit: startup folders ==='
foreach ($d in $startupDirs) {
    Get-ChildItem $d -ErrorAction SilentlyContinue | ForEach-Object { "$d -> $($_.Name)" }
}

'=== 5) audit: registry Run entries ==='
foreach ($key in 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run',
                 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run') {
    $props = Get-ItemProperty $key -ErrorAction SilentlyContinue
    if ($props) {
        $props.PSObject.Properties |
          Where-Object { $_.Name -notmatch '^PS' } |
          ForEach-Object { "$key -> $($_.Name) = $($_.Value)" }
    }
}
'=== done: only NEIRYSTART1..3 + NEURWATCH should autostart now ==='
