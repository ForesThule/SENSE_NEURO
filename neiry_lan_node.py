# -*- coding: utf-8 -*-
# =====================================================================
#  Neiry -> головной TouchDesigner (Эфир) : УЗЛОВОЙ считыватель по LAN
#  Контракт художницы: JSON -> /project1/NEIRY (UDP, порт задаёт launcher)
#
#  Отличия от домашнего installation.py (который слал на 127.0.0.1):
#   - HOST = IP головного ПК по LAN (мини-ПК шлёт на головной, не на себя)
#   - UDP latest-value-wins (не сокет-на-пакет) -> нет WinError 10055,
#     рестарт головного/TD прозрачен
#   - формат JSON метрик НЕ изменён — патч трогать не нужно
#
#  Два потока на головной (оба UDP JSON, по строке на пакет):
#   1) МЕТРИКИ  -> NEIRY_PORT (9003): прежний формат, только после
#      калибровки: rel/inst attention/relaxation, alpha/beta/theta.
#   2) СОБЫТИЯ  -> NEIRY_EVT_PORT (дефолт NEIRY_PORT+10): служебные пакеты вида
#      {"event": "...", "ts": <unix>, ...} — старт узла, скан, коннект,
#      заряд, ход калибровки, контакт электродов, потеря связи, ошибки.
#      Отдельный порт, чтобы НЕ ломать существующий парсер метрик;
#      в TD достаточно добавить второй UDP In DAT. Если художница
#      хочет всё в один порт — выставить NEIRY_EVT_PORT = NEIRY_PORT,
#      но тогда её колбэк обязан игнорировать пакеты с ключом "event".
#
#  Надёжность:
#   - heartbeat ~1/с в C:\SENSE_TECH\logs\neiry_heartbeat.txt (его ждёт
#     вотчдог NEURWATCH: нет свежего heartbeat -> убьёт и перезапустит)
#   - сталл-детектор: сигнал не идёт > STALL_SEC при живом состоянии ->
#     сами рвём сессию и рескан (иначе нативный SDK копит буфер и падает)
#   - Code 108 (AccessDenied/Cannot create BLE device) -> пауза 15с,
#     чтобы Windows отпустила GATT-хендл; бенд НЕ должен быть сопряжён
#     в системном Bluetooth!
#   - слабый RSSI при скане -> не подключаемся, ждём (коннект на -95
#     почти гарантированно кончается 108-й)
#
#  Логи (перманентные, по файлу на час, НИЧЕГО не удаляется):
#   - C:\SENSE_TECH\logs\reader\neiry_YYYY-MM-DD_HH.log — полный архив:
#     все события + строки DBG (каждый отправленный пакет метрик, скан,
#     артефакты, трейсбеки). Ротация сменой файла на границе часа.
#   - C:\SENSE_TECH\_reader.log — как раньше, только важные события
#     (быстрый tail; растёт, чистить руками при случае).
#   - консоль — только важные события, короткое время.
#   Объём архива при идущих метриках ~5-15 МБ/час — следить за диском
#   при прогонах в несколько суток.
#
#  Настройка (env, задаёт launcher .bat):
#     NEIRY_HEAD     = 192.168.1.34   (LAN-IP головного; или 100.105.1.91 Tailscale)
#     NEIRY_PORT     = 9003           (метрики)
#     NEIRY_EVT_PORT = 9013           (события; без env = NEIRY_PORT+10:
#                      efir-1 9013, efir-2 9012, efir-3 9011)
#     NEIRY_ADDR     = ...            (ручное переопределение; штатно ID бенда
#                      лежит в C:\SENSE_TECH\band_id.txt — свой на каждом
#                      мини-ПК, в .gitignore; без ID узел ждёт и НЕ подключается
#                      к чужим бендам никогда)
#
#  Запуск: Запустить_нейробенд_LAN.bat  (надеть бенд, дождаться калибровки 100%)
# =====================================================================

import os
import time
import json
import socket
import traceback

LOG_DIR = 'C:/SENSE_TECH/logs'
HOURLY_DIR = LOG_DIR + '/reader'
HB_PATH = LOG_DIR + '/neiry_heartbeat.txt'
try:
    # ДО импорта neurosdk: SDK при импорте сразу заводит logs/sdk_log.log
    os.makedirs(HOURLY_DIR, exist_ok=True)
except Exception:
    pass

# нативные DLL Neiry падают молча (access violation, python-исключения нет);
# faulthandler успевает дампить python-стек момента краша — по нему видно,
# упало в push_data/process_data_arr или в колбэке SDK
import faulthandler
try:
    _crash_log = open(LOG_DIR + '/crash.log', 'a')
    _crash_log.write('--- start %s pid=%s ---\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), os.getpid()))
    _crash_log.flush()
    faulthandler.enable(_crash_log)
except Exception:
    pass

from neurosdk.scanner import Scanner
from neurosdk.cmn_types import *
from em_st_artifacts.utils import lib_settings, support_classes
from em_st_artifacts import emotional_math

HOST = os.environ.get('NEIRY_HEAD', '192.168.1.34')
PORT = int(os.environ.get('NEIRY_PORT', 9003))  # дефолт = стена R; штатно задаёт .bat
EVT_PORT = int(os.environ.get('NEIRY_EVT_PORT', PORT + 10))  # дефолт по стене: 9013/9012/9011 — три узла не смешиваются
BAND_FILE = 'C:/SENSE_TECH/band_id.txt'   # ID своего бенда: уникален на КАЖДОМ мини-ПК, в .gitignore


def _read_band_file():
    """Первая непустая некомментарная строка band_id.txt: Address или Serial бенда."""
    try:
        for line in open(BAND_FILE, encoding='utf-8'):
            line = line.strip()
            if line and not line.startswith('#'):
                return line
    except Exception:
        pass
    return ''


TARGET = (os.environ.get('NEIRY_ADDR', '').strip() or _read_band_file()).lower()  # env переопределяет файл

RSSI_MIN = -85        # слабее — не подключаемся, ждём пока подойдёт ближе
STALL_SEC = 15        # нет сигнала столько секунд -> принудительный разрыв
CALIB_STALL_SEC = 180 # калибровка не растёт столько секунд -> разрыв и рескан
                      # (данные идут, но грязные — Neiry не засчитывает окна,
                      # обычный сталл-детектор этого не видит)
CODE108_WAIT = 15     # пауза после Cannot create BLE device (ждём освобождения GATT)

# ---- служебное ----
math = None
connected = False
calib_done = False
_last_calib = -1
_last_art = None
_sent = 0
_last_beat = 0.0
_last_data = {'t': 0.0}
_calib_prog = {'t': 0.0}   # время последнего РОСТА процента калибровки
_sock = {'s': None}
_logf = {'hour': None, 'f': None}


# ---------------- логирование ----------------
# Почасовой архив: имя файла = текущий час, на границе часа хендл
# переоткрывается на новый файл. Старые файлы никогда не трогаем.

def _stamp():
    t = time.time()
    return time.strftime('[%Y-%m-%d %H:%M:%S', time.localtime(t)) + '.%03d]' % int((t % 1) * 1000)


def _hourly_file():
    hour = time.strftime('%Y-%m-%d_%H')
    if _logf['f'] is None or _logf['hour'] != hour:
        try:
            if _logf['f'] is not None:
                _logf['f'].close()
        except Exception:
            pass
        try:
            os.makedirs(HOURLY_DIR, exist_ok=True)
            _logf['f'] = open('%s/neiry_%s.log' % (HOURLY_DIR, hour), 'a', encoding='utf-8')
            _logf['hour'] = hour
        except Exception:
            _logf['f'] = None
    return _logf['f']


def _archive(line):
    f = _hourly_file()
    if f is None:
        return
    try:
        f.write(line + '\n')
        f.flush()
    except Exception:
        _logf['f'] = None   # переоткроем на следующей записи


def log(msg):
    """Важное событие: консоль + _reader.log + почасовой архив."""
    print(time.strftime('[%H:%M:%S] ') + msg, flush=True)
    _archive(_stamp() + ' ' + msg)
    try:
        f = open('C:/SENSE_TECH/_reader.log', 'a', encoding='utf-8')
        f.write(time.strftime('[%H:%M:%S] ') + msg + chr(10))
        f.close()
    except Exception:
        pass


def dbg(msg):
    """Подробность (каждый пакет, скан, трейсбек): только почасовой архив."""
    _archive(_stamp() + ' DBG ' + msg)


def beat():
    """Heartbeat для вотчдога NEURWATCH: unix-время UTC, перезапись файла ~1/с."""
    try:
        f = open(HB_PATH, 'w')
        f.write(str(int(time.time())))
        f.close()
    except Exception:
        pass


def sleep_beating(sec):
    """Пауза с heartbeat каждую секунду, чтобы вотчдог не счёл нас зависшими."""
    for _ in range(int(sec)):
        beat(); time.sleep(1)


# ---------------- отправка на головной ----------------

def _get_sock():
    """UDP-сокет (latest-value-wins): без коннекта -> рестарт головного/TD ПРОЗРАЧЕН; non-blocking -> нет сталла/переполнения."""
    s = _sock['s']
    if s is not None:
        return s
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)   # UDP
        s.setblocking(False)                                    # drop при заполнении, НИКОГДА не блокирует
        _sock['s'] = s
        log('UDP-сокет к %s (метрики :%d, события :%d) готов' % (HOST, PORT, EVT_PORT))
        return s
    except Exception:
        _sock['s'] = None
        return None


def send_to_td(data):
    """Пакет метрик -> NEIRY_PORT. Формат контракта, НЕ менять."""
    s = _get_sock()
    if s is None:
        return False
    try:
        s.sendto((json.dumps(data) + '\n').encode('utf-8'), (HOST, PORT))   # fire-and-forget
        return True
    except Exception as e:
        dbg('send_to_td drop: %s' % e)
        return False   # UDP: просто дропаем пакет (важно последнее значение), без reset/reconnect


def send_event(name, **fields):
    """Ключевое событие -> NEIRY_EVT_PORT: {"event": name, "ts": unix, ...}."""
    pkt = {'event': name, 'ts': int(time.time())}
    pkt.update(fields)
    s = _get_sock()
    if s is None:
        dbg('event %s: нет сокета, не отправлено' % name)
        return False
    try:
        s.sendto((json.dumps(pkt) + '\n').encode('utf-8'), (HOST, EVT_PORT))
        dbg('event -> :%d %s' % (EVT_PORT, json.dumps(pkt)))
        return True
    except Exception as e:
        dbg('event %s drop: %s' % (name, e))
        return False


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
    was = connected
    connected = ('InRange' in str(state))
    log('состояние бенда: %s' % state)
    if was != connected:
        send_event('band_state', in_range=connected, state=str(state))


def on_battery(sensor, battery):
    log('заряд: %s%%' % battery)
    try:
        send_event('battery', percent=int(battery))
    except Exception:
        send_event('battery', percent=str(battery))


def on_signal(sensor, data):
    global math, calib_done, _last_calib, _last_art, _sent, _last_beat
    _last_data['t'] = time.time()
    if math is None:
        return
    raw = [support_classes.RawChannels(s.T3 - s.O1, s.T4 - s.O2) for s in data]
    math.push_data(raw)
    math.process_data_arr()

    if not math.calibration_finished():
        pct = math.get_calibration_percents()
        if pct != _last_calib:
            _last_calib = pct
            _calib_prog['t'] = time.time()
            bad = math.is_both_sides_artifacted()
            log('калибровка %d%%%s' % (pct, '  (плохой контакт)' if bad else ''))
            send_event('calibration', percent=pct, bad_contact=bool(bad))
        return

    if not calib_done:
        calib_done = True
        log('=== КАЛИБРОВКА ГОТОВА, метрики идут на головной ===')
        send_event('calibration_done')

    # контакт электродов после калибровки: логируем только переходы
    art = math.is_both_sides_artifacted()
    if art != _last_art:
        _last_art = art
        log('контакт электродов: %s' % ('ПЛОХОЙ (артефакты с обеих сторон)' if art else 'ок'))
        send_event('contact', ok=not art)

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
        ok = send_to_td(out)
        if ok:
            _sent += 1
        dbg('pkt #%d %s -> %s' % (_sent, json.dumps(out), 'sent' if ok else 'DROP'))
        now = time.time()
        if now - _last_beat > 5.0:
            _last_beat = now
            log('метрики -> %s:%d  (пакетов %d)' % (HOST, PORT, _sent))


def session():
    global math, connected, calib_done, _last_calib, _last_art
    math = None; connected = False; calib_done = False; _last_calib = -1; _last_art = None
    sensor = None
    scanner = Scanner([SensorFamily.LEHeadband])
    scanner.sensorsChanged = lambda sc, s: None
    log('ищу нейробенд (Bluetooth)...')
    send_event('scanning')
    scanner.start()
    info = None
    for _ in range(30):
        beat()
        time.sleep(1)
        f = scanner.sensors()
        if not f:
            continue
        dbg('скан: ' + '; '.join('%s/%s/RSSI=%s' % (getattr(s,'Name',''), getattr(s,'Address',''), getattr(s,'RSSI','?')) for s in f))
        # только СВОЙ бенд — к чужим не подключаемся никогда
        m = [s for s in f if TARGET in (str(getattr(s,'Address','')).lower()) or TARGET in (str(getattr(s,'SerialNumber','')).lower()) or TARGET in (str(getattr(s,'Name','')).lower())]
        if not m:
            log('svoy band [%s] ne nayden (vidno %d chuzhih) - zhdu' % (TARGET, len(f)))
            continue
        cand = m[0]
        rssi = getattr(cand, 'RSSI', None)
        if rssi is not None and rssi < RSSI_MIN:
            log('бенд найден, но сигнал слабый (RSSI %s < %s) — не подключаюсь, жду' % (rssi, RSSI_MIN))
            send_event('weak_signal', rssi=rssi, rssi_min=RSSI_MIN)
            continue
        info = cand
        break
    scanner.stop()
    if info is None:
        log('бенд не найден — повтор через 5с')
        send_event('band_not_found')
        del scanner; sleep_beating(5); return
    log('найден %s, подключаюсь...' % getattr(info, 'Name', info))
    log('BAND Address=%s Serial=%s Name=%s RSSI=%s' % (getattr(info,'Address',''),getattr(info,'SerialNumber',''),getattr(info,'Name',''),getattr(info,'RSSI','')))
    send_event('band_found', address=str(getattr(info,'Address','')), serial=str(getattr(info,'SerialNumber','')), rssi=getattr(info,'RSSI',None))
    sensor = scanner.create_sensor(info)
    connected = True
    sensor.sensorStateChanged = on_state
    sensor.batteryChanged = on_battery
    sensor.signalDataReceived = on_signal
    math = build_math()
    if sensor.is_supported_command(SensorCommand.StartSignal):
        sensor.exec_command(SensorCommand.StartSignal)
        log('сигнал пошёл; бенд плотно, электроды смочить (калибровка ~1 мин)')
        send_event('signal_started')
        _last_data['t'] = time.time()
        _calib_prog['t'] = time.time()
        while connected:
            beat()
            time.sleep(1)
            if time.time() - _last_data['t'] > STALL_SEC:
                log('сигнал не идёт %dс при живом соединении — принудительный разрыв, рескан' % STALL_SEC)
                send_event('signal_stall', stall_sec=STALL_SEC)
                break
            if not calib_done and time.time() - _calib_prog['t'] > CALIB_STALL_SEC:
                log('калибровка застряла на %d%% дольше %dс (грязный сигнал) — разрыв, рескан' % (max(_last_calib, 0), CALIB_STALL_SEC))
                send_event('calibration_stall', percent=max(_last_calib, 0), stall_sec=CALIB_STALL_SEC)
                break
        else:
            log('связь с бендом потеряна')
            send_event('band_lost')
    log('сессия закрывается (отправлено пакетов: %d)' % _sent)
    send_event('session_end', packets=_sent, calibrated=calib_done)
    try: sensor.exec_command(SensorCommand.StopSignal)
    except Exception: pass
    try: sensor.disconnect()
    except Exception: pass
    try:
        del sensor; del scanner
    except Exception: pass
    math = None


def single_instance_lock():
    """Лок 'один экземпляр': держим TCP-порт на localhost. Второй процесс
    не сможет забиндиться и выйдет — двое дерутся за один бенд (Code 108)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', 47653))
        s.listen(1)
        return s
    except OSError:
        return None


def main():
    global TARGET
    try:
        os.makedirs(HOURLY_DIR, exist_ok=True)
    except Exception:
        pass
    lock = single_instance_lock()
    if lock is None:
        # НЕ трогаем heartbeat: он принадлежит живому экземпляру, иначе
        # дубликат маскирует фриз основного процесса от вотчдога
        log('!!! другой экземпляр уже запущен — выхожу (проверь второй launcher/задачу NEIRYSTART)')
        send_event('duplicate_instance')
        time.sleep(10)   # чтобы цикл .bat не молотил рестарты впустую
        return
    beat()
    log('=== Neiry LAN узел -> головной %s (метрики :%d, события :%d, UDP JSON) ===' % (HOST, PORT, EVT_PORT))
    if 'NEIRY_PORT' not in os.environ:
        log('!!! NEIRY_PORT не задан — использую дефолт %d (стена R). Запускай через START_NEIRY_LAN.bat' % PORT)
    while not TARGET:
        log('!!! нет ID бенда: создай %s (одна строка — адрес из python scan_bands.py) или задай env NEIRY_ADDR — жду 30с' % BAND_FILE)
        send_event('no_band_id')
        sleep_beating(30)
        TARGET = (os.environ.get('NEIRY_ADDR', '').strip() or _read_band_file()).lower()
    src = 'env NEIRY_ADDR' if os.environ.get('NEIRY_ADDR', '').strip() else 'band_id.txt'
    log('целевой бенд: %s (%s)' % (TARGET, src))
    dbg('env: NEIRY_HEAD=%s NEIRY_PORT=%s NEIRY_EVT_PORT=%s NEIRY_ADDR=%s | RSSI_MIN=%d STALL_SEC=%d CALIB_STALL=%d' % (HOST, PORT, EVT_PORT, TARGET or '-', RSSI_MIN, STALL_SEC, CALIB_STALL_SEC))
    send_event('node_start', target=TARGET or None)
    while True:
        try:
            session()
        except KeyboardInterrupt:
            log('остановлено пользователем')
            send_event('node_stop', reason='keyboard')
            break
        except Exception as e:
            msg = str(e)
            wait = CODE108_WAIT if '108' in msg else 3
            hint = '  (бенд сопряжён в Windows? выключи/включи бенд)' if '108' in msg else ''
            log('сбой сессии: %s — переподключение %dс%s' % (msg, wait, hint))
            dbg('traceback:\n' + traceback.format_exc())
            send_event('session_error', message=msg[:200], code108=('108' in msg), retry_sec=wait)
            sleep_beating(wait)


if __name__ == '__main__':
    main()
