# -*- coding: utf-8 -*-
"""
analyze_earnings.py — 銘柄コードを指定して、決算ごとの業績と株価の反応を出す（CLI）。

使い方:
  python analyze_earnings.py 7203                 # mock（鍵不要）
  PROVIDER=jquants python analyze_earnings.py 7203 --years 3
  python analyze_earnings.py 7203 --no-dividend   # 配当予想修正を除く
結果は画面に表示し、db/analysis/<code>_earnings.json にも保存する。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src import pipeline  # noqa: E402

OUT_DIR = ROOT / "db" / "analysis"


def _p(v):
    return "—" if v is None else f"{v:+.1f}%"


def print_report(res: dict) -> None:
    print(f"\n=== {res['name']}（{res['code']}） {res['start']}〜{res['end']} / 決算イベント {len(res['events'])} 件 ===")
    print("\n【傾向】評価ごとの翌営業日の反応")
    print(f"{'評価':<12}{'回数':>4}{'上昇':>4}{'翌日平均':>9}{'寄付平均':>9}{'5日後':>8}{'20日後':>8}{'対TOPIX':>9}")
    for r in res["summary"]:
        print(f"{r['label']:<12}{r['n']:>4}{r['n_up']:>4}{_p(r['avg_react']):>9}{_p(r['avg_gap']):>9}"
              f"{_p(r['avg_fwd_5']):>8}{_p(r['avg_fwd_20']):>8}{_p(r['avg_relative']):>9}")
    print("\n【決算ごと】新しい順")
    for e in res["events"]:
        vol = "—" if e["vol_ratio"] is None else f"{e['vol_ratio']:.1f}倍"
        kind = f"{e['kind']} {e['period']}".strip()
        print(f"\n■ {e['disclosed_date']} {e['disclosed_time']} 発表　{kind}　→ {e['label']}")
        print(f"   反応日 {e['reaction_date']}: 翌日 {_p(e['react_pct'])}  寄付 {_p(e['gap_pct'])}  高値 {_p(e['high_pct'])}  "
              f"安値 {_p(e['low_pct'])}  出来高 {vol}  5日後 {_p(e['fwd_5'])}  20日後 {_p(e['fwd_20'])}  TOPIX {_p(e['topix_pct'])}")
        for line in e["details"]:
            print(f"   ・{line}")


def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="決算と株価の反応")
    ap.add_argument("code", help="銘柄コード（例: 7203）")
    ap.add_argument("--years", type=float, default=None, help="遡る年数（既定 3・Light の上限 5）")
    ap.add_argument("--name", help="表示に使う会社名（未指定なら J-Quants から取得）")
    ap.add_argument("--no-dividend", action="store_true", help="配当予想修正を対象から外す")
    args = ap.parse_args()

    res = pipeline.analyze_earnings(args.code, args.years, include_dividend=not args.no_dividend, name=args.name)
    print_report(res)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {k: v for k, v in res.items() if not k.startswith("_")}
    path = OUT_DIR / f"{res['code']}_earnings.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n保存: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
