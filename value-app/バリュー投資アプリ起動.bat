@echo off
chcp 65001 >nul
setlocal
title バリュー投資アプリ（上原メソッド）

rem このバッチのある場所（value-app）へ移動
cd /d "%~dp0"

echo ============================================
echo   バリュー投資アプリ（上原メソッド）
echo ============================================
echo.

rem ---- Python の確認（python / py の順で探す）----
set "PY=python"
where python >nul 2>nul
if errorlevel 1 (
  set "PY=py"
  where py >nul 2>nul
  if errorlevel 1 (
    echo [エラー] Python が見つかりません。
    echo         https://www.python.org/ からインストールし、PATH を通してください。
    echo.
    pause
    exit /b 1
  )
)

rem ---- Node.js / npm の確認 ----
where npm >nul 2>nul
if errorlevel 1 (
  echo [エラー] Node.js が見つかりません。
  echo         https://nodejs.org/ からインストールしてください（推奨 LTS 版）。
  echo.
  pause
  exit /b 1
)

rem ---- 初回セットアップ：バックエンド（Python 仮想環境＋依存）----
if not exist "backend\.venv" (
  echo [初回セットアップ] Python 仮想環境を作成しています...
  %PY% -m venv backend\.venv
  echo [初回セットアップ] バックエンドの依存をインストールしています（数分かかります）...
  backend\.venv\Scripts\python.exe -m pip install --upgrade pip
  backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
  echo.
)

rem ---- 初回セットアップ：フロントエンド（npm install）----
if not exist "frontend\node_modules" (
  echo [初回セットアップ] フロントエンドの依存をインストールしています（数分かかります）...
  pushd frontend
  call npm install
  popd
  echo.
)

rem ---- データ提供元：mock（鍵不要のサンプル）----
set "PROVIDER=mock"

echo バックエンドを起動しています...  http://127.0.0.1:8000
start "value-app backend" /D "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"

echo フロントエンドを起動しています... http://localhost:5173
start "value-app frontend" /D "%~dp0frontend" cmd /k "npm run dev"

echo.
echo 起動中です。ブラウザが自動で開くまで少しお待ちください...
timeout /t 9 /nobreak >nul
start "" http://localhost:5173

echo.
echo --------------------------------------------
echo  ブラウザ： http://localhost:5173
echo  開かない場合は上記 URL を手入力してください。
echo  最初は画面右上の「サンプル取込（mock）」で銘柄を投入できます。
echo.
echo  終了するには、開いた2つの黒いウィンドウ
echo （backend / frontend）を閉じてください。
echo --------------------------------------------
echo.
pause
endlocal
