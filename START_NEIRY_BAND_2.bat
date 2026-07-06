@echo off
title NEIRY_BAND_2_C
cd /d "C:\SENSE_TECH"
set "NEIRY_HEAD=192.168.1.34"
rem бенд/порты вшиты в neiry_band_2.py (C6:0D:7C:18:44:AA -> 9002/9012, стена C)
:loop
python "C:\SENSE_TECH\neiry_band_2.py"
timeout /t 3 /nobreak >nul
goto loop
