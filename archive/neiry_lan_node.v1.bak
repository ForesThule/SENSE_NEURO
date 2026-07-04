# -*- coding: utf-8 -*-
# =====================================================================
#  Neiry -> головной TouchDesigner (Эфир) : УЗЛОВОЙ считыватель по LAN
#  Контракт художницы: TCP JSON -> /project1/NEIRY/tcpip2 (порт 9000)
#
#  Отличия от домашнего installation.py (который слал на 127.0.0.1):
#   - HOST = IP головного ПК по LAN (мини-ПК шлёт на головной, не на себя)
#   - ОДИН постоянный TCP-сокет (не сокет-на-пакет) -> нет WinError 10055
#   - формат JSON НЕ изменён — патч трогать не нужно
#
#  Настройка (env, задаёт launcher .bat):
#     NEIRY_HEAD = 192.168.1.34   (LAN-IP головного; или 100.105.1.91 Tailscale)
#     NEIRY_PORT = 9000
#
#  Запуск: Запустить_нейробенд_LAN.bat  (надеть бенд, дождаться калибровки 100%)
# =====================================================================

import os
import time
import json
import socket

from neurosdk.scanner import Scanner
from neurosdk.cmn_types import *
from em_st_artifacts.utils import lib_settings, support_classes
from em_st_artifacts import emotional_math

HOST = os.environ.get('NEIRY_HEAD', '192.168.1.34')
PORT = int(os.environ.get('NEIRY_PORT', 9000))
TARGET = os.environ.get('NEIRY_ADDR', '').strip().lower()  # свой бэнд: BLE Address / Serial / Name

# ---- служебное ----
math = None
connected = False
calib_done = False
_last_calib = -1
_sent = 0
_last_beat = 0.0
_sock = {'s': None}


def log(msg):
    line = time.strftime('[%H:%M:%S] ') + msg
    print(line, flush=True)
    try:
        f=open('C:/SENSE_TECH/_reader.log','a',encoding='utf-8'); f.write(line+chr(10)); f.close()
    except Exception:
        pass


def _get_sock():
    """UDP-сокет (latest-value-wins): без коннекта -> рестарт головного/TD ПРОЗРАЧЕН; non-blocking -> нет сталла/переполнения."""
    s = _sock['s']
    if s is not None:
        return s
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)   # UDP
        s.setblocking(False)                                    # drop при заполнении, НИКОГДА не блокирует
        _sock['s'] = s
        log('UDP-сокет к %s:%d готов (latest-value-wins)' % (HOST, PORT))
        return s
    except Exception:
        _sock['s'] = None
        return None


def send_to_td(data):
    s = _get_sock()
    if s is None:
        return False
    try:
        s.sendto((json.dumps(data) + '\n').encode('utf-8'), (HOST, PORT))   # fire-and-forget
        return True
    except Exception:
        return False   # UDP: просто дропаем пакет (важно последнее значение), без reset/reconnect


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


def on_state(sensor, state):
    global connected
    connected = ('InRange' in str(state))
    log('состояние бенда: %s' % state)


def on_battery(sensor, battery):
    log('заряд: %s%%' % battery)


def on_signal(sensor, data):
    global math, calib_done, _last_calib, _sent, _last_beat
    if math is None:
        return
    raw = [support_classes.RawChannels(s.T3 - s.O1, s.T4 - s.O2) for s in data]
    math.push_data(raw)
    math.process_data_arr()

    if not math.calibration_finished():
        pct = math.get_calibration_percents()
        if pct != _last_calib:
            _last_calib = pct
            bad = math.is_both_sides_artifacted()
            log('калибровка %d%%%s' % (pct, '  (плохой контакт)' if bad else ''))
        return

    if not calib_done:
        calib_done = True
        log('=== КАЛИБРОВКА ГОТОВА, метрики идут на головной ===')

    out = {}
    md = math.read_mental_data_arr()
    if md:
        out['rel_attention'] = md[0].rel_attention
        out['rel_relaxation'] = md[0].rel_relaxation
        out['inst_attention'] = md[0].inst_attention
        out['inst_relaxation'] = md[0].inst_relaxation
    sd = math.read_spectral_data_percents_arr()
    if sd:
        out['alpha_data'] = sd[0].alpha
        out['beta_data'] = sd[0].beta
        out['theta_data'] = sd[0].theta
    if out:
        if send_to_td(out):
            _sent += 1
        now = time.time()
        if now - _last_beat > 5.0:
            _last_beat = now
            log('метрики -> %s:%d  (пакетов %d)' % (HOST, PORT, _sent))


def session():
    global math, connected, calib_done, _last_calib
    math = None; connected = False; calib_done = False; _last_calib = -1
    sensor = None
    scanner = Scanner([SensorFamily.LEHeadband])
    scanner.sensorsChanged = lambda sc, s: None
    log('ищу нейробенд (Bluetooth)...')
    scanner.start()
    info = None
    for _ in range(30):
        time.sleep(1)
        f = scanner.sensors()
        if not f:
            continue
        if TARGET:
            m = [s for s in f if TARGET in (str(getattr(s,'Address','')).lower()) or TARGET in (str(getattr(s,'SerialNumber','')).lower()) or TARGET in (str(getattr(s,'Name','')).lower())]
            if m:
                info = m[0]; break
            log('svoy band [%s] ne nayden (vidno %d chuzhih) - zhdu' % (TARGET, len(f)))
        else:
            info = max(f, key=lambda s: getattr(s,'RSSI',-999)); break
    scanner.stop()
    if info is None:
        log('бенд не найден — повтор через 5с')
        del scanner; time.sleep(5); return
    log('найден %s, подключаюсь...' % getattr(info, 'Name', info))
    log('BAND Address=%s Serial=%s Name=%s RSSI=%s' % (getattr(info,'Address',''),getattr(info,'SerialNumber',''),getattr(info,'Name',''),getattr(info,'RSSI','')))
    sensor = scanner.create_sensor(info)
    connected = True
    sensor.sensorStateChanged = on_state
    sensor.batteryChanged = on_battery
    sensor.signalDataReceived = on_signal
    math = build_math()
    if sensor.is_supported_command(SensorCommand.StartSignal):
        sensor.exec_command(SensorCommand.StartSignal)
        log('сигнал пошёл; бенд плотно, электроды смочить (калибровка ~1 мин)')
        while connected:
            time.sleep(1)
        log('связь с бендом потеряна')
    try: sensor.exec_command(SensorCommand.StopSignal)
    except Exception: pass
    try: sensor.disconnect()
    except Exception: pass
    try:
        del sensor; del scanner
    except Exception: pass
    math = None


def main():
    log('=== Neiry LAN узел -> головной %s:%d (TCP JSON, контракт художницы) ===' % (HOST, PORT))
    while True:
        try:
            session()
        except KeyboardInterrupt:
            log('остановлено пользователем'); break
        except Exception as e:
            log('сбой сессии: %s — переподключение 3с' % e); time.sleep(3)


if __name__ == '__main__':
    main()
