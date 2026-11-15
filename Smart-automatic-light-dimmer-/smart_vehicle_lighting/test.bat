@echo off
setlocal
cd /d "%~dp0"
set "PATH=C:\Users\HP\AppData\Local\Programs\Python\Python311;C:\Users\HP\AppData\Local\Programs\Python\Python311\Scripts;%PATH%"
echo Running Smart Vehicle Lighting Test Suite...
python -m unittest discover -s tests -p "test_*.py" -v
pause
