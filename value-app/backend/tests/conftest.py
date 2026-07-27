"""テスト共通のサンプルデータ（仕様書 受け入れ基準）。"""

import os
import sys

import pytest

# backend ディレクトリを import パスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.engines.financials import RawFinancials  # noqa: E402


@pytest.fixture
def prior_fs() -> RawFinancials:
    """前期（2024-03）の健全な財務データ。"""
    return RawFinancials(
        fiscal_period="2024-03",
        revenue=1000, cogs=600, gross_profit=400,
        operating_income=100, ordinary_income=90, net_income=60,
        operating_cf=80, investing_cf=-30, financing_cf=-20,
        total_assets=1000, equity=500, current_assets=400, current_liabilities=200,
        interest_bearing_debt=200, cash=100, short_term_securities=0,
        inventory=100, receivables=150, payables=120,
        capital_stock=100, shares_outstanding=1000,
        total_dividends=20, dps=20,
    )


@pytest.fixture
def latest_fs() -> RawFinancials:
    """最新期（2025-03）。全項目で前期比改善（Fスコア満点を狙う）。"""
    return RawFinancials(
        fiscal_period="2025-03",
        revenue=1200, cogs=680, gross_profit=520,
        operating_income=150, ordinary_income=140, net_income=95,
        operating_cf=160, investing_cf=-40, financing_cf=-30,
        total_assets=1100, equity=600, current_assets=500, current_liabilities=220,
        interest_bearing_debt=180, cash=150, short_term_securities=0,
        inventory=110, receivables=160, payables=130,
        capital_stock=100, shares_outstanding=1000,
        total_dividends=30, dps=30,
    )
