#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
連動ランキング（CLI）— 候補1銘柄と連動する銘柄をユニバースから探す。

使い方:
    # オフライン確認（synthetic・鍵不要）
    python find_peers.py 6146

    # 本番（yfinance）: ディスコと連動する相手を leaders_jp_us.txt から探す
    PRICE_PROVIDER=yahoo python find_peers.py 6146 \
        --universe-file universe/leaders_jp_us.txt --period 2年 --top 20

    # 「候補に対して先行している銘柄」だけ見る（先行指標探し）
    PRICE_PROVIDER=yahoo python find_peers.py 6146 --leaders-only --top 15

    # 同日連動（連れ高／連れ安）で並べたい場合
    PRICE_PROVIDER=yahoo python find_peers.py 6146 --mode same_day
"""

from __future__ import annotations

import argparse
import os
import sys

from src.data.provider import get_provider
from src.rank import rank_peers
from src.universe import PERIODS, load_universe_file, to_yahoo_symbol

_UNI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "universe")
# 既定は「米国リーダー＋日経225」の広いユニバース
DEFAULT_UNIVERSE = [os.path.join(_UNI_DIR, "us_leaders.txt"),
                    os.path.join(_UNI_DIR, "nikkei225.txt")]


def _merge_universe(paths: list[str]) -> tuple[list[str], dict[str, str]]:
    """複数のユニバースファイルを重複なしで結合する。"""
    symbols: list[str] = []
    names: dict[str, str] = {}
    seen: set[str] = set()
    for p in paths:
        syms, nm = load_universe_file(p)
        for s in syms:
            if s not in seen:
                seen.add(s)
                symbols.append(s)
        names.update(nm)
    return symbols, names


def run(target_in: str, universe_files: list[str], period_label: str,
        mode: str, top: int, leaders_only: bool) -> int:
    target = to_yahoo_symbol(target_in)
    yf_period, _n = PERIODS.get(period_label, ("2y", 490))

    symbols, names = _merge_universe(universe_files)
    provider = get_provider()

    try:
        td, tp = provider.get_close_history(target, yf_period)
    except Exception as e:  # noqa: BLE001
        print(f"エラー: 候補 {target} を取得できません: {e}", file=sys.stderr)
        return 1

    hist: dict[str, tuple[list[str], list[float]]] = {}
    for s in symbols:
        if s == target:
            continue
        try:
            hist[s] = provider.get_close_history(s, yf_period)
        except Exception as e:  # noqa: BLE001
            print(f"  スキップ {s}: {e}", file=sys.stderr)

    rows = rank_peers(target, td, tp, hist, names=names, mode=mode)
    if leaders_only:
        rows = [r for r in rows if r.best_lag > 0]

    tname = names.get(target, "")
    mode_label = "時間差（先行→後続）" if mode == "time_lag" else "同日連動"
    print(f"■ {target} {tname} と連動する銘柄  上位{top}"
          f"（{period_label}・{mode_label}）")
    print(f"  {'銘柄':<10}{'名前':<14}{'相関':>6}{'β':>7}  関係 / 時間差")
    for r in rows[:top]:
        nm = (r.name[:12] if r.name else "")
        print(f"  {r.symbol:<10}{nm:<14}{r.best_corr:+5.2f}{r.best_beta*100:+6.1f}%  "
              f"{r.relation}・{r.strength}・{r.lead_note}")
    if not rows:
        print("  （該当なし。ユニバースや期間を見直してください）")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="連動ランキング（候補×ユニバース）")
    ap.add_argument("target", help="候補銘柄（例: 6146, TSM, ^SOX）")
    ap.add_argument("--universe-file", action="append", default=None,
                    help="ユニバース定義ファイル（複数指定可。既定: 米国リーダー＋日経225）")
    ap.add_argument("--period", default="2年", choices=list(PERIODS))
    ap.add_argument("--mode", default="time_lag", choices=["time_lag", "same_day"],
                    help="time_lag=先行→後続重視 / same_day=同日連動")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--leaders-only", action="store_true",
                    help="候補に対して先行している銘柄だけ表示")
    a = ap.parse_args(argv)
    files = a.universe_file if a.universe_file else DEFAULT_UNIVERSE
    return run(a.target, files, a.period, a.mode, a.top, a.leaders_only)


if __name__ == "__main__":
    raise SystemExit(main())
