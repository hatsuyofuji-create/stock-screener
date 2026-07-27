"""サービス層：DB モデル ⇄ 計算エンジンの橋渡し。"""

from __future__ import annotations

from typing import Optional

from .models import FinancialStatement, Company, MarketData
from .engines.financials import RawFinancials, compute_metrics
from .engines.fscore import compute_fscore
from .engines.screening import ScreenSnapshot

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


def build_snapshot(
    company: Company,
    market: Optional[MarketData] = None,
    effective_tax_rate: float = 0.30,
) -> ScreenSnapshot:
    """企業の財務＋市場データからスクリーニング用スナップショットを組み立てる。

    市場データ（株価・PBR・利回り）が直接与えられていればそれを使い、
    無ければ最新実績の BPS/EPS/DPS と株価から導出する。
    """
    latest, prior = latest_and_prior(company.statements)
    snap = ScreenSnapshot(code=company.code, name=company.name or "")
    if latest is None:
        return snap

    m = compute_metrics(to_raw(latest), effective_tax_rate=effective_tax_rate)
    snap.roe = m.roe
    snap.roic = m.roic
    snap.equity_ratio = m.equity_ratio
    snap.net_interest_bearing_debt = m.net_interest_bearing_debt

    # FCF = 営業CF + 投資CF
    if latest.operating_cf is not None and latest.investing_cf is not None:
        snap.fcf = latest.operating_cf + latest.investing_cf

    shares = latest.shares_outstanding
    if shares and latest.equity is not None:
        snap.bps = latest.equity / shares
    eps = latest.net_income / shares if shares and latest.net_income is not None else None

    price = market.price if market else None
    # PBR
    if market and market.pbr is not None:
        snap.pbr = market.pbr
    elif price is not None and snap.bps:
        snap.pbr = price / snap.bps
    # PER
    if market and market.per is not None:
        snap.per = market.per
    elif price is not None and eps:
        snap.per = price / eps
    # 配当利回り
    if market and market.dividend_yield is not None:
        snap.dividend_yield = market.dividend_yield
    elif price and latest.dps is not None:
        snap.dividend_yield = latest.dps / price
    # 時価総額（会社に登録があれば優先）
    if company.market_cap is not None:
        snap.market_cap = company.market_cap
    elif price is not None and shares:
        snap.market_cap = price * shares
    # 株価3年変化率
    if market and market.price is not None and market.price_3y_ago:
        snap.price_change_3y = (market.price - market.price_3y_ago) / market.price_3y_ago

    # Fスコア（2期以上あれば）
    if prior is not None:
        snap.fscore = compute_fscore(
            to_raw(latest), to_raw(prior), effective_tax_rate=effective_tax_rate
        ).total

    return snap


def build_all_snapshots(db, effective_tax_rate: float = 0.30) -> list[ScreenSnapshot]:
    """全企業のスナップショットを組み立てる。"""
    companies = db.query(Company).all()
    snaps = []
    for c in companies:
        market = db.get(MarketData, c.code)
        snaps.append(build_snapshot(c, market, effective_tax_rate))
    return snaps
