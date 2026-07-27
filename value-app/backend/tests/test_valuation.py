"""適正株価・安全域＋Park24型シナリオ計算のテスト（仕様書 4.3 / 受け入れ基準）。

手計算値と一致すること（EPS・BPS・ROE・base/negative の適正株価・安全域・
リスクリワード）を検証する。
"""

import math

from app.engines.valuation import (
    ScenarioInputs, project_scenario, PARK24_TAX_RATE,
    fair_value_per, fair_value_pbr, fair_value_dividend,
    margin_of_safety, risk_reward, suggest_multiple,
)


def approx(a, b, tol=1e-9):
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=tol)


# ---- Park24 型シナリオ ----

def test_park24_tax_rate():
    assert PARK24_TAX_RATE == 0.35


def test_base_scenario_projection():
    """売上1000・営業利益率15%・配当性向30%・前期BPS5.0・株式数100 の芋づる式計算。"""
    inp = ScenarioInputs(
        scenario="base", revenue=1000, operating_margin=0.15,
        payout_ratio=0.30, one_time_items=0.0,
        shares_outstanding=100, prior_bps=5.0,
    )
    r = project_scenario(inp)
    # 営業利益 = 1000 × 0.15 = 150
    assert approx(r.operating_income, 150)
    # 純利益 = 150 × 0.65 = 97.5
    assert approx(r.net_income, 97.5)
    # EPS = 97.5 / 100 = 0.975
    assert approx(r.eps, 0.975)
    # DPS = 0.975 × 0.30 = 0.2925
    assert approx(r.dps, 0.2925)
    # BPS = 5.0 + 0.975 − 0.2925 = 5.6825
    assert approx(r.bps, 5.6825)
    # ROE = EPS / 平均BPS = 0.975 / ((5.0+5.6825)/2)
    assert approx(r.roe, 0.975 / ((5.0 + 5.6825) / 2))


def test_negative_scenario_impairment():
    """negative シナリオ：一時損益（減損50）を純利益から差し引く。"""
    inp = ScenarioInputs(
        scenario="negative", revenue=1000, operating_margin=0.15,
        payout_ratio=0.30, one_time_items=50.0,
        shares_outstanding=100, prior_bps=5.0,
    )
    r = project_scenario(inp)
    # 純利益 = 97.5 − 50 = 47.5
    assert approx(r.net_income, 47.5)
    assert approx(r.eps, 0.475)
    assert approx(r.dps, 0.1425)
    assert approx(r.bps, 5.0 + 0.475 - 0.1425)


def test_dps_direct_input_overrides_payout():
    inp = ScenarioInputs(
        revenue=1000, operating_margin=0.15, dps=0.5,
        payout_ratio=0.30, shares_outstanding=100, prior_bps=5.0,
    )
    r = project_scenario(inp)
    assert approx(r.dps, 0.5)  # 直接入力が優先


def test_eps_proportional_scale_without_shares():
    """発行済株式数が無い場合、基準期からの比例スケールで EPS を求める。"""
    inp = ScenarioInputs(
        revenue=1000, operating_margin=0.15,
        base_net_income=65.0, base_eps=1.0,  # 基準期: 純利益65 → EPS1.0
    )
    r = project_scenario(inp)
    # 純利益 97.5 → EPS = 1.0 × (97.5 / 65.0) = 1.5
    assert approx(r.eps, 1.5)


# ---- 適正株価・安全域 ----

def test_fair_value_per():
    fv = fair_value_per(eps=0.975, fair_per=15, current_price=10)
    assert approx(fv.fair_price, 14.625)
    assert approx(fv.margin_of_safety, (14.625 - 10) / 14.625)


def test_fair_value_pbr():
    fv = fair_value_pbr(bps=5.6825, fair_pbr=1.5, current_price=10)
    assert approx(fv.fair_price, 8.52375)


def test_fair_value_dividend():
    fv = fair_value_dividend(dps=0.2925, fair_yield=0.03, current_price=10)
    assert approx(fv.fair_price, 0.2925 / 0.03)


def test_margin_of_safety_negative_when_overvalued():
    """現在株価 > 適正株価 なら安全域はマイナス（割高）。"""
    mos = margin_of_safety(fair_price=10, current_price=15)
    assert mos < 0
    assert approx(mos, (10 - 15) / 10)


def test_margin_of_safety_none_on_missing():
    assert margin_of_safety(None, 10) is None
    assert margin_of_safety(0, 10) is None


# ---- リスクリワード ----

def test_risk_reward():
    """base適正14.625・negative適正7.125・現在株価10。"""
    rr = risk_reward(base_fair=14.625, negative_fair=7.125, current_price=10)
    assert approx(rr.upside, (14.625 - 10) / 10)     # +0.4625
    assert approx(rr.downside, (7.125 - 10) / 10)    # −0.2875
    assert approx(rr.risk_reward, 0.4625 / 0.2875)   # ≈1.6087
    assert rr.verdict == "損小利大"


def test_risk_reward_loss_heavy():
    rr = risk_reward(base_fair=11, negative_fair=5, current_price=10)
    # upside=0.1, downside=-0.5 → rr=0.2 → 損大利小
    assert approx(rr.risk_reward, 0.2)
    assert rr.verdict == "損大利小"


# ---- 妥当倍率の提案 ----

def test_suggest_multiple_median_and_mean():
    assert suggest_multiple([10, 12, 20], method="median") == 12
    assert approx(suggest_multiple([10, 12, 20], method="mean"), 14)


def test_suggest_multiple_structural_discount():
    # 構造的割安 → 過去平均から割り引く（factor=0.8）
    assert approx(suggest_multiple([10, 20], method="mean", adjustment="structural", factor=0.8), 12.0)


def test_suggest_multiple_temporary_regression():
    # 一時的 → 過去平均に回帰（調整なし）
    assert approx(suggest_multiple([10, 20], method="mean", adjustment="temporary"), 15.0)


def test_suggest_multiple_empty():
    assert suggest_multiple([]) is None
