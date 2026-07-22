#!/usr/bin/env bash
# ============================================================
# cron / launchd から呼ぶための起動ラッパー。
# 仮想環境の python を絶対パスで使い、.env を読み込んで更新する。
# ログは logs/update.log に追記。
# ============================================================
set -euo pipefail

# このスクリプトが置かれているフォルダ = プロジェクトルート
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

mkdir -p logs
PROVIDER="${PROVIDER:-jquants}" "$DIR/.venv/bin/python" update_daily.py >> logs/update.log 2>&1
