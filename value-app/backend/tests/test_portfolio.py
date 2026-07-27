"""ポートフォリオ管理・アラートのテスト（仕様書 4.8）。"""

from datetime import date

from app.engines.portfolio import (
    take_profit_alert, stop_loss_alert, position_size,
    diversification_check, reevaluate_as_new,
)


# ---- 利確アラート ----

def test_take_profit_growth_hold():
    """成長企業：適正株価到達だが割高すぎでない → 保有継続。"""
    a = take_profit_alert(growth_type="安定成長", current_price=110, fair_price=100)
    assert a.triggered is True
    assert a.action == "保有継続"


def test_take_profit_growth_trim():
    """成長企業：割高すぎ（適正株価×1.3以上）→ ポジション調整。"""
    a = take_profit_alert(growth_type="安定成長", current_price=140, fair_price=100)
    assert a.action == "ポジション調整"


def test_take_profit_cyclical_sell_at_peak():
    a = take_profit_alert(growth_type="シクリカル", current_price=90, fair_price=100,
                          at_cycle_peak=True)
    assert a.triggered is True
    assert a.action == "売却"


def test_take_profit_struggling_recovery_target():
    """業績苦戦：回復後利益×市場平均PER の目標株価に到達 → 売却。"""
    a = take_profit_alert(growth_type="業績低迷", current_price=210,
                          fair_price=None, recovery_target_price=200)
    assert a.triggered is True
    assert a.action == "売却"


def test_take_profit_not_reached():
    a = take_profit_alert(growth_type="安定成長", current_price=80, fair_price=100)
    assert a.triggered is False


# ---- 損切りアラート ----

def test_stop_loss_scenario_broken():
    a = stop_loss_alert(scenario_broken=True)
    assert a.triggered is True
    assert any("シナリオ" in r for r in a.reasons)


def test_stop_loss_value_trap_persist():
    a = stop_loss_alert(pbr=0.6, fscore=2, value_trap_persist=True)
    assert a.triggered is True
    assert any("バリュートラップ" in r for r in a.reasons)


def test_stop_loss_value_trap_not_persist():
    """バリュートラップだが継続していなければ発火しない。"""
    a = stop_loss_alert(pbr=0.6, fscore=2, value_trap_persist=False)
    assert a.triggered is False


def test_stop_loss_two_year_loss():
    a = stop_loss_alert(buy_date="2023-01-01", buy_price=100, current_price=80,
                        today=date(2025, 6, 1))
    assert a.triggered is True
    assert any("2年" in r for r in a.reasons)


def test_stop_loss_recent_loss_not_triggered():
    a = stop_loss_alert(buy_date="2024-06-01", buy_price=100, current_price=80,
                        today=date(2025, 6, 1))
    assert a.triggered is False


# ---- ポジションサイズ ----

def test_position_size():
    # 自信度4 × アップサイド50% = 0.8 × 0.5 = 0.4 → max_weight 0.2 で頭打ち
    p = position_size(confidence=4, upside=0.5, max_weight=0.2)
    assert p.raw_score == (4 / 5) * 0.5
    assert p.recommended_weight == 0.2


def test_position_size_negative_upside():
    p = position_size(confidence=5, upside=-0.3)
    assert p.recommended_weight == 0.0


# ---- 分散チェック ----

def test_diversification_too_few_and_concentrated():
    holdings = [
        {"code": "A", "sector": "機械"},
        {"code": "B", "sector": "機械"},
        {"code": "C", "sector": "機械"},
    ]
    r = diversification_check(holdings)
    assert r.count == 3
    assert r.max_sector_share == 1.0
    assert any("少なすぎ" in w for w in r.warnings)
    assert any("業種偏り" in w for w in r.warnings)


def test_diversification_balanced():
    holdings = [{"code": str(i), "sector": s}
                for i, s in enumerate(["機械", "食品", "情報", "金融", "小売", "化学"])]
    r = diversification_check(holdings)
    assert r.warnings == []


# ---- 再評価 ----

def test_reevaluate_would_buy():
    r = reevaluate_as_new(margin_of_safety=0.2, fscore=8)
    assert r.would_buy is True


def test_reevaluate_would_not_buy():
    r = reevaluate_as_new(margin_of_safety=-0.1, fscore=8)
    assert r.would_buy is False
