"""Fスコアエンジンのテスト（仕様書 4.2 / 受け入れ基準）。

特に項目8（増資判定＝資本金の前期比）と項目4（営業CF > 純利益）の境界値を検証する。
"""

from dataclasses import replace

from app.engines.fscore import (
    compute_fscore, build_forecast_snapshot, HEALTHY_THRESHOLD, UNHEALTHY_THRESHOLD,
)


def test_perfect_score(latest_fs, prior_fs):
    """全項目改善のサンプルは 9 点（満点）になる。"""
    result = compute_fscore(latest_fs, prior_fs)
    assert result.total == 9
    assert result.is_healthy is True
    assert result.is_unhealthy is False
    # 全項目 pass
    assert all(item.passed for item in result.items)
    assert result.mode == "actual"


def test_item8_capital_increase_fails(latest_fs, prior_fs):
    """項目8：資本金が前期より増えた（増資）→ No。"""
    diluted = replace(latest_fs, capital_stock=120)  # prior=100 より増加
    result = compute_fscore(diluted, prior_fs)
    item8 = next(i for i in result.items if i.number == 8)
    assert item8.passed is False
    assert result.total == 8


def test_item8_capital_equal_passes(latest_fs, prior_fs):
    """項目8 境界：資本金が前期と同額（増資なし）→ Yes（<= 判定）。"""
    same = replace(latest_fs, capital_stock=100)  # prior と同額
    result = compute_fscore(same, prior_fs)
    item8 = next(i for i in result.items if i.number == 8)
    assert item8.passed is True


def test_item4_cf_equal_net_income_fails(latest_fs, prior_fs):
    """項目4 境界：営業CF == 純利益 は「>」でないので No。"""
    boundary = replace(latest_fs, operating_cf=95)  # net_income=95 と同値
    result = compute_fscore(boundary, prior_fs)
    item4 = next(i for i in result.items if i.number == 4)
    assert item4.passed is False


def test_item4_cf_above_net_income_passes(latest_fs, prior_fs):
    boundary = replace(latest_fs, operating_cf=96)  # net_income=95 を1上回る
    result = compute_fscore(boundary, prior_fs)
    item4 = next(i for i in result.items if i.number == 4)
    assert item4.passed is True


def test_unhealthy_company():
    """悪化企業は低スコア（不健全判定）になる。"""
    from app.engines.financials import RawFinancials
    prior = RawFinancials(
        fiscal_period="2024-03", revenue=1000, cogs=600, operating_income=100,
        ordinary_income=90, net_income=60, operating_cf=80, total_assets=1000,
        equity=500, current_assets=400, current_liabilities=200,
        interest_bearing_debt=100, cash=50, capital_stock=100,
    )
    # 全面的に悪化 + 増資 + 営業CF < 純利益(赤字だが CF はさらに低い)
    latest = RawFinancials(
        fiscal_period="2025-03", revenue=800, cogs=560, operating_income=20,
        ordinary_income=10, net_income=-30, operating_cf=-50, total_assets=1200,
        equity=450, current_assets=350, current_liabilities=250,
        interest_bearing_debt=300, cash=20, capital_stock=150,  # 増資
    )
    result = compute_fscore(latest, prior)
    assert result.total <= UNHEALTHY_THRESHOLD
    assert result.is_unhealthy is True
    # 項目1（純利益>0）と項目2（営業CF>0）は No
    assert not next(i for i in result.items if i.number == 1).passed
    assert not next(i for i in result.items if i.number == 2).passed
    # 項目8（増資）も No
    assert not next(i for i in result.items if i.number == 8).passed


def test_all_nine_items_present(latest_fs, prior_fs):
    result = compute_fscore(latest_fs, prior_fs)
    assert len(result.items) == 9
    assert [i.number for i in result.items] == list(range(1, 10))
    # カテゴリ内訳（収益性5・安全性3・生産性1）
    cats = [i.category for i in result.items]
    assert cats.count("収益性") == 5
    assert cats.count("安全性") == 3
    assert cats.count("生産性") == 1


def test_forecast_snapshot_overlay(latest_fs, prior_fs):
    """予想版：最新期の一部を予想値に差し替えて算出できる（仕様書 4.2）。"""
    # 予想で純利益を大幅減額（減損想定）→ 項目1/4 に影響
    forecast = build_forecast_snapshot(latest_fs, {
        "net_income": -10, "operating_income": 30, "revenue": 1100,
    })
    # 予想では純利益マイナス → 項目1 No
    result = compute_fscore(forecast, prior_fs, mode="forecast")
    assert result.mode == "forecast"
    item1 = next(i for i in result.items if i.number == 1)
    assert item1.passed is False
    # CF は実績を引き継ぐ（上書きしていない）
    assert forecast.operating_cf == latest_fs.operating_cf


def test_thresholds_constants():
    assert HEALTHY_THRESHOLD == 7
    assert UNHEALTHY_THRESHOLD == 3
