"""財務指標計算エンジン（仕様書 4.1 / 3章）。

`FinancialStatement` の生データ（1決算期分）から各種財務指標を算出する。
DB 非依存の純粋関数として実装し、pytest で正しさを検証する（受け入れ基準参照）。

設計方針:
- ゼロ除算や欠損値（None）が絡む指標は None を返す（「算出不能」を表す）。
- 単年計算に加え、前年比の「改善／悪化」フラグを付与できるようにする
  （Fスコアとトレンド表示で再利用する）。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

# 実効税率のデフォルト（仕様書 7章・用語）。ROIC 等で使用。0.30〜0.35。
# Park24 モデルは 0.35（純利益 = 営業利益 × 0.65）を採用するが、
# 指標計算のデフォルトは 0.30 とし、呼び出し側で上書き可能にする。
DEFAULT_EFFECTIVE_TAX_RATE = 0.30


@dataclass
class RawFinancials:
    """1企業・1決算期分の実績財務データ（仕様書 3章 FinancialStatement）。

    金額の単位は任意（円・百万円など）だが、比率計算のため全項目で統一すること。
    未取得の項目は None を許容する。
    """

    fiscal_period: str  # 決算期, 例 "2025-03"

    # 損益計算書
    revenue: Optional[float] = None            # 売上高
    cogs: Optional[float] = None               # 売上原価
    gross_profit: Optional[float] = None       # 売上総利益
    operating_income: Optional[float] = None   # 営業利益
    ordinary_income: Optional[float] = None    # 経常利益
    net_income: Optional[float] = None         # 純利益

    # キャッシュフロー計算書
    operating_cf: Optional[float] = None       # 営業CF
    investing_cf: Optional[float] = None       # 投資CF
    financing_cf: Optional[float] = None       # 財務CF

    # 貸借対照表
    total_assets: Optional[float] = None       # 総資産
    equity: Optional[float] = None             # 自己資本
    current_assets: Optional[float] = None     # 流動資産
    current_liabilities: Optional[float] = None  # 流動負債
    interest_bearing_debt: Optional[float] = None  # 有利子負債
    cash: Optional[float] = None               # 現預金
    short_term_securities: Optional[float] = None  # 短期有価証券

    # 運転資本
    inventory: Optional[float] = None          # 棚卸資産
    receivables: Optional[float] = None        # 売上債権
    payables: Optional[float] = None           # 仕入債務

    # 資本
    capital_stock: Optional[float] = None      # 資本金
    shares_outstanding: Optional[float] = None  # 発行済株式数

    # 配当
    total_dividends: Optional[float] = None    # 配当金総額
    dps: Optional[float] = None                # 1株当たり配当

    def __post_init__(self) -> None:
        # 売上総利益が未入力でも、売上高・売上原価から補完できる場合は補完する。
        if self.gross_profit is None and self.revenue is not None and self.cogs is not None:
            self.gross_profit = self.revenue - self.cogs


def _safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    """ゼロ除算・欠損を安全に扱う除算。算出不能なら None。"""
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    return numerator / denominator


def _turnover_days(balance: Optional[float], flow: Optional[float]) -> Optional[float]:
    """回転日数 = balance ÷ flow × 365（= 1 ÷ 回転率 × 365）。"""
    ratio = _safe_div(balance, flow)
    if ratio is None:
        return None
    return ratio * 365.0


@dataclass
class FinancialMetrics:
    """算出済みの財務指標（仕様書 4.1）。算出不能な指標は None。"""

    fiscal_period: str

    gross_margin: Optional[float] = None            # 粗利率
    operating_margin: Optional[float] = None        # 営業利益率
    net_margin: Optional[float] = None              # 純利益率（デュポン分解用）
    roe: Optional[float] = None                     # ROE = 純利益 ÷ 自己資本
    roa: Optional[float] = None                     # ROA = 経常利益 ÷ 総資産
    roic: Optional[float] = None                    # ROIC
    current_ratio: Optional[float] = None           # 流動比率
    equity_ratio: Optional[float] = None            # 自己資本比率
    net_interest_bearing_debt: Optional[float] = None  # 純有利子負債（マイナス=ネットキャッシュ）
    gross_de: Optional[float] = None                # グロスD/E
    net_de: Optional[float] = None                  # ネットD/E
    total_asset_turnover: Optional[float] = None    # 総資産回転率
    financial_leverage: Optional[float] = None      # 財務レバレッジ（総資産÷自己資本）
    ccc: Optional[float] = None                     # キャッシュ・コンバージョン・サイクル（日）
    inventory_days: Optional[float] = None          # 棚卸資産回転日数
    receivable_days: Optional[float] = None         # 売上債権回転日数
    payable_days: Optional[float] = None            # 仕入債務回転日数
    # 有利子負債比率（Fスコア項目6で使用）
    debt_to_assets: Optional[float] = None          # 有利子負債 ÷ 総資産
    # ROE デュポン分解（= 純利益率 × 総資産回転率 × 財務レバレッジ）
    roe_dupont: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


def compute_metrics(
    fs: RawFinancials,
    effective_tax_rate: float = DEFAULT_EFFECTIVE_TAX_RATE,
) -> FinancialMetrics:
    """1決算期分の財務指標をまとめて算出する（仕様書 4.1）。"""

    gross_margin = _safe_div(fs.gross_profit, fs.revenue)
    operating_margin = _safe_div(fs.operating_income, fs.revenue)
    net_margin = _safe_div(fs.net_income, fs.revenue)
    roe = _safe_div(fs.net_income, fs.equity)
    # ROA は経常利益ベース（仕様書 4.1）。ROE のレバレッジ水増しを避けるため主指標。
    roa = _safe_div(fs.ordinary_income, fs.total_assets)

    # ROIC = 営業利益 ×(1 − 実効税率) ÷（有利子負債 ＋ 自己資本）
    roic: Optional[float] = None
    if fs.operating_income is not None and fs.interest_bearing_debt is not None and fs.equity is not None:
        invested_capital = fs.interest_bearing_debt + fs.equity
        nopat = fs.operating_income * (1.0 - effective_tax_rate)
        roic = _safe_div(nopat, invested_capital)

    current_ratio = _safe_div(fs.current_assets, fs.current_liabilities)
    equity_ratio = _safe_div(fs.equity, fs.total_assets)

    # 純有利子負債 = 有利子負債 −（現預金 ＋ 短期有価証券）。マイナス＝ネットキャッシュ。
    net_ibd: Optional[float] = None
    if fs.interest_bearing_debt is not None:
        cash = fs.cash or 0.0
        sts = fs.short_term_securities or 0.0
        net_ibd = fs.interest_bearing_debt - (cash + sts)

    gross_de = _safe_div(fs.interest_bearing_debt, fs.equity)
    net_de = _safe_div(net_ibd, fs.equity)
    total_asset_turnover = _safe_div(fs.revenue, fs.total_assets)
    financial_leverage = _safe_div(fs.total_assets, fs.equity)
    debt_to_assets = _safe_div(fs.interest_bearing_debt, fs.total_assets)

    # CCC = 棚卸資産回転日数 ＋ 売上債権回転日数 − 仕入債務回転日数
    inventory_days = _turnover_days(fs.inventory, fs.cogs)
    receivable_days = _turnover_days(fs.receivables, fs.revenue)
    payable_days = _turnover_days(fs.payables, fs.cogs)
    ccc: Optional[float] = None
    if inventory_days is not None and receivable_days is not None and payable_days is not None:
        ccc = inventory_days + receivable_days - payable_days

    # ROE デュポン分解 = 純利益率 × 総資産回転率 × 財務レバレッジ
    roe_dupont: Optional[float] = None
    if net_margin is not None and total_asset_turnover is not None and financial_leverage is not None:
        roe_dupont = net_margin * total_asset_turnover * financial_leverage

    return FinancialMetrics(
        fiscal_period=fs.fiscal_period,
        gross_margin=gross_margin,
        operating_margin=operating_margin,
        net_margin=net_margin,
        roe=roe,
        roa=roa,
        roic=roic,
        current_ratio=current_ratio,
        equity_ratio=equity_ratio,
        net_interest_bearing_debt=net_ibd,
        gross_de=gross_de,
        net_de=net_de,
        total_asset_turnover=total_asset_turnover,
        financial_leverage=financial_leverage,
        ccc=ccc,
        inventory_days=inventory_days,
        receivable_days=receivable_days,
        payable_days=payable_days,
        debt_to_assets=debt_to_assets,
        roe_dupont=roe_dupont,
    )


@dataclass
class MetricChange:
    """指標の前年比。改善/悪化フラグ付き（仕様書 4.1）。"""

    metric: str
    latest: Optional[float]
    prior: Optional[float]
    delta: Optional[float]           # latest − prior
    improved: Optional[bool]         # True=改善, False=悪化, None=判定不能

    def to_dict(self) -> dict:
        return asdict(self)


# 値が「大きいほど良い」指標。ここに無い指標は「小さいほど良い」とみなす。
_HIGHER_IS_BETTER = {
    "gross_margin", "operating_margin", "net_margin", "roe", "roa", "roic",
    "current_ratio", "equity_ratio", "total_asset_turnover", "roe_dupont",
}
# 値が「小さいほど良い」指標。
_LOWER_IS_BETTER = {
    "net_interest_bearing_debt", "gross_de", "net_de", "debt_to_assets",
    "ccc", "inventory_days", "receivable_days", "payable_days",
    "financial_leverage",
}


def compute_change(metric: str, latest: Optional[float], prior: Optional[float]) -> MetricChange:
    """1指標の前年比を計算し、改善/悪化を判定する。"""
    delta: Optional[float] = None
    improved: Optional[bool] = None
    if latest is not None and prior is not None:
        delta = latest - prior
        if metric in _LOWER_IS_BETTER:
            improved = latest < prior
        else:
            # デフォルトは higher-is-better
            improved = latest > prior
    return MetricChange(metric=metric, latest=latest, prior=prior, delta=delta, improved=improved)


def compute_changes(latest: FinancialMetrics, prior: FinancialMetrics) -> dict[str, MetricChange]:
    """2期分の FinancialMetrics から、全指標の前年比を返す。"""
    changes: dict[str, MetricChange] = {}
    latest_d = latest.to_dict()
    prior_d = prior.to_dict()
    for key, value in latest_d.items():
        if key == "fiscal_period":
            continue
        changes[key] = compute_change(key, value, prior_d.get(key))
    return changes
