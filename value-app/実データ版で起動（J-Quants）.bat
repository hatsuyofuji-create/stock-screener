@echo off
chcp 65001 >nul
setlocal
title バリュー投資アプリ（実データ／J-Quants）

cd /d "%~dp0"

echo ============================================
echo   バリュー投資アプリ（実データ版 / J-Quants）
echo ============================================
echo.

rem ---- Python の確認 ----
set "PY=python"
where python >nul 2>nul
if errorlevel 1 (
  set "PY=py"
  where py >nul 2>nul
  if errorlevel 1 (
    echo [エラー] Python が見つかりません。https://www.python.org/ からインストールしてください。
    pause
    exit /b 1
  )
)

rem ---- npm の確認 ----
where npm >nul 2>nul
if errorlevel 1 (
  echo [エラー] Node.js が見つかりません。https://nodejs.org/ からインストールしてください。
  pause
  exit /b 1
)

rem ---- 初回セットアップ ----
if not exist "backend\.venv" (
  echo [初回セットアップ] Python 仮想環境を作成しています...
  %PY% -m venv backend\.venv
  echo [初回セットアップ] バックエンドの依存をインストールしています...
  backend\.venv\Scripts\python.exe -m pip install --upgrade pip
  backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
)
if not exist "frontend\node_modules" (
  echo [初回セットアップ] フロントエンドの依存をインストールしています...
  pushd frontend
  call npm install
  popd
)

rem ---- J-Quants の APIキー（未設定なら入力を促す）----
if "%JQUANTS_API_KEY%"=="" (
  echo J-Quants の APIキー（ダッシュボードで発行）を入力してください。
  set /p JQUANTS_API_KEY=APIキー:
)
if "%JQUANTS_API_KEY%"=="" (
  echo [中止] APIキーが未入力です。鍵なしで試すには「バリュー投資アプリ起動.bat」を使ってください。
  pause
  exit /b 1
)

set "PROVIDER=jquants"

echo バックエンドを起動しています（実データ）... http://127.0.0.1:8000
start "value-app backend (jquants)" /D "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"

echo フロントエンドを起動しています... http://localhost:5173
start "value-app frontend" /D "%~dp0frontend" cmd /k "npm run dev"

echo.
echo 起動中です。ブラウザが開くまでお待ちください...
timeout /t 9 /nobreak >nul
start "" http://localhost:5173

echo.
echo --------------------------------------------
echo  実データ取込は、銘柄コードを指定して
echo  POST /api/companies/銘柄コード/ingest?provider=jquants
echo  （http://127.0.0.1:8000/docs から実行できます）
echo.
echo  終了は開いた2つのウィンドウを閉じてください。
echo --------------------------------------------
echo.
pause
endlocal
