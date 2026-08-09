@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem --- Python を自動で探す（.venv → py → python の順） ---
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"

if not defined PY (
  echo.
  echo [エラー] Python が見つかりませんでした。先に setup.bat を実行するか、
  echo Python をインストールしてください（Add python.exe to PATH にチェック）。
  echo.
  pause
  exit /b 1
)

echo アプリを起動します...
echo ブラウザが開かない場合は http://localhost:8502 を開いてください。
%PY% -m streamlit run tanshin_collector.py --server.port 8502
pause
