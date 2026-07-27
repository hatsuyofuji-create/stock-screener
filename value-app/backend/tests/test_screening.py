"""スクリーニング＋マトリクスのテスト（仕様書 4.5 / 4.7 / 受け入れ基準）。

魔法の公式：小さなダミー集合で合成ランク上位が手計算と一致すること。
"""

from app.engines.screening import (
    ScreenSnapshot, ThresholdCriteria, apply_threshold, magic_formula,
    classify_quadrant, build_matrix,
    QUADRANT_HONMEI, QUADRANT_VALUE_TRAP, QUADRANT_HEALTHY_EXPENSIVE, QUADRANT_OUT,
)


def _universe():
    # (code, roic, pbr)
    return [
        ScreenSnapshot(code="A", roic=0.30, pbr=1.5),  # ROIC最高
        ScreenSnapshot(code="B", roic=0.20, pbr=0.8),
        ScreenSnapshot(code="C", roic=0.10, pbr=0.5),  # PBR最低
        ScreenSnapshot(code="D", roic=0.05, pbr=2.0),  # 最下位
    ]


def test_magic_formula_ranks():
    """手計算:
    ROIC順位(高い順): A=1, B=2, C=3, D=4
    PBR順位(低い順):  C=1, B=2, A=3, D=4
    合成: A=4, B=4, C=4, D=8
    A/B/C は同点4 → ROIC順位が良い順に A, B, C。
    """
    res = magic_formula(_universe(), top_n=3)
    codes = [r["code"] for r in res["results"]]
    assert codes == ["A", "B", "C"]
    a = next(r for r in res["results"] if r["code"] == "A")
    assert a["rank_roic"] == 1 and a["rank_pbr"] == 3 and a["combined_rank"] == 4
    c = next(r for r in res["results"] if r["code"] == "C")
    assert c["rank_roic"] == 3 and c["rank_pbr"] == 1 and c["combined_rank"] == 4
    assert res["count"] == 3


def test_magic_formula_ignores_incomplete():
    snaps = [
        ScreenSnapshot(code="A", roic=0.3, pbr=1.0),
        ScreenSnapshot(code="B", roic=None, pbr=0.5),  # ROIC 欠損 → 除外
        ScreenSnapshot(code="C", roic=0.1, pbr=None),  # PBR 欠損 → 除外
    ]
    res = magic_formula(snaps)
    codes = [r["code"] for r in res["results"]]
    assert codes == ["A"]


def test_threshold_filter():
    snaps = [
        ScreenSnapshot(code="A", dividend_yield=0.04, equity_ratio=0.6,
                       net_interest_bearing_debt=-100, fcf=50, roe=0.18,
                       market_cap=50_000_000_000, fscore=8),
        ScreenSnapshot(code="B", dividend_yield=0.01, equity_ratio=0.6,
                       net_interest_bearing_debt=200, fcf=-10, roe=0.05,
                       market_cap=200_000_000_000, fscore=4),
    ]
    criteria = ThresholdCriteria(
        dividend_yield_min=0.03, net_cash_required=True, fcf_positive=True,
        roe_min=0.15, fscore_min=7,
    )
    res = apply_threshold(snaps, criteria)
    assert res["count"] == 1
    assert res["hits"][0]["code"] == "A"


def test_threshold_missing_value_fails_active_condition():
    """ONの条件で値が欠損なら不合格。"""
    snaps = [ScreenSnapshot(code="X", fscore=None)]
    res = apply_threshold(snaps, ThresholdCriteria(fscore_min=7))
    assert res["count"] == 0


def test_threshold_no_conditions_passes_all():
    snaps = [ScreenSnapshot(code="X"), ScreenSnapshot(code="Y")]
    res = apply_threshold(snaps, ThresholdCriteria())
    assert res["count"] == 2


def test_classify_quadrant():
    assert classify_quadrant(0.8, 8) == QUADRANT_HONMEI            # 低PBR×高F
    assert classify_quadrant(0.8, 3) == QUADRANT_VALUE_TRAP       # 低PBR×低F
    assert classify_quadrant(1.5, 8) == QUADRANT_HEALTHY_EXPENSIVE  # 高PBR×高F
    assert classify_quadrant(1.5, 2) == QUADRANT_OUT             # 高PBR×低F
    assert classify_quadrant(None, 8) is None


def test_build_matrix_highlight():
    snaps = [
        ScreenSnapshot(code="A", name="本命", pbr=0.7, fscore=8, roe=0.20),
        ScreenSnapshot(code="B", name="トラップ", pbr=0.6, fscore=2, roe=0.03),
    ]
    m = build_matrix(snaps)
    a = next(p for p in m["points"] if p["code"] == "A")
    b = next(p for p in m["points"] if p["code"] == "B")
    assert a["quadrant"] == QUADRANT_HONMEI
    assert a["high_roe_low_pbr"] is True   # 高ROE×低PBR ハイライト
    assert b["quadrant"] == QUADRANT_VALUE_TRAP
    assert b["high_roe_low_pbr"] is False
