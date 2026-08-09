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
echo Starting app... If the browser does not open, go to http://localhost:8502
%PY% -m streamlit run tanshin_collector.py --server.port 8502
pause
exit /b 0

:nopy
echo.
echo [ERROR] Python not found. Run setup.bat first, or install Python.
echo https://www.python.org/downloads/  (check "Add python.exe to PATH")
echo.
pause
exit /b 1
