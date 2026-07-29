@echo off
rem ASCII-only launcher (Japanese text in a .bat breaks on CP932 Windows).
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Free Pair Analysis

echo ==========================================
echo    Free Pair Analysis - launcher
echo ==========================================
echo.
echo Folder: "%CD%"

rem --- The single app file must sit next to this launcher ---
if not exist "app.py" (
    echo.
    echo [ERROR] app.py not found in this folder.
    echo   Keep app.py and this .bat together in the SAME folder.
    echo.
    pause
    exit /b 1
)

rem --- Warn if the folder path is very long (Windows ~260 char limit) ---
call :strlen PATHLEN "%CD%"
if %PATHLEN% GEQ 100 (
    echo.
    echo [WARNING] This folder path is very long ^(%PATHLEN% chars^).
    echo   If setup fails, move this folder to a short path like  C:\pair-analysis
    echo.
    pause
)
echo.

rem --- Find Python ---
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

rem --- First run only: create venv and install packages by name ---
if not exist ".venv\Scripts\python.exe" (
    echo [Setup] Creating virtual environment ...
    %PY% -m venv .venv
    if errorlevel 1 goto setup_error
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    echo [Setup] Installing packages ^(this takes a few minutes^) ...
    ".venv\Scripts\python.exe" -m pip install streamlit pandas yfinance
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
echo [ERROR] Setup failed.
echo   - Check your internet connection.
echo   - If the path is long, move this folder to  C:\pair-analysis
echo   - Delete the ".venv" folder here, then run this file again.
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
