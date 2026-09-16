@echo off
chcp 65001 >nul
rem ============================================================
rem  株価急騰分析アプリ コマンド版
rem  銘柄コードを聞かれるので入力すると、決算ごとの業績と株価の反応を表示します。
rem ============================================================
cd /d "%~dp0jp-spike-analyzer"
if not exist ".venv\Scripts\python.exe" (
  echo 先に「アプリ起動.bat」を一度実行して、環境を作ってください。
  pause
  exit /b 1
)
set /p CODE=銘柄コード（例 7203）: 
".venv\Scripts\python.exe" analyze_earnings.py %CODE%
pause
