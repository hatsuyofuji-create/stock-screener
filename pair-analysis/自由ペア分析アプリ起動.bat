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
echo Folder: "%CD%"

rem --- Sanity check: the app files must sit next to this launcher ---
if not exist "app.py" (
    echo.
    echo [ERROR] app.py was not found in this folder.
    echo   This launcher must be in the SAME folder as:
    echo     app.py , requirements.txt , the "src" folder , the "universe" folder
    echo   Move this .bat into that folder ^(or move those files next to it^),
    echo   then run again.
    echo.
    pause
    exit /b 1
)

rem --- Warn if the folder path is very long (Windows ~260 char limit) ---
call :strlen PATHLEN "%CD%"
if %PATHLEN% GEQ 100 (
    echo.
    echo [WARNING] This folder path is very long ^(%PATHLEN% chars^).
    echo   Windows may FAIL to create the Python environment on long paths.
    echo   Recommended: move this folder to a short path such as  C:\pair-analysis
    echo.
    pause
)
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
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    echo [Setup] Installing packages ^(this takes a few minutes^) ...
    if exist "requirements.txt" (
        ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    ) else (
        echo   requirements.txt not found - installing by name instead ...
        ".venv\Scripts\python.exe" -m pip install yfinance pandas streamlit
    )
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

rem --- helper: compute string length of %~2 into variable %~1 ---
:strlen
setlocal enabledelayedexpansion
set "s=%~2"
set "len=0"
for %%N in (4096 2048 1024 512 256 128 64 32 16 8 4 2 1) do (
    if "!s:~%%N,1!" neq "" ( set /a len+=%%N & set "s=!s:~%%N!" )
)
endlocal & set "%~1=%len%"
goto :eof
