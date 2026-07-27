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


# ---------- Phase 4: スクリーニング・マトリクス（4.5 / 4.7） ----------

class MarketDataIn(BaseModel):
    price: Optional[float] = None
    price_3y_ago: Optional[float] = None
    as_of: Optional[str] = None
    per: Optional[float] = None
    pbr: Optional[float] = None
    dividend_yield: Optional[float] = None


class ThresholdIn(BaseModel):
    """閾値フィルターの条件（None/False は OFF）。"""

    dividend_yield_min: Optional[float] = None
    equity_ratio_min: Optional[float] = None
    net_cash_required: bool = False
    fcf_positive: bool = False
    roe_min: Optional[float] = None
    market_cap_max: Optional[float] = None
    price_change_3y_negative: bool = False
    fscore_min: Optional[int] = None


class ScreenSettingIn(BaseModel):
    name: str
    mode: str  # threshold / magic
    params: dict


# ---------- Phase 6: 景気局面・ポートフォリオ（4.4 / 4.8） ----------

class BusinessCycleIn(BaseModel):
    phase: str
    is_cyclical: bool = False


class HoldingIn(BaseModel):
    company_code: str
    buy_price: Optional[float] = None
    shares: Optional[float] = None
    buy_date: Optional[str] = None
    confidence: Optional[int] = None
    thesis: Optional[str] = None


class HoldingOut(HoldingIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class TakeProfitIn(BaseModel):
    current_price: Optional[float] = None    # 未指定なら市場データを使用
    fair_price: Optional[float] = None
    overvalued_factor: float = 1.3
    at_cycle_peak: bool = False
    reached_hist_avg_valuation: bool = False
    recovery_target_price: Optional[float] = None


class StopLossIn(BaseModel):
    current_price: Optional[float] = None
    scenario_broken: bool = False
    value_trap_persist: bool = False
    pbr: Optional[float] = None       # 未指定なら snapshot から
    fscore: Optional[int] = None      # 未指定なら snapshot から


class PositionSizeIn(BaseModel):
    confidence: Optional[int] = None
    upside: Optional[float] = None
    max_weight: float = 0.20


class ReevaluateIn(BaseModel):
    margin_of_safety: Optional[float] = None
    fscore: Optional[int] = None


# ---------- Phase 5: データ自動取得（4.9） ----------

class IngestIn(BaseModel):
    codes: list[str]
    provider: Optional[str] = None  # mock / jquants（未指定は環境変数 PROVIDER）
