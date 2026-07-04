#!/usr/bin/env python3
"""EFIR node band reader -> JSON lines on stdout (transported to head over SSH).

Backends:
  --synthetic   no hardware/SDK; emits a slow random-walk of the canonical metrics
                (stdlib only). Use to validate node->SSH->head->TD pipe end-to-end.
  (default)     real Neiry band via NeuroSDK2 + EmotionalMath (Anastasia path:
                T3-O1 / T4-O2 bipolar, calibration, mental+spectral).

Contract: one compact JSON object per line on stdout, flushed immediately.
Metric fields match Anastasia's confirmed TCP:9000 payload EXACTLY (so her
generation patch consumes them unchanged) -- mental 0..100, spectral 0..1:
  {"id":1,"t":1719,"ok":1,"calib":100,
   "rel_attention":16.1,"rel_relaxation":0.0,"inst_attention":39.1,"inst_relaxation":60.8,
   "alpha_data":0.343,"beta_data":0.429,"theta_data":0.226}
Diagnostics go to stderr only (so stdout stays a clean JSON stream for the head).

VERIFIED 2026-06-27 (session 821cad33): the Neiry MindTracker IS found by NeuroSDK2
as LEHeadband, calibration completes, real mental+spectral data flows to TD.
The earlier "crashes after 2 min" was only a hardcoded sleep(120) in the original
script -- this node runs continuously (reconnect loop).
"""
from __future__ import annotations
import argparse, json, sys, time

MENTAL = ("rel_attention", "rel_relaxation", "inst_attention", "inst_relaxation")
SPECTRAL = ("alpha_data", "beta_data", "theta_data")


def emit(d: dict) -> None:
    sys.stdout.write(json.dumps(d, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def log(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


def now_ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


# --------------------------------------------------------------------------- #
# Synthetic backend (stdlib only) -- proves the whole pipe without hardware    #
# --------------------------------------------------------------------------- #
def run_synthetic(node_id: int, rate_hz: float) -> None:
    import random
    rnd = random.Random(1000 + node_id)            # per-node deterministic seed
    t0 = time.monotonic()
    period = 1.0 / max(rate_hz, 0.1)
    att = relax = 50.0                              # mental 0..100
    a = b = th = 0.33                               # spectral 0..1
    log(f"[node {node_id}] SYNTHETIC backend, {rate_hz} Hz")
    while True:
        att = min(100.0, max(0.0, att + (50 - att) * 0.05 + rnd.uniform(-6, 6)))
        relax = min(100.0, max(0.0, relax + (50 - relax) * 0.05 + rnd.uniform(-6, 6)))
        a = min(1.0, max(0.0, a + rnd.uniform(-0.03, 0.03)))
        b = min(1.0, max(0.0, b + rnd.uniform(-0.03, 0.03)))
        th = min(1.0, max(0.0, th + rnd.uniform(-0.03, 0.03)))
        emit({
            "id": node_id, "t": now_ms(t0), "ok": 1, "calib": 100,
            "rel_attention": round(att, 2),
            "rel_relaxation": round(relax, 2),
            "inst_attention": round(min(100.0, max(0.0, att + rnd.uniform(-5, 5))), 2),
            "inst_relaxation": round(min(100.0, max(0.0, relax + rnd.uniform(-5, 5))), 2),
            "alpha_data": round(a, 4), "beta_data": round(b, 4), "theta_data": round(th, 4),
        })
        time.sleep(period)


# --------------------------------------------------------------------------- #
# Real backend (NeuroSDK2 + EmotionalMath) -- Anastasia path (verified live)    #
# --------------------------------------------------------------------------- #
def run_real(node_id: int, calib_seconds: int, scan_seconds: int) -> None:
    from neurosdk.scanner import Scanner
    from neurosdk.cmn_types import SensorFamily, SensorCommand
    from em_st_artifacts.utils import lib_settings, support_classes
    from em_st_artifacts import emotional_math

    t0 = time.monotonic()
    state = {"math": None, "calib_done": False}

    def on_signal(sensor, data):
        m = state["math"]
        if m is None:
            return
        raw = [support_classes.RawChannels(s.T3 - s.O1, s.T4 - s.O2) for s in data]
        m.push_data(raw)
        m.process_data_arr()
        if not m.calibration_finished():
            emit({"id": node_id, "t": now_ms(t0), "ok": 1,
                  "calib": int(m.get_calibration_percents())})
            return
        if not state["calib_done"]:
            state["calib_done"] = True
            log(f"[node {node_id}] calibration finished")
        out = {"id": node_id, "t": now_ms(t0), "ok": 1, "calib": 100}
        md = m.read_mental_data_arr()
        if md:
            out["rel_attention"] = round(md[0].rel_attention, 3)
            out["rel_relaxation"] = round(md[0].rel_relaxation, 3)
            out["inst_attention"] = round(md[0].inst_attention, 3)
            out["inst_relaxation"] = round(md[0].inst_relaxation, 3)
        sd = m.read_spectral_data_percents_arr()
        if sd:
            out["alpha_data"] = round(sd[0].alpha, 4)
            out["beta_data"] = round(sd[0].beta, 4)
            out["theta_data"] = round(sd[0].theta, 4)
        if len(out) > 4:
            emit(out)

    while True:  # reconnect loop -- show runs unattended
        try:
            log(f"[node {node_id}] scanning {scan_seconds}s for LEHeadband...")
            scanner = Scanner([SensorFamily.LEHeadband])
            scanner.start(); time.sleep(scan_seconds); scanner.stop()
            infos = scanner.sensors()
            if not infos:
                emit({"id": node_id, "t": now_ms(t0), "ok": 0, "msg": "no_device"})
                time.sleep(2); continue
            sensor = scanner.create_sensor(infos[0])
            log(f"[node {node_id}] connected: {infos[0]}")
            sensor.signalDataReceived = on_signal

            mls = lib_settings.MathLibSetting(
                sampling_rate=250, process_win_freq=25, n_first_sec_skipped=4,
                fft_window=1000, bipolar_mode=True, squared_spectrum=True,
                channels_number=4, channel_for_analysis=0)
            ads = lib_settings.ArtifactDetectSetting(
                art_bord=110, allowed_percent_artpoints=70, raw_betap_limit=800_000,
                global_artwin_sec=4, num_wins_for_quality_avg=125,
                hamming_win_spectrum=True, hanning_win_spectrum=False,
                total_pow_border=400_000_000, spect_art_by_totalp=True)
            sads = lib_settings.ShortArtifactDetectSetting(
                ampl_art_detect_win_size=200, ampl_art_zerod_area=200,
                ampl_art_extremum_border=25)
            mss = lib_settings.MentalAndSpectralSetting(
                n_sec_for_averaging=2, n_sec_for_instant_estimation=4)
            m = emotional_math.EmotionalMath(mls, ads, sads, mss)
            m.set_calibration_length(calib_seconds)
            m.set_mental_estimation_mode(False)
            m.set_skip_wins_after_artifact(10)
            m.set_zero_spect_waves(True, 0, 1, 1, 1, 0)
            m.set_spect_normalization_by_bands_width(True)
            state["math"] = m; state["calib_done"] = False

            if sensor.is_supported_command(SensorCommand.StartSignal):
                m.start_calibration()
                sensor.exec_command(SensorCommand.StartSignal)
                log(f"[node {node_id}] streaming (calib {calib_seconds}s)...")
                while True:                # stream until disconnect/error (NO sleep-and-exit)
                    time.sleep(1.0)
        except Exception as e:
            emit({"id": node_id, "t": now_ms(t0), "ok": 0, "msg": str(e)[:80]})
            log(f"[node {node_id}] error: {e} -> retry in 3s")
            time.sleep(3)


def main() -> None:
    ap = argparse.ArgumentParser(description="EFIR node band reader -> JSON stdout")
    ap.add_argument("--id", type=int, required=True, help="node/band id (1..3)")
    ap.add_argument("--synthetic", action="store_true", help="no hardware; fake metrics")
    ap.add_argument("--rate", type=float, default=10.0, help="synthetic emit Hz")
    ap.add_argument("--calib", type=int, default=20, help="calibration seconds (real)")
    ap.add_argument("--scan", type=int, default=15, help="scan seconds (real)")
    args = ap.parse_args()
    try:
        if args.synthetic:
            run_synthetic(args.id, args.rate)
        else:
            run_real(args.id, args.calib, args.scan)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
