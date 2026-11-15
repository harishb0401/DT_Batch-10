@echo off
setlocal
cd /d "%~dp0smart_vehicle_lighting"
set "PATH=C:\Users\HP\AppData\Local\Programs\Python\Python311;C:\Users\HP\AppData\Local\Programs\Python\Python311\Scripts;%PATH%"
echo Running Smart Vehicle Lighting Test Suite...
python -m unittest discover -s tests -p "test_*.py" -v
pause
