# -*- coding: utf-8 -*-
"""
backfill_tdnet.py — 蓄積開始前の適時開示を、非公式 TDnet WebAPI で一度だけ埋める。

使い方:
  python backfill_tdnet.py 7203                      # 銘柄 7203 の過去分（既定 5年）
  python backfill_tdnet.py 7203 --years 3
  python backfill_tdnet.py --range 2026-06-01 2026-08-31   # 全銘柄・期間指定（件数が多い）

既に公式クロールで貯まっている日付は上書きしない（重複除去）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.data import tdnet, tdnet_backfill  # noqa: E402


def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="適時開示の過去分バックフィル")
    ap.add_argument("code", nargs="?", help="銘柄コード（例: 7203）")
    ap.add_argument("--years", type=float, default=5.0)
    ap.add_argument("--range", nargs=2, metavar=("FROM", "TO"), help="全銘柄・期間指定 YYYY-MM-DD")
    args = ap.parse_args()

    store = tdnet.TdnetStore()
    end = pd.Timestamp.today().normalize()
    if args.range:
        a, b = pd.Timestamp(args.range[0]), pd.Timestamp(args.range[1])
        df = tdnet_backfill.fetch_by_range(a, b)
    elif args.code:
        start = end - pd.DateOffset(years=args.years)
        lo, _ = store.coverage()
        if lo is not None:
            end = min(end, lo - pd.Timedelta(days=1))  # 公式で貯まっている分より前だけ
        df = tdnet_backfill.fetch_by_code(args.code, start, end)
    else:
        ap.error("銘柄コードか --range を指定してください")
        return 2
    added = store.upsert(df)
    print(f"取得 {len(df)} 件 / 追加 {added} 件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
