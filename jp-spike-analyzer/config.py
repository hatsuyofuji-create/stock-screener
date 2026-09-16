# -*- coding: utf-8 -*-
"""
config.py — 急騰の定義と、照合する情報の「窓」の設定。

数字を変えたいときはここか .env（SPIKE_PCT など）を書き換える。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name, "").strip()
    try:
        return float(v) if v else default
    except ValueError:
        return default


@dataclass(frozen=True)
class SpikeConfig:
    """急騰判定のしきい値。"""

    # 急騰の定義: 前日終値 → 翌営業日終値 の変化率（%）がこれ以上
    pct: float = 8.0
    # 出来高倍率（表示用）の分母: 直近N日平均（当日は含めない）
    vol_window: int = 20
    # 遡る年数の初期値（チャートの見やすさ優先。J-Quants Light は最大5年）
    years: float = 3.0
    # 急騰後の追随を見るための保有日数
    forward_days: tuple[int, ...] = (5, 20)

    @classmethod
    def from_env(cls) -> "SpikeConfig":
        return cls(
            pct=_env_float("SPIKE_PCT", cls.pct),
            years=_env_float("SPIKE_YEARS", cls.years),
        )


# 急騰日を 0 として、何営業日前〜後の情報を並べるか
TDNET_WINDOW = (-1, 1)      # 適時開示: 前日〜翌日（前日引け後の開示が当日の急騰に効く）
EDINET_WINDOW = (-1, 5)     # EDINET: 大量保有報告書などは事後に出るので後ろを広めに
NEWS_WINDOW = (-2, 1)       # ニュース見出し
STATEMENT_WINDOW = (-1, 0)  # 決算発表（J-Quants）: 前日引け後 or 当日

# 「地合い」と判定する TOPIX の同日騰落（%）
MARKET_MOVE_PCT = 2.0
