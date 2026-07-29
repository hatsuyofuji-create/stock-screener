#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
総当たりスキャン — 先行×後続の全ペアを測り、連動の強いものを上位に出す。

しんぽこさんの「総当たり700万通り」の構想版。ユニバース（銘柄リスト）を渡すと、
全ての順序付きペア（先行→後続）について beta / 相関 / 追随率を計算し、並べる。

「筋が通ったもの」を上位に:
    スコア = |相関| ×（同じ経済テーマなら 1.5 倍・econ.THEMES 参照）
    → 銅→住友鉱山、半導体→半導体装置 のような意味の通るペアが上がりやすい。

使い方:
    # オフライン確認（synthetic）
    python scan.py --universe TSM,NVDA,MU,6146,6857,5713 --top 10

    # 本番（yfinance）＋ファイルからユニバース読み込み（1行1シンボル）
    PRICE_PROVIDER=yahoo python scan.py --universe-file tickers.txt --period 半年 --top 30

注意:
    ペア数は N×(N-1) で急増する（700万通り≒先行約2600×後続2600）。
    本番の大ユニバースは取得に時間がかかるため、まず小さめで試すこと。
"""

from __future__ import annotations

import argparse
import sys

from src.analysis import analyze_pair
from src.data.provider import get_provider
from src.econ import same_theme
from src.universe import PERIODS, default_lag, to_yahoo_symbol

THEME_BONUS = 1.5   # 同一テーマのペアに掛ける加点


def load_universe(args) -> list[str]:
    syms: list[str] = []
    if args.universe:
        syms += [s for s in args.universe.split(",") if s.strip()]
    if args.universe_file:
        with open(args.universe_file, encoding="utf-8") as f:
            syms += [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    # 正規化 + 重複除去（順序維持）
    seen: dict[str, None] = {}
    for s in syms:
        seen.setdefault(to_yahoo_symbol(s), None)
    return list(seen)


def run(universe: list[str], period_label: str, threshold: float, top: int) -> int:
    if len(universe) < 2:
        print("エラー: ユニバースは2銘柄以上必要です。", file=sys.stderr)
        return 1
    yf_period, _n = PERIODS.get(period_label, ("2y", 490))
    provider = get_provider()

    # 先に全銘柄の終値を1回ずつ取得（ペアごとの再取得を避ける）
    hist: dict[str, tuple[list[str], list[float]]] = {}
    for s in universe:
        try:
            hist[s] = provider.get_close_history(s, yf_period)
        except Exception as e:  # noqa: BLE001
            print(f"  スキップ {s}: {e}", file=sys.stderr)

    rows = []
    for leader in hist:
        lag = default_lag(leader)
        dl, pl = hist[leader]
        for follower in hist:
            if follower == leader:
                continue
            df, pf = hist[follower]
            res = analyze_pair(leader, follower, dl, pl, df, pf,
                               lag=lag, threshold=threshold)
            if res.n_days == 0:
                continue
            bonus = THEME_BONUS if same_theme(leader, follower) else 1.0
            score = abs(res.corr) * bonus
            rows.append((score, res, bonus > 1.0))

    rows.sort(key=lambda r: r[0], reverse=True)

    print(f"■ 総当たりスキャン結果  上位{top}（{period_label}・しきい値±{threshold*100:.0f}%）")
    print(f"  対象 {len(hist)} 銘柄 / {len(rows)} ペア  ※★=同一経済テーマ")
    print(f"  {'先行':>8} → {'後続':<8} {'β':>7} {'相関':>6} {'太さ':>4}  ↓急落時追随")
    for score, res, themed in rows[:top]:
        star = "★" if themed else " "
        d = res.down
        print(f"{star} {res.leader:>8} → {res.follower:<8} "
              f"{res.beta*100:+6.2f}% {res.corr:+5.2f} {res.thickness:>4}  "
              f"{d.n:>3}回 {d.follow_rate*100:5.1f}% 平均{d.avg_move*100:+.2f}%")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="総当たりペアスキャン")
    ap.add_argument("--universe", default="", help="カンマ区切りのシンボル")
    ap.add_argument("--universe-file", default="", help="1行1シンボルのファイル")
    ap.add_argument("--period", default="2年", choices=list(PERIODS))
    ap.add_argument("--threshold", type=float, default=0.03)
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args(argv)
    return run(load_universe(a), a.period, a.threshold, a.top)


if __name__ == "__main__":
    raise SystemExit(main())
