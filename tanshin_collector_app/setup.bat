@echo off
cd /d "%~dp0"
set "PY="

if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if defined PY goto found

py -3 --version >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto found

python --version >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto found

for %%D in (
  "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
  "C:\Python313\python.exe"
  "C:\Python312\python.exe"
  "C:\Python311\python.exe"
) do if not defined PY if exist %%~D set "PY=%%~D"
if defined PY goto found

goto nopy

:found
echo Using Python: %PY%
echo Installing libraries... please wait a few minutes.
echo.
%PY% -m pip install -r requirements.txt
echo.
echo ==== DONE ====
echo Close this window, then double-click run_app.bat
pause
exit /b 0

:nopy
echo.
echo [ERROR] Python not found on this PC.
echo.
echo 1. Install Python:  https://www.python.org/downloads/
echo 2. On the FIRST install screen, check  "Add python.exe to PATH"
echo 3. Restart the PC, then run setup.bat again.
echo.
pause
exit /b 1
