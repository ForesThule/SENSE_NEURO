# -*- coding: utf-8 -*-
# Найти адреса бэндов рядом. Запусти на мини-ПК с надетым/включённым СВОИМ бэндом.
import time
from neurosdk.scanner import Scanner
from neurosdk.cmn_types import *
sc = Scanner([SensorFamily.LEHeadband])
sc.start(); print('scan 10s...'); time.sleep(10); sc.stop()
f = sc.sensors()
if not f: print('НИЧЕГО НЕ НАЙДЕНО (бэнд включён? донгл вставлен?)')
for s in sorted(f, key=lambda x: -getattr(x,'RSSI',-999)):
    print('Name=%s | Address=%s | Serial=%s | RSSI=%s' % (s.Name, s.Address, s.SerialNumber, s.RSSI))
print('--> впиши Address (или Serial) СВОЕГО (обычно сильнейший RSSI) в NEIRY_ADDR лаунчера')
