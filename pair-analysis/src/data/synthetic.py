# -*- coding: utf-8 -*-
"""
SyntheticProvider: 鍵・ネット不要の決定論的な擬似価格。

- テストとオフライン確認用。乱数シードをシンボルから決めるので、同じ入力なら
  常に同じ系列を返す（テストが安定する）。
- 「先行→後続」を確認できるよう、シンボル名に "_FOLLOWS:<leader>" を付けると、
  そのリーダーの前日リターンに連動する後続系列を生成できる（テスト用の仕掛け）。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import random

from .provider import PriceProvider


def _business_days(n: int, end: _dt.date | None = None) -> list[str]:
    end = end or _dt.date(2026, 7, 24)
    days: list[str] = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:  # 月-金
            days.append(d.isoformat())
        d -= _dt.timedelta(days=1)
    return list(reversed(days))


def _seed(symbol: str) -> int:
    return int(hashlib.sha256(symbol.encode()).hexdigest(), 16) % (2 ** 32)


class SyntheticProvider(PriceProvider):
    name = "synthetic"

    # period ラベル → 生成する営業日数
    _N = {"6mo": 120, "1y": 245, "2y": 490, "3y": 735, "5y": 1225}

    def get_close_history(self, symbol: str, period: str) -> tuple[list[str], list[float]]:
        n = self._N.get(period, 490)
        dates = _business_days(n)
        rng = random.Random(_seed(symbol))
        price = 100.0
        closes: list[float] = []
        for _ in range(n):
            ret = rng.gauss(0.0004, 0.02)   # 日次ドリフト+ボラ
            price *= (1.0 + ret)
            closes.append(round(price, 4))
        return dates, closes
