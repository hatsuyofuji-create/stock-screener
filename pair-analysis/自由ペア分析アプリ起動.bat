@echo off
rem NOTE: This launcher uses ASCII-only messages on purpose.
rem Japanese text inside a .bat gets mojibake on CP932 Windows and breaks parsing.
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Free Pair Analysis

echo ==========================================
echo    Free Pair Analysis - launcher
echo ==========================================
echo.

rem --- Find Python (prefer the py launcher, else python) ---
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [ERROR] Python not found.
    echo   Install Python from https://www.python.org/downloads/
    echo   and check "Add python.exe to PATH" during installation.
    echo.
    pause
    exit /b 1
)

rem --- First run only: create venv and install packages ---
if not exist ".venv\Scripts\python.exe" (
    echo [Setup] Creating virtual environment ...
    %PY% -m venv .venv
    if errorlevel 1 goto setup_error
    echo [Setup] Installing packages ^(this takes a few minutes^) ...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto setup_error
    echo [Setup] Done.
    echo.
)

rem --- Launch with live Yahoo Finance data ---
set "PRICE_PROVIDER=yahoo"
echo Your browser will open automatically.
echo To stop the app, press Ctrl+C in this black window.
echo.
".venv\Scripts\python.exe" -m streamlit run app.py

echo.
echo App closed.
pause
exit /b 0

:setup_error
echo.
echo [ERROR] Setup failed. Check your internet connection and try again.
echo   If it keeps failing, delete the ".venv" folder and run this file again.
pause
exit /b 1
