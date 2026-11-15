@echo off
setlocal
cd /d "%~dp0smart_vehicle_lighting"
set "PATH=C:\Users\HP\AppData\Local\Programs\Python\Python311;C:\Users\HP\AppData\Local\Programs\Python\Python311\Scripts;%PATH%"
echo Starting AI Smart Vehicle Lighting System...
python -m src.main
pause
