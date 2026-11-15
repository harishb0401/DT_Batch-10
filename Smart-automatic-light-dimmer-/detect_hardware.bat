@echo off
setlocal
cd /d "%~dp0smart_vehicle_lighting"
set "PATH=C:\Users\HP\AppData\Local\Programs\Python\Python311;C:\Users\HP\AppData\Local\Programs\Python\Python311\Scripts;%PATH%"
python scripts\detect_hardware.py
pause
