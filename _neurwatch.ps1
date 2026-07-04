# _neurwatch.ps1 - Efir neuro-reader watchdog (scheduled task NEURWATCH, every 2 min).
# Healthy = python process alive AND heartbeat fresh (<60s). Otherwise self-heal:
#   - python hung (stale heartbeat) -> kill it; the launcher loop respawns it.
#   - launcher gone               -> schtasks /run NEIRYSTART.
# Heartbeat file is written ~1/s by neiry_lan_node.py (even while searching for a band),
# so a stale heartbeat means the python really froze, not just "no band".
$ErrorActionPreference = 'SilentlyContinue'
$HB   = 'C:\SENSE_TECH\logs\neiry_heartbeat.txt'
$LOG  = 'C:\SENSE_TECH\logs\watchdog.log'
$TASK = 'NEIRYSTART'

if (-not (Test-Path 'C:\SENSE_TECH\logs')) { New-Item -ItemType Directory -Force 'C:\SENSE_TECH\logs' | Out-Null }

function Note($m){
    $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m)
    try { $line | Out-File -Append -Encoding utf8 $LOG } catch {}
}

$py = @(Get-Process python -ErrorAction SilentlyContinue)

# heartbeat freshness
$fresh = $false
if (Test-Path $HB) {
    try {
        $ts  = [long]((Get-Content $HB -Raw).Trim())
        $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()   # locale-independent (no -UFormat %s / [double]::Parse)
        if ($ts -gt 0 -and ($now - $ts) -lt 60) { $fresh = $true }
    } catch {}
}

# healthy -> stay silent (no log spam)
if ($py.Count -gt 0 -and $fresh) { exit 0 }

# python alive but hung -> kill; launcher loop respawns
if ($py.Count -gt 0 -and -not $fresh) {
    Note 'heartbeat stale > 60s -> reader hung, killing python (launcher will respawn)'
    Stop-Process -Name python -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# launcher (cmd loop) alive?
$launcher = @(Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" -ErrorAction SilentlyContinue |
             Where-Object { $_.CommandLine -like '*START_NEIRY_LAN*' })

if ($launcher.Count -eq 0) {
    Note 'launcher not running -> schtasks /run NEIRYSTART'
    schtasks /run /tn $TASK | Out-Null
} else {
    Note 'launcher alive -> it will respawn python within a few seconds'
}
exit 0
