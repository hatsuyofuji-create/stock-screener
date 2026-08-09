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
  echo [エラー] Python が見つかりませんでした。
  echo   1) https://www.python.org/downloads/ から Python をインストール
  echo   2) インストール画面で「Add python.exe to PATH」に必ずチェック
  echo   3) パソコンを再起動してから、もう一度この setup.bat を実行
  echo.
  pause
  exit /b 1
)

echo 使用する Python: %PY%
echo 必要なライブラリをインストールします（初回だけ・数分かかります）...
echo.
%PY% -m pip install -r requirements.txt
echo.
echo ============================================================
echo  完了しました。
echo  このウィンドウを閉じて、run_app.bat をダブルクリックしてください。
echo ============================================================
pause
