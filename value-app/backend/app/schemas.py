"""API スキーマ（Pydantic v2）。仕様書 3章のデータモデルに対応。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class FinancialStatementIn(BaseModel):
    """財務データ入力（手入力／CSV）。"""

    fiscal_period: str
    source: Optional[str] = "manual"

    revenue: Optional[float] = None
    cogs: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    ordinary_income: Optional[float] = None
    net_income: Optional[float] = None

    operating_cf: Optional[float] = None
    investing_cf: Optional[float] = None
    financing_cf: Optional[float] = None

    total_assets: Optional[float] = None
    equity: Optional[float] = None
    current_assets: Optional[float] = None
    current_liabilities: Optional[float] = None
    interest_bearing_debt: Optional[float] = None
    cash: Optional[float] = None
    short_term_securities: Optional[float] = None

    inventory: Optional[float] = None
    receivables: Optional[float] = None
    payables: Optional[float] = None

    capital_stock: Optional[float] = None
    shares_outstanding: Optional[float] = None

    total_dividends: Optional[float] = None
    dps: Optional[float] = None


class FinancialStatementOut(FinancialStatementIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_code: str


class CompanyIn(BaseModel):
    code: str
    name: str
    sector: Optional[str] = None
    market_cap: Optional[float] = None
    growth_type: Optional[str] = None
    moat_tags: Optional[list[str]] = None
    qualitative_note: Optional[str] = None


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    sector: Optional[str] = None
    market_cap: Optional[float] = None
    growth_type: Optional[str] = None
    moat_tags: Optional[str] = None
    qualitative_note: Optional[str] = None
    is_cyclical: bool = False
