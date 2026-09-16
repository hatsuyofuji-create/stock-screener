@echo off
chcp 65001 >nul
rem ============================================================
rem  株価急騰分析アプリ 更新
rem  GitHub から最新のコードを取り込み、必要な部品を入れ直します。
rem ============================================================
cd /d "%~dp0"
echo 最新のコードを取り込んでいます...
git pull
if errorlevel 1 (
  echo 取り込みに失敗しました。ネットワークか git の設定を確認してください。
  pause
  exit /b 1
)
cd /d "%~dp0jp-spike-analyzer"
if exist ".venv\Scripts\python.exe" (
  echo 部品を確認しています...
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)
echo.
echo 更新が終わりました。この窓は閉じて構いません。
pause
