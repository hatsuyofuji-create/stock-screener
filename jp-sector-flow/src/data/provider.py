# -*- coding: utf-8 -*-
"""
データ提供元の共通インターフェース（DataProvider）。

方針:
  - app.py / update_daily.py は requests を直書きせず、必ずこの DataProvider 経由で
    データを取得する。
  - 提供元を差し替えられるよう、mock（鍵不要）と jquants（本番）を用意する。

各プロバイダは次の2つを返す:
  - get_turnover_history() -> pd.DataFrame
        index = 日付（昇順）, columns = 銘柄コード, values = 売買代金（円）
  - get_sector_map()       -> dict[str, str]
        銘柄コード -> セクター名
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

import pandas as pd


class DataProvider(ABC):
    """データ提供元の抽象基底クラス。"""

    name: str = "base"

    @abstractmethod
    def get_turnover_history(self) -> pd.DataFrame:
        """日付 × 銘柄コードの売買代金（円）テーブルを返す。"""
        raise NotImplementedError

    @abstractmethod
    def get_sector_map(self) -> dict[str, str]:
        """銘柄コード -> セクター名 の対応を返す。"""
        raise NotImplementedError


def get_provider(name: str | None = None) -> DataProvider:
    """
    環境変数 PROVIDER（または引数）に応じて DataProvider を生成するファクトリ。
    未指定なら mock を使う（鍵不要で必ず動く）。
    """
    name = (name or os.getenv("PROVIDER") or "mock").strip().lower()

    if name == "mock":
        from .mock import MockProvider
        return MockProvider()
    if name == "jquants":
        from .jquants import JQuantsProvider
        return JQuantsProvider()

    raise ValueError(f"未知の PROVIDER です: {name!r}（'mock' か 'jquants' を指定）")
