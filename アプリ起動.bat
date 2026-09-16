@echo off
chcp 65001 >nul
rem ============================================================
rem  株価急騰分析アプリ 起動
rem  ダブルクリックすると画面版（Streamlit）が立ち上がり、ブラウザが開きます。
rem  止めるときは、この黒い窓で Ctrl+C を押すか、窓を閉じてください。
rem ============================================================
cd /d "%~dp0jp-spike-analyzer"

if not exist ".venv\Scripts\python.exe" (
  echo 初回セットアップ: Python 環境を作成しています（数分かかります）...
  python -m venv .venv
  if errorlevel 1 (
    echo Python が見つかりません。https://www.python.org/downloads/ からインストールしてください。
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

if not exist ".env" (
  copy .env.example .env >nul
  echo 設定ファイル .env を作りました。メモ帳が開くので J-Quants の APIキーを記入して保存してください。
  notepad .env
)

echo 画面版を起動します。ブラウザが自動で開きます（開かない場合は http://localhost:8501 ）。
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless false --browser.gatherUsageStats false
pause
