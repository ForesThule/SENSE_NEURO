@echo off
title NEIRY_LAN_NODE
cd /d "C:\SENSE_TECH"
set "NEIRY_HEAD=192.168.1.34"
set "NEIRY_PORT=9003"
set "NEIRY_EVT_PORT=9013"
rem ID бенда НЕ здесь: он в C:\SENSE_TECH\band_id.txt (свой на каждом мини-ПК, в .gitignore)
:loop
python "C:\SENSE_TECH\neiry_lan_node.py"
timeout /t 3 /nobreak >nul
goto loop
