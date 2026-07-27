"""データ取得の抽象契約とファクトリ（仕様書 4.9）。

- app / router に requests を直書きしない。必ず DataProvider 経由で取得する。
- 提供元は環境変数 PROVIDER（mock / jquants）で切り替える。
- プロバイダは「集める」だけに徹し、計算・保存は上位層（ingest / engines）が行う。

各メソッドの戻り値は DB モデルの列名に合わせた dict（そのまま upsert できる形）:
  - fetch_company(code) -> {name, sector, market_cap} | None
  - fetch_statements(code) -> [{fiscal_period, source, revenue, ...}, ...]
  - fetch_market(code) -> {price, price_3y_ago, as_of, per, pbr, dividend_yield} | None
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional


class DataProvider(ABC):
    name: str = "base"

    @abstractmethod
    def fetch_company(self, code: str) -> Optional[dict]:
        ...

    @abstractmethod
    def fetch_statements(self, code: str) -> list[dict]:
        ...

    @abstractmethod
    def fetch_market(self, code: str) -> Optional[dict]:
        ...


def get_provider(name: Optional[str] = None) -> DataProvider:
    """環境変数 PROVIDER もしくは引数でプロバイダを選ぶ（デフォルト mock）。"""
    name = (name or os.getenv("PROVIDER") or "mock").strip().lower()
    if name == "jquants":
        from .jquants import JQuantsProvider
        return JQuantsProvider()
    if name == "mock":
        from .mock import MockProvider
        return MockProvider()
    raise ValueError(f"未知の PROVIDER: {name}（mock / jquants）")
