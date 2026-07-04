@echo off
cd /d "C:\SENSE_TECH"
set "NEIRY_HEAD=192.168.1.34"
set "NEIRY_PORT=9003"
set "NEIRY_ADDR=F7:14:0E:FE:9D:20"
:loop
python "C:\SENSE_TECH\neiry_lan_node.py"
timeout /t 3 /nobreak >nul
goto loop
