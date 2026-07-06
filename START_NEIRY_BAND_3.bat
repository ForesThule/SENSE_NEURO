@echo off
title NEIRY_BAND_3_L
cd /d "C:\SENSE_TECH"
set "NEIRY_HEAD=192.168.1.34"
rem бенд/порты вшиты в neiry_band_3.py (EF:21:DE:1C:A3:67 -> 9001/9011, стена L)
:loop
python "C:\SENSE_TECH\neiry_band_3.py"
timeout /t 3 /nobreak >nul
goto loop
