# -*- coding: utf-8 -*-
"""
価格データ提供元の共通インターフェース（PriceProvider）。

方針（jp-sector-flow の DataProvider と同じ思想）:
  - analyze.py / scan.py / app.py は yfinance を直書きせず、必ずこの
    PriceProvider 経由で終値を取得する。
  - 提供元は環境変数 PRICE_PROVIDER（yahoo / synthetic）で差し替え。
    synthetic は鍵・ネット不要で必ず動く（テスト・オフライン確認用）。

契約:
  get_close_history(symbol, period) -> (dates, closes)
      dates  = 昇順の 'YYYY-MM-DD' 文字列リスト
      closes = 対応する終値（float）リスト
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod


class PriceProvider(ABC):
    name: str = "base"

    @abstractmethod
    def get_close_history(self, symbol: str, period: str) -> tuple[list[str], list[float]]:
        """symbol の終値履歴を (dates, closes) で返す。"""
        raise NotImplementedError


def get_provider(name: str | None = None) -> PriceProvider:
    """
    環境変数 PRICE_PROVIDER（または引数）に応じてプロバイダを生成する。
    未指定なら synthetic（鍵不要で必ず動く）。
    """
    name = (name or os.getenv("PRICE_PROVIDER") or "synthetic").strip().lower()
    if name in ("synthetic", "mock"):
        from .synthetic import SyntheticProvider
        return SyntheticProvider()
    if name in ("yahoo", "yfinance", "yf"):
        from .yahoo import YahooProvider
        return YahooProvider()
    raise ValueError(f"未知の PRICE_PROVIDER です: {name!r}（'synthetic' か 'yahoo'）")
