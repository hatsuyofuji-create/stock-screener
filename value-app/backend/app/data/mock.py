"""MockProvider：鍵不要の決定論的サンプルデータ（テスト・デモ用）。仕様書 4.9。"""

from __future__ import annotations

from typing import Optional

from .provider import DataProvider


class MockProvider(DataProvider):
    name = "mock"

    def fetch_company(self, code: str) -> Optional[dict]:
        return {"name": f"モック銘柄{code}", "sector": "機械", "market_cap": 80_000_000_000}

    def fetch_statements(self, code: str) -> list[dict]:
        """3期分の決定論データ（改善トレンド）。実データ取得の置き換え検証用。"""
        base = [
            dict(fiscal_period="2023-03", revenue=900, cogs=560, operating_income=80,
                 ordinary_income=75, net_income=48, operating_cf=70, investing_cf=-25,
                 financing_cf=-20, total_assets=950, equity=460, current_assets=380,
                 current_liabilities=190, interest_bearing_debt=210, cash=90,
                 short_term_securities=0, inventory=95, receivables=140, payables=115,
                 capital_stock=100, shares_outstanding=1000, total_dividends=15, dps=15),
            dict(fiscal_period="2024-03", revenue=1000, cogs=600, operating_income=100,
                 ordinary_income=90, net_income=60, operating_cf=80, investing_cf=-30,
                 financing_cf=-20, total_assets=1000, equity=500, current_assets=400,
                 current_liabilities=200, interest_bearing_debt=200, cash=100,
                 short_term_securities=0, inventory=100, receivables=150, payables=120,
                 capital_stock=100, shares_outstanding=1000, total_dividends=20, dps=20),
            dict(fiscal_period="2025-03", revenue=1200, cogs=680, operating_income=150,
                 ordinary_income=140, net_income=95, operating_cf=160, investing_cf=-40,
                 financing_cf=-30, total_assets=1100, equity=600, current_assets=500,
                 current_liabilities=220, interest_bearing_debt=180, cash=150,
                 short_term_securities=0, inventory=110, receivables=160, payables=130,
                 capital_stock=100, shares_outstanding=1000, total_dividends=30, dps=30),
        ]
        for row in base:
            row["source"] = "mock"
        return base

    def fetch_market(self, code: str) -> Optional[dict]:
        # BPS(最新) = 600/1000 = 0.6。株価 0.5 → PBR ≈ 0.83（低PBR）
        return {"price": 0.5, "price_3y_ago": 0.7, "as_of": "2025-07-01"}
