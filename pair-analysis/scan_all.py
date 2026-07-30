#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
総当たりスキャン（バッチ）— しんぽこ設計の「700万通り」自動マッチング。

先行群 × 後続群 を両方向で総当たりし、連動率（同方向率）の高い順に並べてCSV出力する。
各ペアに 曜日別ベスト（月曜95% 等）と トレンド（前50→今90）も付ける。

    # オフライン確認（synthetic）: 米国リーダー × 日経225 を両方向
    python scan_all.py --top 40

    # 本番（yfinance）
    PRICE_PROVIDER=yahoo python scan_all.py \
        --leaders-file universe/us_leaders.txt \
        --followers-file universe/nikkei225.txt --min-coact 0.7 --out scan.csv

    # 日本株全銘柄（約4000）を後続にする（J-Quants・鍵必要）
    PRICE_PROVIDER=jquants python scan_all.py --jp-followers-all --top 100

注意:
  ペア数 = 先行数 × 後続数 × 2(両方向)。数千 × 数千 は非常に重い。
  まず「主要指数・米株（数十）× 日本株」から始めるのが現実的。
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

from src.analysis import align, linreg, pct_returns
from src.coactivity import coactivity
from src.data.provider import get_provider
from src.rank import _aligned_at_lag
from src.universe import PERIODS, load_universe_file, to_yahoo_symbol

_UNI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "universe")


def _load(paths: list[str]) -> tuple[list[str], dict[str, str]]:
    syms, names, seen = [], {}, set()
    for p in paths:
        s, nm = load_universe_file(p)
        for x in s:
            if x not in seen:
                seen.add(x)
                syms.append(x)
        names.update(nm)
    return syms, names


def scan_pair(ld, lp, fd, fp, max_lag: int, min_days: int):
    """先行(ld,lp) → 後続(fd,fp) を測り (連動率, 相関, lag, CoactStat) を返す。無効なら None。"""
    d, a, b = align(ld, lp, fd, fp)
    if len(d) < min_days:
        return None
    lr = pct_returns(a)   # leader returns
    fr = pct_returns(b)   # follower returns
    # 先行→後続なので lag>=0（先行が lag 日先に動く）。連動率が最大の lag を採用。
    best = None
    for lag in range(0, max_lag + 1):
        # leader が follower に lag 先行: x=lr[:-lag], y=fr[lag:]
        if lag == 0:
            x, y = lr, fr
        else:
            x, y = lr[:-lag], fr[lag:]
        if len(x) < min_days:
            continue
        r_co, n = _coact_rate(x, y)
        if best is None or r_co > best[0]:
            best = (r_co, lag, x, y)
    if best is None:
        return None
    r_co, lag, x, y = best
    _s, _i, corr = linreg(x, y)
    # 曜日別・トレンド用の日付（先行の各リターン日）
    ret_dates = d[1:]
    pd_ = ret_dates[:len(x)] if lag == 0 else ret_dates[:len(x)]
    co = coactivity(pd_, x, y)
    return r_co, corr, lag, co


def _coact_rate(x, y):
    from src.coactivity import same_dir_rate
    return same_dir_rate(x, y)


def run(leaders, followers, names, period_label, max_lag, min_days,
        min_coact, top, out_path, both_ways):
    yf_period = PERIODS.get(period_label, ("2y", 490))[0]
    provider = get_provider()

    universe = list(dict.fromkeys(leaders + followers))
    hist: dict[str, tuple[list[str], list[float]]] = {}
    for i, s in enumerate(universe):
        try:
            hist[s] = provider.get_close_history(s, yf_period)
        except Exception as e:  # noqa: BLE001
            print(f"  スキップ {s}: {e}", file=sys.stderr)
        if (i + 1) % 50 == 0:
            print(f"  取得 {i+1}/{len(universe)} ...", file=sys.stderr)

    pairs = []
    for L in leaders:
        if L not in hist:
            continue
        for F in followers:
            if F == L or F not in hist:
                continue
            res = scan_pair(*hist[L], *hist[F], max_lag, min_days)
            if res is None:
                continue
            r_co, corr, lag, co = res
            if r_co < min_coact:
                continue
            pairs.append({
                "先行": L, "先行名": names.get(L, ""),
                "後続": F, "後続名": names.get(F, ""),
                "連動率%": round(r_co * 100, 1),
                "先行日数": lag,
                "相関": round(corr, 2),
                "曜日ベスト": co.best_weekday_label(),
                "トレンド": co.trend_label(),
                "直近%": round(co.recent * 100, 1),
                "以前%": round(co.prior * 100, 1),
                "日数": co.n,
            })

    pairs.sort(key=lambda p: p["連動率%"], reverse=True)

    if out_path:
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(pairs[0].keys()) if pairs else
                               ["先行", "後続", "連動率%"])
            w.writeheader()
            w.writerows(pairs)
        print(f"→ {out_path} に {len(pairs)} 件を書き出しました。", file=sys.stderr)

    print(f"■ 総当たり結果  上位{top}（{period_label}・連動率>={min_coact*100:.0f}%・"
          f"先行群{len(leaders)}×後続群{len(followers)}）")
    print(f"  {'先行':>8} → {'後続':<9}{'連動率':>6} {'先行':>3} {'曜日ベスト':>10}  トレンド")
    for p in pairs[:top]:
        print(f"  {p['先行']:>8} → {p['後続']:<9}{p['連動率%']:>5}% "
              f"{p['先行日数']:>2}日 {p['曜日ベスト']:>10}  {p['トレンド']}")
    if not pairs:
        print("  （該当なし。--min-coact を下げるかユニバースを見直してください）")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="総当たりスキャン（連動率）")
    ap.add_argument("--leaders-file", action="append", default=None)
    ap.add_argument("--followers-file", action="append", default=None)
    ap.add_argument("--jp-followers-all", action="store_true",
                    help="日本株全銘柄を後続にする（PRICE_PROVIDER=jquants 必須）")
    ap.add_argument("--period", default="2年", choices=list(PERIODS))
    ap.add_argument("--max-lag", type=int, default=2, help="先行の最大日数（0..max）")
    ap.add_argument("--min-days", type=int, default=60)
    ap.add_argument("--min-coact", type=float, default=0.6, help="連動率の下限(例0.7=70%)")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--both-ways", action="store_true",
                    help="先行群↔後続群を入れ替えた向きも一緒にスキャン")
    ap.add_argument("--out", default="", help="結果CSVの出力パス")
    a = ap.parse_args(argv)

    lead_files = a.leaders_file or [os.path.join(_UNI, "us_leaders.txt")]
    leaders, lnames = _load(lead_files)

    if a.jp_followers_all:
        from src.data.jquants import list_jp_universe
        followers = list_jp_universe()
        fnames = {}
    else:
        foll_files = a.followers_file or [os.path.join(_UNI, "nikkei225.txt")]
        followers, fnames = _load(foll_files)

    names = {**lnames, **fnames}
    if a.both_ways:
        leaders2 = list(dict.fromkeys(leaders + followers))
        followers = leaders2
        leaders = leaders2

    leaders = [to_yahoo_symbol(s) for s in leaders]
    followers = [to_yahoo_symbol(s) for s in followers]
    return run(leaders, followers, names, a.period, a.max_lag, a.min_days,
               a.min_coact, a.top, a.out, a.both_ways)


if __name__ == "__main__":
    raise SystemExit(main())
