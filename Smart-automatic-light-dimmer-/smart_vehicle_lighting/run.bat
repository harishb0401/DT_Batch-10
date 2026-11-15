@echo off
setlocal
cd /d "%~dp0"
set "PATH=%LOCALAPPDATA%\Programs\Python\Python313;%LOCALAPPDATA%\Programs\Python\Python313\Scripts;C:\Program Files\Python313;C:\Program Files\Python313\Scripts;C:\Program Files\Python311;C:\Program Files\Python311\Scripts;D:\Python311;D:\Python311\Scripts;%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
echo =========================================================
echo   Starting AI Smart Vehicle Lighting System...
echo =========================================================

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    py -m src.main %*
) else (
    python -m src.main %*
)
pause
