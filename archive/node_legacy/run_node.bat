@echo off
chcp 65001 >nul
setlocal
set HERE=%~dp0
rem  usage:  run_node.bat [node-id] [head-ip]
set NODE=%1
if "%NODE%"=="" set /p NODE=Node id (1/2/3):
set HEADIP=%2
if "%HEADIP%"=="" set HEADIP=100.105.1.91

if not exist "%HERE%.venv\Scripts\python.exe" (
  echo === creating venv (first run) ===
  py -3.11 -m venv "%HERE%.venv" 2>nul || python -m venv "%HERE%.venv"
  "%HERE%.venv\Scripts\python.exe" -m pip install --upgrade pip
  "%HERE%.venv\Scripts\python.exe" -m pip install -r "%HERE%requirements.txt"
)

echo === node %NODE%  ->  %HEADIP%:900%NODE% ===
"%HERE%.venv\Scripts\python.exe" "%HERE%emo_send_node.py" --node-id %NODE% --head-ip %HEADIP%
pause
