"""
EFIR distributed NODE sender (slave) — Neiry band -> head TouchDesigner over the network.

Derived from Anastasia's emo_send_data_to_td.py (NeuroSDK2 + EmotionalMath).
ORIGINAL IS NOT MODIFIED — this is a separate copy in EFIR_DIST\.

Each mini-PC runs this with its own --node-id. It connects to its own band,
runs EmotionalMath, and sends 7 metrics + node_id as JSON over TCP to the head.

  # real band, node 1, head over Tailscale:
  python emo_send_node.py --node-id 1
  # explicit head + LAN ip:
  python emo_send_node.py --node-id 2 --head-ip 192.168.50.32
  # no band — fake LFO stream to test the head TD:
  python emo_send_node.py --node-id 3 --synthetic

Head TD: a TCP/IP DAT in SERVER mode per node on port (port_base + node_id):
  node 1 -> 9001,  node 2 -> 9002,  node 3 -> 9003.
JSON keys: rel_attention, rel_relaxation, inst_attention, inst_relaxation,
           alpha_data, beta_data, theta_data, node_id.
"""
import argparse
import socket
import json
import math
import subprocess
import ipaddress
from time import sleep


def parse_args():
    p = argparse.ArgumentParser(
        description="EFIR Neiry node -> head TouchDesigner. Data travels over the LOCAL WiFi LAN; "
                    "the head's LAN IP is auto-discovered via Tailscale (no DHCP reservation needed).")
    p.add_argument('--head-ip', default=None,
                   help='head LAN IP. If omitted, auto-discovered from Tailscale (recommended on mesh WiFi).')
    p.add_argument('--head-name', default='efir-head',
                   help='Tailscale name of the head, used for auto-discovery')
    p.add_argument('--node-id', type=int, required=True, choices=[1, 2, 3],
                   help='1/2/3 — selects port 9000+id and tags the stream')
    p.add_argument('--port-base', type=int, default=9000, help='effective port = port-base + node-id')
    p.add_argument('--calibration', type=int, default=20, help='EmotionalMath calibration seconds')
    p.add_argument('--search', type=int, default=25, help='BLE scan seconds')
    p.add_argument('--synthetic', action='store_true', help='no band: stream plausible LFO metrics')
    return p.parse_args()


args = parse_args()
PORT = args.port_base + args.node_id
NODE = args.node_id


def _is_private(ip):
    try:
        return ipaddress.ip_address(ip).is_private
    except Exception:
        return False


def _my_lan_prefix():
    """First 3 octets of this PC's primary LAN IPv4 (e.g. '192.168.68.')."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('192.168.0.1', 9))          # no packet actually sent; just selects the outgoing iface
        ip = s.getsockname()[0]
        s.close()
        if _is_private(ip):
            return ip.rsplit('.', 1)[0] + '.'
    except Exception:
        pass
    return None


def discover_head_ip():
    """Read the head's CURRENT LAN IP from Tailscale (it tracks each peer's LAN endpoints).
    DATA still goes straight over the LAN to that IP — Tailscale is only the address book,
    so we get LAN speed AND survive DHCP changes without reservations."""
    prefix = _my_lan_prefix()
    try:
        out = subprocess.check_output(['tailscale', 'status', '--json'], text=True, timeout=5)
        data = json.loads(out)
        for peer in (data.get('Peer') or {}).values():
            name = (str(peer.get('DNSName', '')) + ' ' + str(peer.get('HostName', ''))).lower()
            if args.head_name.lower() not in name:
                continue
            cands = []
            cur = peer.get('CurAddr') or ''
            if cur:
                cands.append(cur.rsplit(':', 1)[0])
            for a in (peer.get('Addrs') or []):
                cands.append(a.rsplit(':', 1)[0])
            priv = [c for c in cands if _is_private(c)]
            same = [c for c in priv if prefix and c.startswith(prefix)]   # prefer this node's own subnet
            if same:
                return same[0]
            if priv:
                return priv[0]
    except Exception as e:
        print('[discover] tailscale lookup failed:', e)
    return None


# Resolve the head IP once at startup: explicit --head-ip wins, else Tailscale auto-discovery.
HEAD_IP = args.head_ip
if not HEAD_IP:
    print(f"[discover] resolving '{args.head_name}' LAN IP via Tailscale...")
    while HEAD_IP is None:
        HEAD_IP = discover_head_ip()
        if HEAD_IP is None:
            print("[discover] head not found yet (same WiFi? Tailscale up on both?) — retry in 3s")
            sleep(3)
print(f"[head] {args.head_name} -> {HEAD_IP}:{PORT}")

_fail_streak = 0


def send_to_touchdesigner(data):
    """One TCP packet of JSON to the head over the LAN. Resilient; re-discovers IP on DHCP drift."""
    global HEAD_IP, _fail_streak
    payload = dict(data or {})
    payload['node_id'] = NODE
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)                       # don't block the callback if head is down
            s.connect((HEAD_IP, PORT))
            s.sendall(json.dumps(payload).encode('utf-8'))
        _fail_streak = 0
    except (ConnectionRefusedError, OSError, socket.timeout):
        _fail_streak += 1
        if _fail_streak >= 20 and not args.head_ip:   # IP likely drifted -> ask Tailscale again
            new = discover_head_ip()
            if new and new != HEAD_IP:
                print(f"[head] LAN IP changed {HEAD_IP} -> {new}")
                HEAD_IP = new
            _fail_streak = 0


# ---------------------------------------------------------------------------
# synthetic mode — no hardware, for rehearsing the head TD without 3 bands
# ---------------------------------------------------------------------------
if args.synthetic:
    print(f"[synthetic] node {NODE} -> {HEAD_IP}:{PORT}   (Ctrl+C to stop)")
    t = 0.0
    try:
        while True:
            ph = NODE * 1.7                          # phase offset so 3 nodes differ
            send_to_touchdesigner({
                'rel_attention':   50 + 45 * math.sin(t * 0.7 + ph),
                'rel_relaxation':  50 + 45 * math.sin(t * 0.5 + ph + 1),
                'inst_attention':  50 + 40 * math.sin(t * 1.3 + ph),
                'inst_relaxation': 50 + 40 * math.sin(t * 0.9 + ph + 2),
                'alpha_data': 0.3 + 0.2 * math.sin(t * 0.4 + ph),
                'beta_data':  0.3 + 0.2 * math.sin(t * 1.1 + ph),
                'theta_data': 0.3 + 0.2 * math.sin(t * 0.6 + ph),
            })
            t += 0.1
            sleep(0.1)
    except KeyboardInterrupt:
        print("stopped")
    raise SystemExit(0)


# ---------------------------------------------------------------------------
# real band — NeuroSDK2 + EmotionalMath (Anastasia's logic, transport changed)
# ---------------------------------------------------------------------------
from neurosdk.scanner import Scanner
from em_st_artifacts.utils import lib_settings, support_classes
from em_st_artifacts import emotional_math
from neurosdk.cmn_types import *

math_lib = None


def sensor_found(scanner, sensors):
    for s in sensors:
        print('Sensor found:', s)


def on_sensor_state_changed(sensor, state):
    print('Sensor {0} is {1}'.format(sensor.name, state))


def on_battery_changed(sensor, battery):
    print('Battery:', battery)


def on_signal_received(sensor, data):
    raw = []
    for sample in data:
        raw.append(support_classes.RawChannels(sample.T3 - sample.O1, sample.T4 - sample.O2))
    math_lib.push_data(raw)
    math_lib.process_data_arr()
    if not math_lib.calibration_finished():
        print("Calibration:", math_lib.get_calibration_percents())
        return
    out = {}
    md = math_lib.read_mental_data_arr()
    if md:
        out['rel_attention'] = md[0].rel_attention
        out['rel_relaxation'] = md[0].rel_relaxation
        out['inst_attention'] = md[0].inst_attention
        out['inst_relaxation'] = md[0].inst_relaxation
    sd = math_lib.read_spectral_data_percents_arr()
    if sd:
        out['alpha_data'] = sd[0].alpha
        out['beta_data'] = sd[0].beta
        out['theta_data'] = sd[0].theta
    send_to_touchdesigner(out)


def on_resist_received(sensor, data):
    for ch, v in (('O1', data.O1), ('O2', data.O2), ('T3', data.T3), ('T4', data.T4)):
        print(f"{ch} resist {'OK' if v < 2_000_000 else 'HIGH'}: {v}")


try:
    scanner = Scanner([SensorFamily.LEHeadband])
    scanner.sensorsChanged = sensor_found
    scanner.start()
    print(f"Searching {args.search}s...")
    sleep(args.search)
    scanner.stop()

    infos = scanner.sensors()
    if not infos:
        print("No band found — check Bluetooth/pairing.")
        raise SystemExit(1)

    sensor = scanner.create_sensor(infos[0])
    print("Connected:", infos[0])
    sensor.sensorStateChanged = on_sensor_state_changed
    sensor.batteryChanged = on_battery_changed
    sensor.signalDataReceived = on_signal_received
    sensor.resistDataReceived = on_resist_received

    sensor.exec_command(SensorCommand.StartResist)
    print("Resist check (20s)...")
    sleep(20)
    sensor.exec_command(SensorCommand.StopResist)

    mls = lib_settings.MathLibSetting(sampling_rate=250, process_win_freq=25, n_first_sec_skipped=4,
                                      fft_window=1000, bipolar_mode=True, squared_spectrum=True,
                                      channels_number=4, channel_for_analysis=0)
    ads = lib_settings.ArtifactDetectSetting(art_bord=110, allowed_percent_artpoints=70, raw_betap_limit=800_000,
                                             global_artwin_sec=4, num_wins_for_quality_avg=125,
                                             hamming_win_spectrum=True, hanning_win_spectrum=False,
                                             total_pow_border=400_000_000, spect_art_by_totalp=True)
    sads = lib_settings.ShortArtifactDetectSetting(ampl_art_detect_win_size=200, ampl_art_zerod_area=200,
                                                   ampl_art_extremum_border=25)
    mss = lib_settings.MentalAndSpectralSetting(n_sec_for_averaging=2, n_sec_for_instant_estimation=4)

    math_lib = emotional_math.EmotionalMath(mls, ads, sads, mss)
    math_lib.set_calibration_length(args.calibration)
    math_lib.set_mental_estimation_mode(False)
    math_lib.set_skip_wins_after_artifact(10)
    math_lib.set_zero_spect_waves(True, 0, 1, 1, 1, 0)
    math_lib.set_spect_normalization_by_bands_width(True)

    if sensor.is_supported_command(SensorCommand.StartSignal):
        sensor.exec_command(SensorCommand.StartSignal)
        print("Signal start")
        math_lib.start_calibration()
        print(f"Streaming node {NODE} -> {HEAD_IP}:{PORT}   (Ctrl+C to stop)")
        try:
            while True:          # run continuously for the show; callbacks fire on the SDK thread
                sleep(1)
        except KeyboardInterrupt:
            print("stopping...")
        sensor.exec_command(SensorCommand.StopSignal)

    sensor.disconnect()
    del sensor
    del math_lib
    del scanner
except Exception as err:
    print("ERROR:", err)
