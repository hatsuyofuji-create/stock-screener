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


# ---------- Phase 2: 適正株価・シナリオ（4.3） ----------

class ScenarioIn(BaseModel):
    """Park24 型シナリオ1本分の入力（仕様書 4.3 STEP1）。"""

    scenario: str = "base"  # base / negative
    revenue: Optional[float] = None
    operating_margin: Optional[float] = None
    payout_ratio: Optional[float] = None
    dps: Optional[float] = None
    one_time_items: float = 0.0
    effective_tax_rate: float = 0.35
    shares_outstanding: Optional[float] = None
    prior_bps: Optional[float] = None
    base_net_income: Optional[float] = None
    base_eps: Optional[float] = None


class FairMultiples(BaseModel):
    """妥当倍率（本質的価値の閾値）。手動上書き可。"""

    fair_per: Optional[float] = None
    fair_pbr: Optional[float] = None
    fair_yield: Optional[float] = None  # 妥当配当利回り（例 0.03）


class ValuationIn(BaseModel):
    """適正株価・安全域・リスクリワードの一括計算入力（仕様書 4.3）。"""

    current_price: Optional[float] = None
    multiples: FairMultiples = FairMultiples()
    base: ScenarioIn
    negative: Optional[ScenarioIn] = None
    # 予想を Forecast テーブルへ保存するか（銘柄コードは URL パスで指定）
    save: bool = False
    fiscal_period: Optional[str] = None
    source: str = "user_excel"


# ---------- Phase 3: 予想Excel 取り込み（4.6） ----------

class CellRef(BaseModel):
    sheet: Optional[str] = None
    cell: str


class MappingProfileIn(BaseModel):
    """マッピング設定の保存。"""

    format_name: str
    company_code: Optional[str] = None
    mapping: dict[str, CellRef]


class ExtractIn(BaseModel):
    """確定マッピングに基づく抽出＆Forecast保存の入力。

    file_id は /api/excel/preview が返す一時ファイル ID。
    """

    file_id: str
    mapping: dict[str, CellRef]
    fiscal_period: Optional[str] = None
    scenario: str = "base"
    source: str = "user_excel"
    save: bool = False
    save_profile_as: Optional[str] = None  # 指定時、マッピングを名前付きで保存
