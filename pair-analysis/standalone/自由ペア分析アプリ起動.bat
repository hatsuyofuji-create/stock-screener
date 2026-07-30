@echo off
rem ASCII-only launcher.
rem Short path -> run right here.  Very long path -> relocate to a short work folder.
rem Broken/missing venv -> rebuild automatically. No manual folder cleanup needed.
chcp 65001 >nul
setlocal
title Free Pair Analysis
cd /d "%~dp0"

if not exist "app.py" (
    echo [ERROR] app.py was not found next to this launcher.
    echo   Keep app.py and this .bat together in one folder, then run again.
    echo.
    pause
    exit /b 1
)

call :strlen LEN "%CD%"
if %LEN% GEQ 90 goto relocate
goto run

:relocate
set "TARGET=%USERPROFILE%\pair-analysis"
if /I "%CD%\"=="%TARGET%\" goto run
echo This folder path is long ^(%LEN% chars^); using a short work folder instead:
echo   "%TARGET%"
if not exist "%TARGET%" mkdir "%TARGET%" 2>nul
if not exist "%TARGET%" (
    echo [ERROR] Could not create "%TARGET%".
    pause
    exit /b 1
)
copy /Y "app.py" "%TARGET%\app.py" >nul
copy /Y "%~f0" "%TARGET%\%~nx0" >nul
echo Launching from there ...
start "" "%TARGET%\%~nx0"
exit /b 0

:run
echo ==========================================
echo    Free Pair Analysis - launcher
echo ==========================================
echo Folder: "%CD%"
echo.

set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [ERROR] Python not found.
    echo   Install from https://www.python.org/downloads/
    echo   and check "Add python.exe to PATH" during installation.
    echo.
    pause
    exit /b 1
)

set "VPY=.venv\Scripts\python.exe"
set "REBUILD="
if not exist "%VPY%" set "REBUILD=1"
if exist "%VPY%" (
    "%VPY%" -c "import streamlit, pandas, yfinance" >nul 2>nul
    if errorlevel 1 set "REBUILD=1"
)
if defined REBUILD goto rebuild
goto launch

:rebuild
if exist ".venv" (
    echo [Setup] Rebuilding the environment ...
    rmdir /S /Q ".venv"
) else (
    echo [Setup] Creating the environment ...
)
%PY% -m venv .venv
if errorlevel 1 goto setup_error
"%VPY%" -m pip install --upgrade pip >nul
echo [Setup] Installing packages ^(this takes a few minutes the first time^) ...
"%VPY%" -m pip install streamlit pandas yfinance
if errorlevel 1 goto setup_error
echo [Setup] Done.
echo.

:launch
set "PRICE_PROVIDER=yahoo"
echo Your browser will open automatically.
echo To stop the app, press Ctrl+C in this black window.
echo.
"%VPY%" -m streamlit run app.py

echo.
echo App closed.
pause
exit /b 0

:setup_error
echo.
echo [ERROR] Setup failed. Check your internet connection, then run this file again.
echo   (It will rebuild automatically - you do not need to delete anything.)
pause
exit /b 1

:strlen
setlocal enabledelayedexpansion
set "s=%~2"
set "len=0"
for %%N in (4096 2048 1024 512 256 128 64 32 16 8 4 2 1) do (
    if "!s:~%%N,1!" neq "" ( set /a len+=%%N & set "s=!s:~%%N!" )
)
endlocal & set "%~1=%len%"
goto :eof
