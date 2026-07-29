@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title 自由ペア分析アプリ

echo ============================================
echo    自由ペア分析アプリ を起動します
echo ============================================
echo.

rem --- Python を探す（py ランチャ優先、無ければ python） ---
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
    echo [エラー] Python が見つかりませんでした。
    echo   https://www.python.org/downloads/ からインストールしてください。
    echo   インストール時に「Add python.exe to PATH」に必ずチェックを入れてください。
    echo.
    pause
    exit /b 1
)

rem --- 初回だけ仮想環境を作成し、パッケージを入れる ---
if not exist ".venv\Scripts\python.exe" (
    echo [初回セットアップ] 仮想環境を作成しています...
    %PY% -m venv .venv
    if errorlevel 1 goto :setup_error
    echo [初回セットアップ] 必要なパッケージを入れています（数分かかることがあります）...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :setup_error
    echo [初回セットアップ] 完了しました。
    echo.
)

rem --- 本番データ（yfinance）で起動 ---
set "PRICE_PROVIDER=yahoo"

echo ブラウザが自動で開きます。
echo 終了するときは、この黒い画面で Ctrl+C を押してください。
echo.
".venv\Scripts\python.exe" -m streamlit run app.py

echo.
echo アプリを終了しました。
pause
exit /b 0

:setup_error
echo.
echo [エラー] セットアップに失敗しました。
echo   ネット接続を確認して、もう一度このファイルをダブルクリックしてください。
echo.
pause
exit /b 1
