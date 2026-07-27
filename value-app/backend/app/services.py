"""サービス層：DB モデル ⇄ 計算エンジンの橋渡し。"""

from __future__ import annotations

from typing import Optional

from .models import FinancialStatement
from .engines.financials import RawFinancials

# RawFinancials に写す財務項目（fiscal_period 以外）。
_FS_FIELDS = (
    "revenue", "cogs", "gross_profit", "operating_income", "ordinary_income",
    "net_income", "operating_cf", "investing_cf", "financing_cf",
    "total_assets", "equity", "current_assets", "current_liabilities",
    "interest_bearing_debt", "cash", "short_term_securities",
    "inventory", "receivables", "payables",
    "capital_stock", "shares_outstanding", "total_dividends", "dps",
)


def to_raw(fs: FinancialStatement) -> RawFinancials:
    """DB の FinancialStatement を計算エンジン用 RawFinancials へ変換する。"""
    kwargs = {f: getattr(fs, f) for f in _FS_FIELDS}
    return RawFinancials(fiscal_period=fs.fiscal_period, **kwargs)


def sorted_statements(statements: list[FinancialStatement]) -> list[FinancialStatement]:
    """決算期の昇順（古い→新しい）に並べ替える。"""
    return sorted(statements, key=lambda s: s.fiscal_period)


def latest_and_prior(
    statements: list[FinancialStatement],
) -> tuple[Optional[FinancialStatement], Optional[FinancialStatement]]:
    """最新期と前期を返す（Fスコア用）。不足時は None。"""
    ordered = sorted_statements(statements)
    latest = ordered[-1] if len(ordered) >= 1 else None
    prior = ordered[-2] if len(ordered) >= 2 else None
    return latest, prior
