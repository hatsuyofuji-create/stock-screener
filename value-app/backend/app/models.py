"""DB モデル（仕様書 3章）。企業 × 決算期 × 指標の3次元でデータを持つ。

トレンド（前年比改善など）を扱うため、FinancialStatement は最低3期を保持する想定。
派生指標（ROE, Fスコア, 適正株価 等）は保存せず計算で求める（必要ならキャッシュ）。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import String, Float, Integer, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# 成長タイプ（仕様書 3章・11章）
GROWTH_TYPES = ("安定成長", "シクリカル成長", "シクリカル", "業績低迷", "新領域開拓")
# モート（競争優位性）タグ（仕様書 3章・10章）
MOAT_TAGS = ("スイッチングコスト", "コスト競争力", "ブランド", "ネットワーク効果", "特許規制")


class Company(Base):
    __tablename__ = "companies"

    code: Mapped[str] = mapped_column(String, primary_key=True)  # 証券コード
    name: Mapped[str] = mapped_column(String, nullable=False)
    sector: Mapped[Optional[str]] = mapped_column(String, nullable=True)      # 業種
    market_cap: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 時価総額
    growth_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # モートタグはカンマ区切りで保持（初期実装。将来は正規化可）。
    moat_tags: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    qualitative_note: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    statements: Mapped[list["FinancialStatement"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    forecasts: Mapped[list["Forecast"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    holdings: Mapped[list["Holding"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )

    @property
    def is_cyclical(self) -> bool:
        """シクリカル銘柄フラグ（仕様書 4.4：PER の高低を反転解釈する対象）。"""
        return self.growth_type in ("シクリカル成長", "シクリカル")


class FinancialStatement(Base):
    """実績財務データ（EDINET/TDnet 由来）。仕様書 3章。"""

    __tablename__ = "financial_statements"
    __table_args__ = (
        UniqueConstraint("company_code", "fiscal_period", name="uq_fs_company_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_code: Mapped[str] = mapped_column(ForeignKey("companies.code"), nullable=False)
    fiscal_period: Mapped[str] = mapped_column(String, nullable=False)  # 例 "2025-03"
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # edinet / tdnet / manual

    # 損益計算書
    revenue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cogs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gross_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    operating_income: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ordinary_income: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_income: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # キャッシュフロー
    operating_cf: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    investing_cf: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    financing_cf: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # 貸借対照表
    total_assets: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    equity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_assets: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_liabilities: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    interest_bearing_debt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cash: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    short_term_securities: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # 運転資本
    inventory: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    receivables: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    payables: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # 資本
    capital_stock: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    shares_outstanding: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # 配当
    total_dividends: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    company: Mapped["Company"] = relationship(back_populates="statements")


class Forecast(Base):
    """予想データ（四季報 / ユーザーExcel / コンセンサス）。仕様書 3章・4.6。"""

    __tablename__ = "forecasts"
    __table_args__ = (
        UniqueConstraint(
            "company_code", "fiscal_period", "source", "scenario",
            name="uq_forecast_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_code: Mapped[str] = mapped_column(ForeignKey("companies.code"), nullable=False)
    fiscal_period: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # user_excel / shikiho / consensus
    scenario: Mapped[str] = mapped_column(String, default="base")  # base / negative

    revenue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)          # 予想売上高
    operating_income: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 予想営業利益
    operating_margin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 予想営業利益率
    net_income: Mapped[Optional[float]] = mapped_column(Float, nullable=True)        # 予想純利益
    eps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)              # 予想EPS
    bps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)              # 予想BPS
    dps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)              # 予想DPS
    one_time_items: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 一時損益（減損等）

    company: Mapped["Company"] = relationship(back_populates="forecasts")


class Holding(Base):
    """保有銘柄（仕様書 3章・4.8）。"""

    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_code: Mapped[str] = mapped_column(ForeignKey("companies.code"), nullable=False)
    buy_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    shares: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    buy_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # ISO 日付文字列
    confidence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 自信度 1-5
    thesis: Mapped[Optional[str]] = mapped_column(String, nullable=True)       # 投資アイデア

    company: Mapped["Company"] = relationship(back_populates="holdings")


class MappingProfile(Base):
    """予想Excel のマッピング設定（仕様書 4.6）。銘柄・様式ごとに保存し再利用する。"""

    __tablename__ = "mapping_profiles"
    __table_args__ = (
        UniqueConstraint("company_code", "format_name", name="uq_mapping_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    format_name: Mapped[str] = mapped_column(String, nullable=False)  # 例 "park24_annual"
    # {"eps": {"sheet": "Sheet1", "cell": "C5"}, ...}
    mapping: Mapped[dict] = mapped_column(JSON, nullable=False)
