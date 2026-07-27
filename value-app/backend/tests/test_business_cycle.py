"""景気局面セレクターのテスト（仕様書 4.4）。"""

import pytest

from app.engines.business_cycle import select_business_cycle, PHASES


def test_all_phases_defined():
    assert len(PHASES) == 8
    assert "順調な拡大" in PHASES


def test_expansion_uses_per():
    sel = select_business_cycle("順調な拡大")
    assert sel.recommended_method == "per"
    assert "低PER" in sel.primary_indicators
    assert sel.indicator_confidence["低PER"] == "高"


def test_bottom_uses_pbr():
    sel = select_business_cycle("底・底からの回復")
    assert sel.recommended_method == "pbr"
    assert "低PBR" in sel.primary_indicators


def test_early_recession_uses_dividend():
    sel = select_business_cycle("後退の初期")
    assert sel.recommended_method == "dividend"
    assert "高配当利回り" in sel.primary_indicators


def test_cyclical_inverts_to_pbr():
    """シクリカル銘柄は PER 局面でも PBR を前面に、注記を付す。"""
    sel = select_business_cycle("順調な拡大", is_cyclical=True)
    assert sel.recommended_method == "pbr"
    assert sel.cyclical_note is not None
    assert "反転解釈" in sel.cyclical_note


def test_unknown_phase_raises():
    with pytest.raises(ValueError):
        select_business_cycle("好景気")
