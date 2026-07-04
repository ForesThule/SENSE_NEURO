# -*- coding: utf-8 -*-
# =====================================================================
#  Neiry -> головной TouchDesigner (Эфир) : ридер v2 БЕЗ ОЖИДАНИЯ КАЛИБРОВКИ
#
#  Идея: посетитель надел подключённый бэнд -> метрики идут на головной
#  СРАЗУ (adaptive-прокси из сырого спектра), а em_st-калибровка идёт
#  ФОНОМ и по завершении ПЛАВНО вплетается (crossfade) как персональный
#  коэффициент. Ноль ожидания. Если em_st застрял (движение) — прокси несёт всё.
#
#  Контракт головного НЕ меняется: TCP JSON -> порт 9000, те же ключи:
#    rel_attention rel_relaxation inst_attention inst_relaxation
#    alpha_data beta_data theta_data
#
#  numpy на мини-ПК НЕТ -> компактный чистый-Python FFT (radix-2).
#
#  env (launcher .bat): NEIRY_HEAD, NEIRY_PORT(9000), NEIRY_ADDR(опц.)
# =====================================================================

import os, time, json, socket, math as _m
from collections import deque
import numpy as np

from neurosdk.scanner import Scanner
from neurosdk.cmn_types import *
from em_st_artifacts.utils import lib_settings, support_classes
from em_st_artifacts import emotional_math

HOST = os.environ.get('NEIRY_HEAD', '192.168.1.34')
PORT = int(os.environ.get('NEIRY_PORT', 9000))
TARGET = os.environ.get('NEIRY_ADDR', '').strip().lower()

FS = 250                 # частота дискретизации бэнда
WIN = 512                # окно FFT (~2.05 с) — степень двойки
STEP_SEC = 0.25          # как часто пересчитываем прокси
BLEND_SEC = 8.0          # длительность плавного вплетения em_st после калибровки
BASE_TAU = 25.0          # постоянная времени адаптивного baseline (сек) — «индивид. коэффициент»
SMOOTH_TAU = 0.6         # сглаживание выходной метрики (сек)

# ---- состояние ----
math = None
connected = False
_sock = {'s': None}
_sent = 0
_last_beat = 0.0

# буферы сырья (два биполяра)
_bufL = deque(maxlen=WIN)
_bufR = deque(maxlen=WIN)
_last_proc = 0.0

# adaptive baseline (EMA mean + EMA abs-dev) на прокси
_base = {'att_m': None, 'att_d': None, 'rel_m': None, 'rel_d': None}
# сглаженный выход
_out = {'att': None, 'rel': None}
# фаза em_st
_calib_done = False
_blend = 0.0             # 0 = чистый прокси, 1 = чистый em_st
_blend_t0 = None


def log(msg):
    print(time.strftime('[%H:%M:%S] ') + msg, flush=True)


# -------------------- сеть --------------------
def _get_sock():
    s = _sock['s']
    if s is not None:
        return s
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect((HOST, PORT))
        _sock['s'] = s
        log('соединение с головным %s:%d установлено' % (HOST, PORT))
        return s
    except Exception:
        _sock['s'] = None
        return None


def send_to_td(data):
    s = _get_sock()
    if s is None:
        return False
    try:
        s.sendall((json.dumps(data) + '\n').encode('utf-8'))
        return True
    except Exception:
        try: s.close()
        except Exception: pass
        _sock['s'] = None
        return False


# -------------------- спектр: numpy + метод Уэлча --------------------
_SEG = 256                          # длина сегмента Уэлча (~1.02 с)
_HOP = 128                          # 50% перекрытие
_HANN = np.hanning(_SEG)
_FREQ = np.fft.rfftfreq(_SEG, 1.0 / FS)
_TH = (_FREQ >= 4.0) & (_FREQ < 7.0)     # theta
_AL = (_FREQ >= 8.0) & (_FREQ < 12.0)    # alpha
_BE = (_FREQ >= 13.0) & (_FREQ < 30.0)   # beta

def _band_powers(buf):
    """θ/α/β мощности одного биполяра методом Уэлча (усреднение сегментов)."""
    n = len(buf)
    if n < _SEG:
        return None
    x = np.asarray(buf, dtype=np.float64)
    x = x - x.mean()
    starts = range(0, n - _SEG + 1, _HOP)
    psd = None; cnt = 0
    for s in starts:
        X = np.fft.rfft(x[s:s + _SEG] * _HANN)
        p = X.real ** 2 + X.imag ** 2
        psd = p if psd is None else psd + p
        cnt += 1
    psd /= cnt
    return float(psd[_TH].sum()), float(psd[_AL].sum()), float(psd[_BE].sum())


def _proxy_from_raw():
    """Мгновенные attention/relaxation прокси из сырья (усреднение двух биполяров)."""
    bpL = _band_powers(_bufL); bpR = _band_powers(_bufR)
    if bpL is None or bpR is None:
        return None
    th = (bpL[0] + bpR[0]) * 0.5
    al = (bpL[1] + bpR[1]) * 0.5
    be = (bpL[2] + bpR[2]) * 0.5
    eps = 1e-9
    engagement = be / (al + th + eps)      # β/(α+θ) — внимание (Pope)
    if engagement > 5.0: engagement = 5.0  # клип от артефакт-спайков (реальный EEG <~2)
    relax = al / (al + be + eps)            # α/(α+β) — расслабление
    return engagement, relax, al, be, th


def _adapt(name_m, name_d, x):
    """Adaptive z-норм через EMA(mean) + EMA(|dev|) -> сигмоида 0..1. Плавная персонализация."""
    a = STEP_SEC / max(BASE_TAU, STEP_SEC)
    m = _base[name_m]; d = _base[name_d]
    if m is None:
        _base[name_m] = x; _base[name_d] = abs(x) * 0.5 + 1e-6
        return 0.5
    m = m + a * (x - m)
    d = d + a * (abs(x - m) - d)
    _base[name_m] = m; _base[name_d] = d
    z = (x - m) / (2.0 * d + 1e-9)          # ~±1 в норме
    return 1.0 / (1.0 + _m.exp(-1.4 * z))    # сигмоида -> 0..1


def _smooth(key, x):
    a = STEP_SEC / max(SMOOTH_TAU, STEP_SEC)
    v = _out[key]
    v = x if v is None else v + a * (x - v)
    _out[key] = v
    return v


# -------------------- сенсор --------------------
def on_state(sensor, state):
    global connected
    connected = ('InRange' in str(state))
    log('состояние бенда: %s' % state)


def on_battery(sensor, battery):
    log('заряд: %s%%' % battery)


def on_signal(sensor, data):
    global math, _calib_done, _blend, _blend_t0, _sent, _last_beat, _last_proc
    if math is None:
        return

    # 1) сырьё -> em_st (фоновая калибровка) + наши буферы
    raw = []
    for s in data:
        l = s.T3 - s.O1; r = s.T4 - s.O2
        raw.append(support_classes.RawChannels(l, r))
        _bufL.append(l); _bufR.append(r)
    math.push_data(raw)
    math.process_data_arr()

    now = time.time()
    if now - _last_proc < STEP_SEC:
        return
    _last_proc = now

    # 2) МГНОВЕННЫЙ прокси из сырья (доступен с ~2-й секунды, без калибровки)
    pr = _proxy_from_raw()
    if pr is None:
        return
    engagement, relax, al, be, th = pr
    att_proxy = _adapt('att_m', 'att_d', engagement)   # 0..1 персонализировано
    rel_proxy = _adapt('rel_m', 'rel_d', relax)

    # 3) em_st: если калибровка завершилась — начать плавный crossfade
    calib_fin = math.calibration_finished()
    if calib_fin and not _calib_done:
        _calib_done = True; _blend_t0 = now
        log('=== em_st калибровка готова -> плавно вплетаю персональный коэффициент (%.0fс) ===' % BLEND_SEC)
    if not calib_fin:
        pct = math.get_calibration_percents()
        # тихий прогресс (не спамим) — раз в ~2с через beat ниже

    # 4) значения em_st (только после калибровки)
    att_em = rel_em = ia_em = ir_em = None
    a_em = b_em = t_em = None
    if calib_fin:
        md = math.read_mental_data_arr()
        if md:
            att_em = md[0].rel_attention / 100.0
            rel_em = md[0].rel_relaxation / 100.0
            ia_em = md[0].inst_attention / 100.0
            ir_em = md[0].inst_relaxation / 100.0
        sd = math.read_spectral_data_percents_arr()
        if sd:
            a_em, b_em, t_em = sd[0].alpha, sd[0].beta, sd[0].theta
        if _blend_t0 is not None:
            _blend = min(1.0, (now - _blend_t0) / BLEND_SEC)

    # 5) микс прокси<->em_st (att/rel в 0..1), сглаживание
    if att_em is not None:
        att = (1.0 - _blend) * att_proxy + _blend * att_em
        rel = (1.0 - _blend) * rel_proxy + _blend * rel_em
    else:
        att, rel = att_proxy, rel_proxy
    att = _smooth('att', att); rel = _smooth('rel', rel)

    # 6) спектр в проценты (для ключей alpha/beta/theta): em_st если есть, иначе из сырья
    if a_em is not None:
        alpha_o, beta_o, theta_o = a_em, b_em, t_em
    else:
        tot = al + be + th + 1e-9
        alpha_o = 100.0 * al / tot; beta_o = 100.0 * be / tot; theta_o = 100.0 * th / tot

    out = {
        'rel_attention':  round(att * 100.0, 2),
        'rel_relaxation': round(rel * 100.0, 2),
        'inst_attention':  round((ia_em if ia_em is not None else att) * 100.0, 2),
        'inst_relaxation': round((ir_em if ir_em is not None else rel) * 100.0, 2),
        'alpha_data': round(alpha_o, 3),
        'beta_data':  round(beta_o, 3),
        'theta_data': round(theta_o, 3),
    }
    if send_to_td(out):
        _sent += 1
    if now - _last_beat > 2.0:
        _last_beat = now
        phase = ('em_st %.0f%%' % (_blend * 100)) if _calib_done else ('калибровка %d%% (фон)' % math.get_calibration_percents())
        log('att=%.2f rel=%.2f | %s | пакетов %d' % (att, rel, phase, _sent))


def build_math():
    mls = lib_settings.MathLibSetting(sampling_rate=250, process_win_freq=25,
                                      n_first_sec_skipped=4, fft_window=1000,
                                      bipolar_mode=True, squared_spectrum=True,
                                      channels_number=4, channel_for_analysis=0)
    ads = lib_settings.ArtifactDetectSetting(art_bord=110, allowed_percent_artpoints=70,
                                             raw_betap_limit=800_000, global_artwin_sec=4,
                                             num_wins_for_quality_avg=125,
                                             hamming_win_spectrum=True, hanning_win_spectrum=False,
                                             total_pow_border=400_000_000, spect_art_by_totalp=True)
    sads = lib_settings.ShortArtifactDetectSetting(ampl_art_detect_win_size=200,
                                                   ampl_art_zerod_area=200, ampl_art_extremum_border=25)
    mss = lib_settings.MentalAndSpectralSetting(n_sec_for_averaging=2, n_sec_for_instant_estimation=4)
    m = emotional_math.EmotionalMath(mls, ads, sads, mss)
    m.set_calibration_length(6)
    m.set_mental_estimation_mode(False)
    m.set_skip_wins_after_artifact(10)
    m.set_zero_spect_waves(True, 0, 1, 1, 1, 0)
    m.set_spect_normalization_by_bands_width(True)
    m.start_calibration()
    return m


def _reset():
    global math, connected, _calib_done, _blend, _blend_t0, _last_proc
    math = None; connected = False; _calib_done = False; _blend = 0.0; _blend_t0 = None; _last_proc = 0.0
    _bufL.clear(); _bufR.clear()
    for k in _base: _base[k] = None
    for k in _out: _out[k] = None


def session():
    global math, connected
    _reset()
    scanner = Scanner([SensorFamily.LEHeadband])
    scanner.sensorsChanged = lambda sc, s: None
    log('ищу нейробенд (Bluetooth)...')
    scanner.start()
    info = None
    for _ in range(30):
        time.sleep(1)
        f = scanner.sensors()
        if f:
            if TARGET:
                m = [s for s in f if TARGET in str(getattr(s, 'Address', '')).lower()
                     or TARGET in str(getattr(s, 'SerialNumber', '')).lower()
                     or TARGET in str(getattr(s, 'Name', '')).lower()]
                info = m[0] if m else f[0]
            else:
                info = f[0]
            break
    scanner.stop()
    if info is None:
        log('бенд не найден — повтор через 5с'); del scanner; time.sleep(5); return
    log('найден %s, подключаюсь...' % getattr(info, 'Name', info))
    sensor = scanner.create_sensor(info)
    connected = True
    sensor.sensorStateChanged = on_state
    sensor.batteryChanged = on_battery
    sensor.signalDataReceived = on_signal
    math = build_math()
    if sensor.is_supported_command(SensorCommand.StartSignal):
        sensor.exec_command(SensorCommand.StartSignal)
        log('сигнал пошёл; метрики идут СРАЗУ (калибровка вплетётся фоном)')
        while connected:
            time.sleep(1)
        log('связь с бендом потеряна')
    try: sensor.exec_command(SensorCommand.StopSignal)
    except Exception: pass
    try: sensor.disconnect()
    except Exception: pass
    try: del sensor; del scanner
    except Exception: pass
    math = None


def main():
    log('=== Neiry LAN узел v2 -> %s:%d (мгновенные метрики + фоновая калибровка) ===' % (HOST, PORT))
    while True:
        try:
            session()
        except KeyboardInterrupt:
            log('остановлено пользователем'); break
        except Exception as e:
            log('сбой сессии: %s — переподключение 3с' % e); time.sleep(3)


if __name__ == '__main__':
    main()
