# -*- coding: utf-8 -*-
"""
analyze.py — 銘柄コードを指定して急騰日と「その時何が起きていたか」を出す（CLI）。

使い方:
  python analyze.py 7203                 # mock（鍵不要）
  PROVIDER=jquants python analyze.py 7203 --years 5
  python analyze.py 7203 --no-news       # ニュース取得を省く
結果は画面に表示し、db/analysis/<code>.json にも保存する（app.py でも読める）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config import SpikeConfig  # noqa: E402
from src import pipeline  # noqa: E402

OUT_DIR = ROOT / "db" / "analysis"


def _fmt(v, suffix="%"):
    return "—" if v is None else f"{v:+.1f}{suffix}"


def print_report(res: dict) -> None:
    print(f"\n=== {res['name']}（{res['code']}） {res['start']}〜{res['end']} / 急騰 {len(res['spikes'])} 件 ===")
    for ev in res["spikes"]:
        vol = "—" if ev["vol_ratio"] is None else f"{ev['vol_ratio']:.1f}倍"
        print(f"\n■ {ev['date']}  前日比 {ev['pct']:+.1f}%  寄付 {_fmt(ev['gap_pct'])}  出来高 {vol}  "
              f"TOPIX {_fmt(ev['topix_pct'])}  5日後 {_fmt(ev['fwd_5'])}  20日後 {_fmt(ev['fwd_20'])}")
        print(f"   要因タグ: {' / '.join(ev['tags']) or '—'}")
        for s in ev["statements"]:
            print(f"   [{s['kind']} {s['rel']}] {s['date']} {s['time']} {s['period']}  → {s['label']}")
            for line in s["details"]:
                print(f"       ・{line}")
        for x in ev["disclosures"]:
            print(f"   [開示 {x['rel']}] {x['date']} {x['time']} 〔{x['tag']}〕{x['title']}")
        for x in ev["edinet"]:
            print(f"   [EDINET {x['rel']}] {x['date']} {x['description']} ({x['filer']})")
        for x in ev["news"][:12]:
            print(f"   [ニュース {x['rel']}] {x['date']} {x['title']} — {x['publisher']}")
        if len(ev["news"]) > 12:
            print(f"   （ほか {len(ev['news']) - 12} 件は db/analysis の JSON に保存）")


def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="急騰日の要因分析")
    ap.add_argument("code", help="銘柄コード（例: 7203）")
    ap.add_argument("--years", type=float, default=None, help="遡る年数（既定 5・Light の上限）")
    ap.add_argument("--name", help="ニュース検索に使う会社名（未指定なら J-Quants から取得）")
    ap.add_argument("--no-news", action="store_true", help="ニュース取得を省く")
    ap.add_argument("--no-edinet", action="store_true", help="EDINET 照合を省く")
    ap.add_argument("--pct", type=float, help="急騰のしきい値（前日終値比 %%・既定 8）")
    args = ap.parse_args()

    cfg = SpikeConfig.from_env()
    if args.pct is not None:
        cfg = SpikeConfig(pct=args.pct, years=cfg.years)

    res = pipeline.analyze(args.code, args.years, cfg=cfg, with_news=not args.no_news,
                           with_edinet=not args.no_edinet, name=args.name)
    print_report(res)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {k: v for k, v in res.items() if not k.startswith("_")}
    path = OUT_DIR / f"{res['code']}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n保存: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
