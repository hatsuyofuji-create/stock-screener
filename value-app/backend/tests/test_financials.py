"""財務指標エンジンのテスト（仕様書 4.1）。手計算値と一致することを検証。"""

import math

from app.engines.financials import (
    RawFinancials, compute_metrics, compute_change, DEFAULT_EFFECTIVE_TAX_RATE,
)


def approx(a, b, tol=1e-6):
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


def test_basic_ratios(latest_fs):
    m = compute_metrics(latest_fs)
    assert approx(m.gross_margin, 520 / 1200)
    assert approx(m.operating_margin, 150 / 1200)
    assert approx(m.net_margin, 95 / 1200)
    assert approx(m.roe, 95 / 600)
    # ROA は経常利益ベース（仕様書 4.1）
    assert approx(m.roa, 140 / 1100)
    assert approx(m.current_ratio, 500 / 220)
    assert approx(m.equity_ratio, 600 / 1100)
    assert approx(m.total_asset_turnover, 1200 / 1100)
    assert approx(m.financial_leverage, 1100 / 600)
    assert approx(m.debt_to_assets, 180 / 1100)


def test_roic(latest_fs):
    m = compute_metrics(latest_fs, effective_tax_rate=0.30)
    expected = 150 * (1 - 0.30) / (180 + 600)
    assert approx(m.roic, expected)
    # 実効税率のデフォルトが 0.30 であること
    m_default = compute_metrics(latest_fs)
    assert DEFAULT_EFFECTIVE_TAX_RATE == 0.30
    assert approx(m_default.roic, expected)


def test_net_interest_bearing_debt_and_de(latest_fs):
    m = compute_metrics(latest_fs)
    # 純有利子負債 = 180 - (150 + 0) = 30
    assert approx(m.net_interest_bearing_debt, 30)
    assert approx(m.gross_de, 180 / 600)
    assert approx(m.net_de, 30 / 600)


def test_net_cash_is_negative():
    """現預金が有利子負債を上回ればネットキャッシュ（マイナス）。"""
    fs = RawFinancials(
        fiscal_period="2025-03", interest_bearing_debt=100, cash=250,
        short_term_securities=50, equity=500,
    )
    m = compute_metrics(fs)
    assert m.net_interest_bearing_debt == 100 - (250 + 50)
    assert m.net_interest_bearing_debt < 0  # ネットキャッシュ


def test_ccc(latest_fs):
    m = compute_metrics(latest_fs)
    inv_days = 110 / 680 * 365
    recv_days = 160 / 1200 * 365
    pay_days = 130 / 680 * 365
    assert approx(m.inventory_days, inv_days)
    assert approx(m.receivable_days, recv_days)
    assert approx(m.payable_days, pay_days)
    assert approx(m.ccc, inv_days + recv_days - pay_days)


def test_dupont_equals_roe(latest_fs):
    """デュポン分解の積が ROE に一致すること（純利益率×総資産回転率×財務レバレッジ）。"""
    m = compute_metrics(latest_fs)
    assert approx(m.roe_dupont, m.roe)


def test_gross_profit_autofill():
    """売上総利益が未入力でも売上高−売上原価で補完される。"""
    fs = RawFinancials(fiscal_period="2025-03", revenue=1000, cogs=600)
    assert fs.gross_profit == 400
    m = compute_metrics(fs)
    assert approx(m.gross_margin, 0.4)


def test_division_by_zero_returns_none():
    fs = RawFinancials(fiscal_period="2025-03", revenue=0, net_income=10, equity=0, total_assets=0)
    m = compute_metrics(fs)
    assert m.operating_margin is None
    assert m.roe is None
    assert m.roa is None
    assert m.total_asset_turnover is None


def test_missing_values_return_none():
    fs = RawFinancials(fiscal_period="2025-03")
    m = compute_metrics(fs)
    assert m.roe is None
    assert m.roic is None
    assert m.ccc is None


def test_compute_change_higher_is_better():
    c = compute_change("roe", 0.15, 0.10)
    assert c.improved is True
    assert approx(c.delta, 0.05)
    c2 = compute_change("roe", 0.08, 0.10)
    assert c2.improved is False


def test_compute_change_lower_is_better():
    # 有利子負債比率は下がるほど改善
    c = compute_change("debt_to_assets", 0.15, 0.20)
    assert c.improved is True
    # CCC も短いほど良い
    c2 = compute_change("ccc", 40, 30)
    assert c2.improved is False


def test_compute_change_none_when_missing():
    c = compute_change("roe", None, 0.10)
    assert c.improved is None
    assert c.delta is None
