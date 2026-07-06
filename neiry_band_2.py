# -*- coding: utf-8 -*-
# =====================================================================
#  Neiry -> головной TouchDesigner (Эфир) : ридер бенда стены C
#  ЭКЗЕМПЛЯР 2 из 3 — все три бенда на ОДНОЙ машине, по процессу на бенд:
#  нативный neurosdk падает access violation'ом целым процессом, изоляция
#  процессов = краш одного бенда не трогает две другие стены.
#
#  ЭТОТ ФАЙЛ СГЕНЕРИРОВАН из шаблона (см. README) — правки вносить в шаблон
#  и перегенерировать все три, иначе экземпляры разъедутся.
#
#  Бенд:    C6:0D:7C:18:44:AA  (вшит; env НЕ переопределяет — см. комментарий у PORT)
#  Метрики: UDP JSON -> NEIRY_HEAD:9002   (контракт художницы, НЕ менять)
#  События: UDP JSON -> NEIRY_HEAD:9012   {"event": ..., "band": "C", ...}
#
#  Межпроцессная дисциплина:
#   - лок экземпляра: localhost:47655 (дубль выходит сам)
#   - шлюз подключения logs/connect.lock: create_sensor строго по одному —
#     одновременные коннекты через один BT-адаптер = access violation в SDK
#   - сдвиг старта 10с, чтобы после ребута три процесса не ломились хором
#   - heartbeat: logs/neiry_heartbeat_2.txt (~1/с, его ждёт NEURWATCH)
#
#  Надёжность (как в однобендовом ридере):
#   - сталл-детектор >15с без сигнала; застрявшая калибровка >180с;
#   - Code 108 -> пауза 15с; порог RSSI (env NEIRY_RSSI_MIN, дефолт -85);
#   - бенд НЕ должен быть сопряжён в Bluetooth Windows;
#   - faulthandler -> logs/crash_2.log; почасовые логи logs/reader_2/.
#
#  Запуск: START_NEIRY_BAND_2.bat (задача NEIRYSTART2, onlogon)
# =====================================================================

import os
import time
import json
import socket
import threading
import traceback

# ==== конфигурация экземпляра (единственное отличие трёх скриптов) ====
BAND_LABEL = 'C'   # стена: R / C / L
BAND_ADDR = 'C6:0D:7C:18:44:AA'     # свой бенд этого экземпляра
INSTANCE = 2           # номер экземпляра 1..3
START_DELAY = 10    # сдвиг старта, с
LOCK_PORT = 47655   # лок «один экземпляр» (47653 + INSTANCE)

HOST = os.environ.get('NEIRY_HEAD', '192.168.1.34')
# порты и бенд НАМЕРЕННО без env-переопределений: `set NEIRY_PORT=9003` от
# старого START_NEIRY_LAN.bat живёт в сессии cmd до её закрытия, и экземпляр C
# уезжал метриками на порт стены R (поймано в бою 2026-07-06)
PORT = 9002        # метрики
EVT_PORT = 9012     # события
TARGET = BAND_ADDR.lower()

RSSI_MIN = int(os.environ.get('NEIRY_RSSI_MIN', -85))  # слабее — не подключаемся
STALL_SEC = 15        # нет сигнала столько секунд -> принудительный разрыв
CALIB_STALL_SEC = 180 # калибровка не растёт столько секунд -> разрыв и рескан
CODE108_WAIT = 15     # пауза после Cannot create BLE device (ждём освобождения GATT)
GATE_WAIT = 120       # сколько ждать шлюз подключения, с

LOG_DIR = 'C:/SENSE_TECH/logs'
HOURLY_DIR = LOG_DIR + '/reader_%d' % INSTANCE
HB_PATH = LOG_DIR + '/neiry_heartbeat_%d.txt' % INSTANCE
READER_LOG = 'C:/SENSE_TECH/_reader_%d.log' % INSTANCE
GATE_PATH = LOG_DIR + '/connect.lock'          # ОБЩИЙ для всех трёх экземпляров
try:
    # ДО импорта neurosdk: SDK при импорте сразу заводит logs/sdk_log.log
    # (sdk_log.log общий у трёх процессов — SDK пишет в append, терпимо)
    os.makedirs(HOURLY_DIR, exist_ok=True)
except Exception:
    pass

# нативные DLL Neiry падают молча (access violation, python-исключения нет);
# faulthandler успевает дампить python-стек момента краша
import faulthandler
try:
    _crash_log = open(LOG_DIR + '/crash_%d.log' % INSTANCE, 'a')
    _crash_log.write('--- start %s pid=%s ---\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), os.getpid()))
    _crash_log.flush()
    faulthandler.enable(_crash_log)
except Exception:
    pass

from neurosdk.scanner import Scanner
from neurosdk.cmn_types import *
from em_st_artifacts.utils import lib_settings, support_classes
from em_st_artifacts import emotional_math

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
_io_lock = threading.Lock()   # колбэки SDK приходят из своих потоков


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
    with _io_lock:
        f = _hourly_file()
        if f is None:
            return
        try:
            f.write(line + '\n')
            f.flush()
        except Exception:
            _logf['f'] = None   # переоткроем на следующей записи


def log(msg):
    """Важное событие: консоль + _reader_N.log + почасовой архив."""
    msg = '[%s] %s' % (BAND_LABEL, msg)
    print(time.strftime('[%H:%M:%S] ') + msg, flush=True)
    _archive(_stamp() + ' ' + msg)
    try:
        f = open(READER_LOG, 'a', encoding='utf-8')
        f.write(time.strftime('[%H:%M:%S] ') + msg + chr(10))
        f.close()
    except Exception:
        pass


def dbg(msg):
    """Подробность (каждый пакет, скан, трейсбек): только почасовой архив."""
    _archive(_stamp() + ' DBG [%s] %s' % (BAND_LABEL, msg))


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


# ---------------- шлюз подключения (межпроцессный) ----------------
# create_sensor у SDK падает access violation'ом при обрыве в момент коннекта;
# одновременные коннекты трёх процессов через один адаптер — гарантия краша.
# Подключается только тот, кто создал connect.lock; протухший лок (>3 мин,
# владелец умер в момент коннекта) снимаем сами.

def gate_acquire():
    t0 = time.time()
    while time.time() - t0 < GATE_WAIT:
        try:
            fd = os.open(GATE_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except OSError:
            try:
                if time.time() - os.path.getmtime(GATE_PATH) > 180:
                    os.remove(GATE_PATH)
                    continue
            except OSError:
                pass
            beat(); time.sleep(1)
    return False


def gate_release():
    try:
        os.remove(GATE_PATH)
    except OSError:
        pass


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
    """Ключевое событие -> NEIRY_EVT_PORT: {"event": name, "ts": unix, "band": LABEL, ...}."""
    pkt = {'event': name, 'ts': int(time.time()), 'band': BAND_LABEL}
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


def dump_band_info(sensor):
    """Всё, что можно вытащить из бенда через SDK: серийник, прошивка, железо,
    батарея, каналы, частота, фичи/команды/параметры. Каждое поле читается
    защищённо — недоступное просто пропускаем (DBG скажет почему)."""
    info = {}

    def grab(key, fn):
        try:
            v = fn()
            if v is not None:
                info[key] = v
        except Exception as e:
            dbg('band_info: %s недоступно (%s)' % (key, e))

    grab('name', lambda: str(sensor.name))
    grab('address', lambda: str(sensor.address))
    grab('serial', lambda: str(sensor.serial_number))
    grab('family', lambda: str(sensor.sensor_family))
    grab('state', lambda: str(sensor.state))
    grab('battery', lambda: int(sensor.batt_power))
    grab('channels', lambda: int(sensor.channels_count))
    grab('sampling_frequency', lambda: str(sensor.sampling_frequency))
    grab('gain', lambda: str(sensor.gain))
    grab('data_offset', lambda: str(sensor.data_offset))
    grab('firmware_mode', lambda: str(sensor.firmware_mode))

    def _ver():
        v = sensor.version
        return 'FW %s.%s.%s / HW %s.%s.%s / Ext %s' % (
            getattr(v, 'FwMajor', '?'), getattr(v, 'FwMinor', '?'), getattr(v, 'FwPatch', '?'),
            getattr(v, 'HwMajor', '?'), getattr(v, 'HwMinor', '?'), getattr(v, 'HwPatch', '?'),
            getattr(v, 'ExtMajor', '?'))
    grab('version', _ver)

    grab('features', lambda: ', '.join(str(x) for x in sensor.features))
    grab('commands', lambda: ', '.join(str(x) for x in sensor.commands))
    grab('parameters', lambda: ', '.join('%s[%s]' % (getattr(p, 'Param', p), getattr(p, 'ParamAccess', '?')) for p in sensor.parameters))

    for k in ('name', 'address', 'serial', 'family', 'version', 'firmware_mode',
              'battery', 'channels', 'sampling_frequency', 'gain', 'data_offset', 'state'):
        if k in info:
            log('бенд-инфо: %s = %s' % (k, info[k]))
    for k in ('features', 'commands', 'parameters'):
        if k in info:
            dbg('бенд-инфо %s: %s' % (k, info[k]))

    send_event('band_info', **{k: info[k] for k in
        ('serial', 'address', 'name', 'family', 'version', 'firmware_mode',
         'battery', 'channels', 'sampling_frequency') if k in info})


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
    # --- шлюз: подключается только один экземпляр за раз ---
    if not gate_acquire():
        log('шлюз подключения занят > %dс — отдаю очередь, рескан' % GATE_WAIT)
        send_event('gate_timeout')
        del scanner; return
    started = False
    try:
        sensor = scanner.create_sensor(info)
        connected = True
        sensor.sensorStateChanged = on_state
        sensor.batteryChanged = on_battery
        sensor.signalDataReceived = on_signal
        dump_band_info(sensor)
        math = build_math()
        if sensor.is_supported_command(SensorCommand.StartSignal):
            sensor.exec_command(SensorCommand.StartSignal)
            started = True
            log('сигнал пошёл; бенд плотно, электроды смочить (калибровка ~1 мин)')
            send_event('signal_started')
    finally:
        gate_release()
    if started:
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
        s.bind(('127.0.0.1', LOCK_PORT))
        s.listen(1)
        return s
    except OSError:
        return None


def main():
    try:
        os.makedirs(HOURLY_DIR, exist_ok=True)
    except Exception:
        pass
    lock = single_instance_lock()
    if lock is None:
        # НЕ трогаем heartbeat: он принадлежит живому экземпляру, иначе
        # дубликат маскирует фриз основного процесса от вотчдога
        log('!!! другой экземпляр [%s] уже запущен — выхожу (проверь launcher/задачу NEIRYSTART%d)' % (BAND_LABEL, INSTANCE))
        send_event('duplicate_instance')
        time.sleep(10)   # чтобы цикл .bat не молотил рестарты впустую
        return
    beat()
    log('=== Neiry узел [%s] %d/3 -> головной %s (метрики :%d, события :%d, UDP JSON) ===' % (BAND_LABEL, INSTANCE, HOST, PORT, EVT_PORT))
    dbg('cfg: HEAD=%s PORT=%d EVT=%d TARGET=%s | RSSI_MIN=%d STALL_SEC=%d CALIB_STALL=%d DELAY=%d' % (HOST, PORT, EVT_PORT, TARGET, RSSI_MIN, STALL_SEC, CALIB_STALL_SEC, START_DELAY))
    log('целевой бенд: %s (вшитый)' % TARGET)
    send_event('node_start', target=TARGET, instance=INSTANCE)
    if START_DELAY > 0:
        log('сдвиг старта %dс (очередь к BT-адаптеру)' % START_DELAY)
        sleep_beating(START_DELAY)
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
