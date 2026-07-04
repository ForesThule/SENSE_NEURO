' watchdog_hidden.vbs - run the Efir neuro watchdog windowless (no flashing console).
' NEURWATCH task action points here; VBS launches powershell with window style 0 (hidden).
CreateObject("WScript.Shell").Run "powershell -NoProfile -ExecutionPolicy Bypass -File C:\SENSE_TECH\_neurwatch.ps1", 0, False
