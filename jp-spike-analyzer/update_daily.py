# -*- coding: utf-8 -*-
"""
update_daily.py — 適時開示（TDnet 公式）の日次蓄積バッチ。

毎営業日、JPX TDnet の当日一覧（全銘柄）を読んで db/tdnet/YYYY-MM.csv に貯める。
公式は直近1か月しか見られないので、貯め続けることで過去の急騰日と突き合わせられるようになる。

使い方:
  python update_daily.py                 # 当日（土日はスキップ）
  python update_daily.py --days 30       # 直近30日ぶんをまとめて取り込む（初回向け）
  python update_daily.py --date 2026-09-10
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.data import tdnet  # noqa: E402


def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="TDnet 適時開示の日次蓄積")
    ap.add_argument("--date", help="取り込む日付 YYYY-MM-DD（省略時は今日）")
    ap.add_argument("--days", type=int, default=1, help="指定日から遡る日数（初回は 30 程度）")
    args = ap.parse_args()

    force = os.getenv("FORCE_RUN", "").strip().lower() in ("1", "true", "yes")
    base = date.fromisoformat(args.date) if args.date else date.today()
    days = [base - timedelta(days=i) for i in range(args.days)]
    days = [d for d in days if d.weekday() < 5 or force]
    if not days:
        print("土日のためスキップしました。（FORCE_RUN=true で強制実行できます）")
        return 0

    store = tdnet.TdnetStore()
    session = requests.Session()
    total = 0
    for d in sorted(days):
        try:
            df = tdnet.fetch_official_day(d, session=session)
        except Exception as e:  # noqa: BLE001
            print(f"{d}: 取得失敗 {str(e)[:150]}")
            continue
        added = store.upsert(df)
        total += added
        print(f"{d}: {len(df)} 件取得 / {added} 件追加")

    lo, hi = store.coverage()
    print(f"蓄積: {total} 件追加 / 公式カバー範囲 {lo.date() if lo is not None else '-'}〜{hi.date() if hi is not None else '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
