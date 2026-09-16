# -*- coding: utf-8 -*-
"""
株価・決算データ提供元の共通インターフェース（PriceProvider）。

方針（jp-sector-flow と同じ）:
  - analyze.py / app.py は requests を直書きせず、必ず Provider 経由で取得する。
  - 提供元は環境変数 PROVIDER（mock / jquants）で切り替える。

各プロバイダが返すもの:
  - get_daily_bars(code, start, end) -> pd.DataFrame
        index = 日付（昇順・DatetimeIndex）
        columns = open, high, low, close, volume, turnover（調整後があれば調整後）
  - get_statements(code) -> pd.DataFrame
        columns = disclosed_date, disclosed_time, doc_type, period, + 数値（あれば）
  - get_market_index(start, end) -> pd.Series
        index = 日付, values = TOPIX 終値（取れなければ空の Series）
  - get_company_name(code) -> str
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

import pandas as pd


class PriceProvider(ABC):
    name: str = "base"

    @abstractmethod
    def get_daily_bars(self, code: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def get_statements(self, code: str) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def get_market_index(self, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
        raise NotImplementedError

    @abstractmethod
    def get_company_name(self, code: str) -> str:
        raise NotImplementedError


def normalize_code(code: str) -> str:
    """'7203' / '72030' / ' 7203 ' などを 4桁（または英字入り4文字）の銘柄コードに揃える。"""
    c = str(code).strip().upper()
    if len(c) == 5 and c.endswith("0"):
        c = c[:-1]
    return c


def get_provider(name: str | None = None) -> PriceProvider:
    """環境変数 PROVIDER（または引数）に応じて PriceProvider を生成する。未指定なら mock。"""
    name = (name or os.getenv("PROVIDER") or "mock").strip().lower()
    if name == "mock":
        from .mock import MockProvider
        return MockProvider()
    if name == "jquants":
        from .jquants import JQuantsProvider
        return JQuantsProvider()
    raise ValueError(f"未知の PROVIDER です: {name!r}（'mock' か 'jquants' を指定）")


def is_mock() -> bool:
    return (os.getenv("PROVIDER") or "mock").strip().lower() == "mock"
