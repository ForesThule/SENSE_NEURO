@echo off
title NEIRY_BAND_1_R
cd /d "C:\SENSE_TECH"
set "NEIRY_HEAD=192.168.1.34"
rem бенд/порты вшиты в neiry_band_1.py (F7:14:0E:FE:9D:20 -> 9003/9013, стена R)
:loop
python "C:\SENSE_TECH\neiry_band_1.py"
timeout /t 3 /nobreak >nul
goto loop
