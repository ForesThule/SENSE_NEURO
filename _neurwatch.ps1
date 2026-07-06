# _neurwatch.ps1 - Efir neuro-reader watchdog (scheduled task NEURWATCH, every 2 min).
# Supports BOTH deployments:
#   - multi-band (one PC, 3 bands): tasks NEIRYSTART1..3, scripts neiry_band_N.py,
#     heartbeats logs\neiry_heartbeat_N.txt
#   - legacy single-band: task NEIRYSTART, script neiry_lan_node.py,
#     heartbeat logs\neiry_heartbeat.txt
# An instance is watched only if its scheduled task exists on this machine.
# Healthy = reader python alive AND heartbeat fresh (<60s). Otherwise self-heal:
#   - reader hung (stale heartbeat) -> kill THAT reader; its launcher loop respawns.
#   - launcher gone                 -> schtasks /run its NEIRYSTART* task.
$ErrorActionPreference = 'SilentlyContinue'
$BASE = 'C:\SENSE_TECH'
$LOG  = "$BASE\logs\watchdog.log"

if (-not (Test-Path "$BASE\logs")) { New-Item -ItemType Directory -Force "$BASE\logs" | Out-Null }

function Note($m){
    $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m)
    try { $line | Out-File -Append -Encoding utf8 $LOG } catch {}
}

function TaskExists($t){
    schtasks /query /tn $t 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function HeartbeatFresh($hb){
    if (-not (Test-Path $hb)) { return $false }
    try {
        $ts  = [long]((Get-Content $hb -Raw).Trim())
        $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        return ($ts -gt 0 -and ($now - $ts) -lt 60)
    } catch { return $false }
}

function WatchInstance($name, $script, $hb, $launcherMark, $task){
    # only OUR reader processes — other pythons on the box must not mask/suffer
    $py = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
           Where-Object { $_.CommandLine -like "*$script*" })
    $fresh = HeartbeatFresh $hb

    if ($py.Count -gt 0 -and $fresh) { return }   # healthy -> stay silent

    if ($py.Count -gt 0 -and -not $fresh) {
        Note "$name : heartbeat stale > 60s -> reader hung, killing it (launcher will respawn)"
        $py | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 2
    }

    $launcher = @(Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" -ErrorAction SilentlyContinue |
                 Where-Object { $_.CommandLine -like "*$launcherMark*" })
    if ($launcher.Count -eq 0) {
        Note "$name : launcher not running -> schtasks /run $task"
        schtasks /run /tn $task | Out-Null
    } else {
        Note "$name : launcher alive -> it will respawn python within a few seconds"
    }
}

# multi-band instances (watched only where their tasks are registered)
foreach ($n in 1,2,3) {
    if (TaskExists "NEIRYSTART$n") {
        WatchInstance "band$n" "neiry_band_$n.py" "$BASE\logs\neiry_heartbeat_$n.txt" "START_NEIRY_BAND_$n" "NEIRYSTART$n"
    }
}

# legacy single-band
if (TaskExists 'NEIRYSTART') {
    WatchInstance 'single' 'neiry_lan_node.py' "$BASE\logs\neiry_heartbeat.txt" 'START_NEIRY_LAN' 'NEIRYSTART'
}
exit 0
