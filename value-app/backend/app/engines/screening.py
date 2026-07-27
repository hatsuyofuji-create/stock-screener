"""スクリーニング＋銘柄マトリクスのエンジン（仕様書 4.5 / 4.7）。

- モードA：閾値フィルター（各条件は可変・ON/OFF可）。
- モードB：グリーンブラットの魔法の公式（ROIC 順位 ＋ PBR 順位の合成ランク）。
- 銘柄マトリクス：横軸 PBR・縦軸 Fスコアの4象限分類とハイライト。

DB 非依存の純粋関数。入力は ScreenSnapshot のリスト（DB から組み立てる）。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional

# マトリクスのデフォルト閾値（仕様書 4.7）
DEFAULT_PBR_THRESHOLD = 1.0
DEFAULT_FSCORE_HEALTHY = 7
# 高ROE ハイライトのデフォルト閾値（4章「高ROEなのに低PBR」）
DEFAULT_HIGH_ROE = 0.15


@dataclass
class ScreenSnapshot:
    """1銘柄の評価スナップショット（財務＋市場データの計算済み値）。"""

    code: str
    name: str = ""
    pbr: Optional[float] = None
    per: Optional[float] = None
    dividend_yield: Optional[float] = None
    market_cap: Optional[float] = None
    price_change_3y: Optional[float] = None
    roe: Optional[float] = None
    roic: Optional[float] = None
    equity_ratio: Optional[float] = None
    net_interest_bearing_debt: Optional[float] = None
    fcf: Optional[float] = None
    fscore: Optional[int] = None
    bps: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ----------------------------------------------------------------------------
# モードA：閾値フィルター
# ----------------------------------------------------------------------------

@dataclass
class ThresholdCriteria:
    """閾値フィルターの条件（None / False は OFF）。仕様書 4.5 モードA。"""

    dividend_yield_min: Optional[float] = None   # 配当利回り ≥ X
    equity_ratio_min: Optional[float] = None     # 自己資本比率 ≥ Y
    net_cash_required: bool = False              # 純有利子負債 < 0（ネットキャッシュ）
    fcf_positive: bool = False                   # FCF > 0
    roe_min: Optional[float] = None              # ROE ≥ 15% など
    market_cap_max: Optional[float] = None       # 時価総額 ≤ 1000億円 など
    price_change_3y_negative: bool = False       # 株価3年変化率 < 0（逆張り）
    fscore_min: Optional[int] = None             # Fスコア ≥ 7


def _passes(snap: ScreenSnapshot, c: ThresholdCriteria) -> tuple[bool, dict[str, bool]]:
    """各条件の合否を返す。ONの条件で値が欠損なら不合格（安全側）。"""
    results: dict[str, bool] = {}

    def check(name: str, active: bool, ok) -> None:
        if active:
            results[name] = bool(ok)

    check("dividend_yield_min", c.dividend_yield_min is not None,
          snap.dividend_yield is not None and c.dividend_yield_min is not None
          and snap.dividend_yield >= c.dividend_yield_min)
    check("equity_ratio_min", c.equity_ratio_min is not None,
          snap.equity_ratio is not None and c.equity_ratio_min is not None
          and snap.equity_ratio >= c.equity_ratio_min)
    check("net_cash_required", c.net_cash_required,
          snap.net_interest_bearing_debt is not None and snap.net_interest_bearing_debt < 0)
    check("fcf_positive", c.fcf_positive,
          snap.fcf is not None and snap.fcf > 0)
    check("roe_min", c.roe_min is not None,
          snap.roe is not None and c.roe_min is not None and snap.roe >= c.roe_min)
    check("market_cap_max", c.market_cap_max is not None,
          snap.market_cap is not None and c.market_cap_max is not None
          and snap.market_cap <= c.market_cap_max)
    check("price_change_3y_negative", c.price_change_3y_negative,
          snap.price_change_3y is not None and snap.price_change_3y < 0)
    check("fscore_min", c.fscore_min is not None,
          snap.fscore is not None and c.fscore_min is not None and snap.fscore >= c.fscore_min)

    passed = all(results.values()) if results else True
    return passed, results


def apply_threshold(snaps: list[ScreenSnapshot], criteria: ThresholdCriteria) -> dict:
    """閾値フィルターを適用し、ヒット銘柄と件数を返す（仕様書 4.5 モードA）。"""
    hits = []
    for snap in snaps:
        passed, detail = _passes(snap, criteria)
        if passed:
            hits.append({**snap.to_dict(), "criteria_detail": detail})
    return {"count": len(hits), "hits": hits}


# ----------------------------------------------------------------------------
# モードB：魔法の公式（ランキング）
# ----------------------------------------------------------------------------

def _competition_rank(values: list[tuple[str, float]], descending: bool) -> dict[str, int]:
    """標準競争順位（同値は同順位）を返す。値が良いほど 1 に近い。"""
    ranks: dict[str, int] = {}
    for code, val in values:
        better = sum(
            1 for _, other in values
            if (other > val if descending else other < val)
        )
        ranks[code] = better + 1
    return ranks


def magic_formula(snaps: list[ScreenSnapshot], top_n: int = 30) -> dict:
    """ROIC 高い順 ＋ PBR 低い順の合成ランクで上位 N 社を選ぶ（仕様書 4.5 モードB）。"""
    eligible = [s for s in snaps if s.roic is not None and s.pbr is not None]

    roic_pairs = [(s.code, s.roic) for s in eligible]
    pbr_pairs = [(s.code, s.pbr) for s in eligible]
    rank_roic = _competition_rank(roic_pairs, descending=True)   # ROIC は高いほど上位
    rank_pbr = _competition_rank(pbr_pairs, descending=False)    # PBR は低いほど上位

    rows = []
    for s in eligible:
        rr = rank_roic[s.code]
        rp = rank_pbr[s.code]
        rows.append({
            **s.to_dict(),
            "rank_roic": rr,
            "rank_pbr": rp,
            "combined_rank": rr + rp,
        })
    # 合成ランク昇順（同値は ROIC 順位が良い方を優先）
    rows.sort(key=lambda r: (r["combined_rank"], r["rank_roic"]))
    return {"count": min(top_n, len(rows)), "results": rows[:top_n]}


# ----------------------------------------------------------------------------
# 銘柄マトリクス（4.7）
# ----------------------------------------------------------------------------

# 象限の定義（横軸 PBR：左が割安、縦軸 Fスコア：上が健全）
QUADRANT_HONMEI = "honmei"            # 左上：低PBR × 高Fスコア（本命ゾーン・買い候補）
QUADRANT_VALUE_TRAP = "value_trap"   # 左下：低PBR × 低Fスコア（バリュートラップ警告・赤）
QUADRANT_HEALTHY_EXPENSIVE = "healthy_expensive"  # 右上：高PBR × 高Fスコア（健全だが割高）
QUADRANT_OUT = "out"                 # 右下：高PBR × 低Fスコア（対象外）


def classify_quadrant(pbr: Optional[float], fscore: Optional[int],
                      pbr_threshold: float = DEFAULT_PBR_THRESHOLD,
                      fscore_healthy: int = DEFAULT_FSCORE_HEALTHY) -> Optional[str]:
    """PBR と Fスコアから4象限を判定する（仕様書 4.7）。"""
    if pbr is None or fscore is None:
        return None
    low_pbr = pbr < pbr_threshold
    high_f = fscore >= fscore_healthy
    if low_pbr and high_f:
        return QUADRANT_HONMEI
    if low_pbr and not high_f:
        return QUADRANT_VALUE_TRAP
    if not low_pbr and high_f:
        return QUADRANT_HEALTHY_EXPENSIVE
    return QUADRANT_OUT


def build_matrix(snaps: list[ScreenSnapshot],
                 pbr_threshold: float = DEFAULT_PBR_THRESHOLD,
                 fscore_healthy: int = DEFAULT_FSCORE_HEALTHY,
                 high_roe: float = DEFAULT_HIGH_ROE) -> dict:
    """散布図用のポイント配列を作る（仕様書 4.7）。

    各点に象限・色・「高ROE×低PBR」ハイライトフラグを付与する。
    """
    points = []
    for s in snaps:
        quadrant = classify_quadrant(s.pbr, s.fscore, pbr_threshold, fscore_healthy)
        highlight = (
            s.roe is not None and s.pbr is not None
            and s.roe >= high_roe and s.pbr < pbr_threshold
        )
        points.append({
            "code": s.code, "name": s.name,
            "pbr": s.pbr, "fscore": s.fscore, "roe": s.roe,
            "quadrant": quadrant,
            "high_roe_low_pbr": highlight,
        })
    return {
        "pbr_threshold": pbr_threshold,
        "fscore_healthy": fscore_healthy,
        "points": points,
    }
