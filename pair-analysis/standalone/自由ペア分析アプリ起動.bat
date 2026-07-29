@echo off
rem ASCII-only launcher. Self-installs to a short path and self-heals the venv,
rem so the user never has to empty folders or copy files by hand.
chcp 65001 >nul
setlocal
title Free Pair Analysis

rem Target = a short, always-writable path in the user's profile.
set "TARGET=%USERPROFILE%\pair-analysis"

rem ---- Self-install: if not already running from TARGET, copy there & relaunch ----
if /I not "%~dp0"=="%TARGET%\" (
    if not exist "%~dp0app.py" (
        echo [ERROR] app.py was not found next to this launcher.
        echo   Keep app.py and this .bat together in one folder, then run again.
        echo.
        pause
        exit /b 1
    )
    echo Installing the app to a short path:
    echo   "%TARGET%"
    if not exist "%TARGET%" mkdir "%TARGET%" 2>nul
    if not exist "%TARGET%" (
        echo [ERROR] Could not create "%TARGET%".
        pause
        exit /b 1
    )
    copy /Y "%~dp0app.py" "%TARGET%\app.py" >nul
    copy /Y "%~f0" "%TARGET%\%~nx0" >nul
    echo Done. Launching from there ...
    start "" "%TARGET%\%~nx0"
    exit /b 0
)

cd /d "%TARGET%"
echo ==========================================
echo    Free Pair Analysis - launcher
echo ==========================================
echo Folder: "%CD%"
echo.

rem ---- Find Python ----
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

rem ---- Ensure a HEALTHY environment (rebuild automatically if broken) ----
set "VPY=.venv\Scripts\python.exe"
set "REBUILD="
if not exist "%VPY%" set "REBUILD=1"
if exist "%VPY%" (
    "%VPY%" -c "import streamlit, pandas, yfinance" >nul 2>nul
    if errorlevel 1 set "REBUILD=1"
)
if defined REBUILD (
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
)

rem ---- Launch with live Yahoo Finance data ----
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
