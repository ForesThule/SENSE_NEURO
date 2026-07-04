# SENSE_TECH — рантайм нейро-узла «Эфир» (мини-ПК efir-1 / efir-2 / efir-3)

Папка на каждом мини-ПК. Читает нейробэнд Neiry по Bluetooth, считает метрики
внимания/расслабления и шлёт их по UDP на головной ПК (TouchDesigner), который
гонит проекцию на стену. Выставка 24/7 (ЦСИ М'АРС), смены по 12 ч.

## Структура папки
```
neiry_lan_node.py     — ридер: метрики после калибровки Neiry (~1 мин); закалён
                        под 24/7: heartbeat ~1/с, сталл-детектор (>15 с без
                        сигнала -> разрыв и рескан), пауза 15 с на Code 108,
                        порог RSSI -85 при скане, лок «один экземпляр»
                        (localhost:47653), почасовые логи, поток событий в TD
START_NEIRY_LAN.bat   — лаунчер: env NEIRY_HEAD/PORT/EVT_PORT + вечный цикл python (рестарт 3с)
band_id.txt           — не в git: ID СВОЕГО бенда (Address/Serial), уникален на
                        каждом мини-ПК; шаблон — band_id.example.txt. Без него
                        узел ждёт и ни к чему не подключается
scan_bands.py         — найти BLE-адрес своего бэнда
_neurwatch.ps1        — сторож (задача NEURWATCH, каждые 2 мин): оживляет ридер
watchdog_hidden.vbs   — обёртка: запускает _neurwatch.ps1 без мигающего окна
README.md             — этот файл
logs\                 — не в git: neiry_heartbeat.txt, watchdog.log,
                        reader\neiry_YYYY-MM-DD_HH.log (почасовой полный архив,
                        ~5-15 МБ/час при идущих метриках — следить за диском)
_reader.log           — не в git: только важные события, для быстрого tail
vendor\               — установочные артефакты (numpy .whl, Autologon64.exe) для переустановки
archive\              — старые версии (.v1.bak, *_v2.legacy.py), легаси-нода (node_legacy)
```

## Автозапуск и надёжность (24/7)
- **NEIRYSTART** (задача, onLogon) → `START_NEIRY_LAN.bat` → вечный цикл python.
- **NEURWATCH** (задача, /mo 2) → `watchdog_hidden.vbs` → `_neurwatch.ps1`: ридер мёртв
  ИЛИ heartbeat старше 60 с (зависание) → убить + перезапустить. Heartbeat пишется ~1/с
  (даже при поиске бэнда), поэтому «протухший» heartbeat = реальный фриз, а не «нет бэнда».
  Сторож трогает только python с `neiry_lan_node.py` в командной строке.
- Ридер сам реконнектится; рвёт сессию при «замере сигнала» (>15 с без данных);
  второй экземпляр выходит сам (лок на localhost:47653) — двое дерутся за один
  бэнд и дают Code 108/AccessDenied.
- Бэнд НЕ должен быть сопряжён в Bluetooth Windows — иначе Code 108.

## Контракт с головным (PRE-FINAL.13 — НЕ менять)
Метрики: UDP JSON+'\n' → головной, порт по стене: **efir-1 = 9003 (R), efir-2 = 9002 (C),
efir-3 = 9001 (L)**. Ключи: `rel_attention rel_relaxation inst_attention
inst_relaxation alpha_data beta_data theta_data`. Стену гонит `inst_attention`.
Идут только после калибровки 100%. Ключи в пакете НЕ гарантированы все сразу —
брать по имени, отсутствующие пропускать.
Сеть/порты — в `START_NEIRY_LAN.bat` (NEIRY_HEAD / NEIRY_PORT); ID бенда — в
`band_id.txt` (env NEIRY_ADDR переопределяет его вручную).

## События (дополнение к контракту, отдельный порт)
Служебный поток: UDP JSON+'\n' → головной, порт **NEIRY_EVT_PORT = метрики+10**
(efir-1 = 9013, efir-2 = 9012, efir-3 = 9011). Формат:
`{"event": "<имя>", "ts": <unix>, ...}`. События: `node_start node_stop scanning
band_found weak_signal band_not_found signal_started calibration(percent)
calibration_done battery(percent) contact(ok) band_state signal_stall band_lost
session_end session_error duplicate_instance`. Патч метрик они не задевают —
в TD это отдельный UDP In DAT; пока приёмника нет, пакеты просто теряются.

## Операции на месте
| Задача | Команда |
|---|---|
| Проверить живость | `type logs\neiry_heartbeat.txt` (unix-ts растёт) · хвост `_reader.log` |
| Полный разбор инцидента | `logs\reader\neiry_YYYY-MM-DD_HH.log` (DBG: каждый пакет, сканы, трейсбеки) |
| Найти адрес бэнда | `python scan_bands.py` → вписать в `band_id.txt` (шаблон band_id.example.txt) |
| Ручной старт | `schtasks /run /tn NEIRYSTART` (или запустить `START_NEIRY_LAN.bat`) |
| Остановить | `taskkill /F /IM python.exe` (лаунчер поднимет заново; совсем — снять NEIRYSTART) |
| Лог сторожа | `logs\watchdog.log` (пишется только при инцидентах) |

Источник (dev, ProArt): `C:\WORK\PROJECTS\Money\Sense\june_update\Ephyr\Neiry\node_osc`.
Раскладку приводит `organize_sense_tech.ps1` (там же) — идемпотентно, запускать на любой машине.
