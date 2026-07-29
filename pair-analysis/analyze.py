#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自由ペア分析（CLI）— 先行→後続の連動をその場で1ペア測る。

使い方:
    # オフライン（synthetic データ・鍵不要）で動作確認
    python analyze.py TSM 6146

    # 本番（yfinance）
    PRICE_PROVIDER=yahoo python analyze.py TSM 6146 --period 2年 --threshold 0.03

    # JSON 出力（他ツール連携用）
    PRICE_PROVIDER=yahoo python analyze.py ^SOX 6857 --json
"""

from __future__ import annotations

import argparse
import json
import sys

from src.analysis import analyze_pair
from src.data.provider import get_provider
from src.universe import PERIODS, default_lag, to_yahoo_symbol


def run(leader_in: str, follower_in: str, period_label: str,
        threshold: float, lag: int | None, as_json: bool) -> int:
    leader = to_yahoo_symbol(leader_in)
    follower = to_yahoo_symbol(follower_in)
    yf_period, _n = PERIODS.get(period_label, ("2y", 490))
    if lag is None:
        lag = default_lag(leader)

    provider = get_provider()
    try:
        dl, pl = provider.get_close_history(leader, yf_period)
        df, pf = provider.get_close_history(follower, yf_period)
    except Exception as e:  # noqa: BLE001 - CLIなのでユーザ向けに要約
        print(f"エラー: {e}", file=sys.stderr)
        return 1

    res = analyze_pair(leader, follower, dl, pl, df, pf, lag=lag, threshold=threshold)

    if as_json:
        print(json.dumps({
            "leader": res.leader, "follower": res.follower, "lag": res.lag,
            "n_days": res.n_days, "beta": res.beta, "corr": res.corr,
            "thickness": res.thickness,
            "up": vars(res.up), "down": vars(res.down),
        }, ensure_ascii=False, indent=2))
        return 0

    thr_pct = threshold * 100
    print(f"■ {res.leader} → {res.follower}"
          f"（{period_label}・lag={res.lag}日・しきい値±{thr_pct:.0f}%）")
    print(f"  ベータ  : {res.beta*100:+.2f}%  （先行1%→後続の動き / 全{res.n_days}営業日）")
    print(f"  つながり: {res.thickness}（相関 r={res.corr:+.2f}）")
    u, d = res.up, res.down
    print(f"  ↑急騰時: {u.n:>3}回中 {u.follow_rate*100:5.1f}% が追随・平均{u.avg_move*100:+.2f}%")
    print(f"  ↓急落時: {d.n:>3}回中 {d.follow_rate*100:5.1f}% が追随・平均{d.avg_move*100:+.2f}%")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="自由ペア分析（先行→後続の連動）")
    ap.add_argument("leader", help="先行シンボル（例: TSM, ^SOX, 6857）")
    ap.add_argument("follower", help="後続シンボル（例: 6146）")
    ap.add_argument("--period", default="2年", choices=list(PERIODS), help="期間ラベル")
    ap.add_argument("--threshold", type=float, default=0.03, help="急変しきい値（例 0.03=±3%）")
    ap.add_argument("--lag", type=int, default=None, help="後続をずらす営業日数（既定=市場から自動）")
    ap.add_argument("--json", action="store_true", help="JSON で出力")
    a = ap.parse_args(argv)
    return run(a.leader, a.follower, a.period, a.threshold, a.lag, a.json)


if __name__ == "__main__":
    raise SystemExit(main())
