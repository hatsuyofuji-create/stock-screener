"""ポートフォリオ管理・アラートエンジン（仕様書 4.8 / 12章）。

判断基準は常に「適正株価」。購入価格や含み益に判断を惑わされない設計。

- 利確アラート：現在株価 ≥ 適正株価 到達 → 成長タイプ別ルール。
- 損切りアラート：①シナリオ崩壊、②バリュートラップ継続、③2年以上含み損。
- ポジションサイズ提案：自信度 × アップサイド％。
- 分散チェック：保有5〜10、業種偏り。
- 「今この株を非保有と仮定」再評価。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from typing import Optional

from .screening import classify_quadrant, QUADRANT_VALUE_TRAP

# 成長タイプのグルーピング（仕様書 4.8 の利確ルール）
GROWTH_TYPES_GROWTH = ("安定成長", "シクリカル成長", "新領域開拓")
GROWTH_TYPES_CYCLICAL = ("シクリカル",)
GROWTH_TYPES_STRUGGLING = ("業績低迷",)

DEFAULT_OVERVALUED_FACTOR = 1.3   # 「割高すぎ」の判定係数（適正株価の何倍か）
DEFAULT_LOSS_YEARS = 2            # 損切りの時間基準（含み損2年以上）


# ----------------------------------------------------------------------------
# 利確アラート
# ----------------------------------------------------------------------------

@dataclass
class TakeProfitAlert:
    triggered: bool
    reached_fair_value: bool
    growth_group: str
    action: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def _growth_group(growth_type: Optional[str]) -> str:
    if growth_type in GROWTH_TYPES_CYCLICAL:
        return "cyclical"
    if growth_type in GROWTH_TYPES_STRUGGLING:
        return "struggling"
    return "growth"  # デフォルトは成長企業扱い


def take_profit_alert(
    *,
    growth_type: Optional[str],
    current_price: Optional[float],
    fair_price: Optional[float],
    overvalued_factor: float = DEFAULT_OVERVALUED_FACTOR,
    at_cycle_peak: bool = False,
    reached_hist_avg_valuation: bool = False,
    recovery_target_price: Optional[float] = None,
) -> TakeProfitAlert:
    """成長タイプ別の利確アラートを返す（仕様書 4.8）。"""
    reached = (
        current_price is not None and fair_price is not None
        and current_price >= fair_price
    )
    group = _growth_group(growth_type)

    if group == "growth":
        overvalued = (
            current_price is not None and fair_price is not None
            and current_price >= fair_price * overvalued_factor
        )
        if overvalued:
            return TakeProfitAlert(True, reached, group, "ポジション調整",
                                   "割高すぎ。成長の源泉が健在でもポジションを調整。")
        if reached:
            return TakeProfitAlert(True, reached, group, "保有継続",
                                   "適正株価に到達。成長の源泉が崩れない限り保有。")
        return TakeProfitAlert(False, reached, group, "保有継続", "適正株価未到達。")

    if group == "cyclical":
        if at_cycle_peak or reached_hist_avg_valuation:
            return TakeProfitAlert(True, reached, group, "売却",
                                   "景気ピーク／過去平均バリュエーション到達。売却を検討。")
        if reached:
            return TakeProfitAlert(True, reached, group, "景気局面を確認",
                                   "適正株価到達。景気局面（ピーク接近か）を確認。")
        return TakeProfitAlert(False, reached, group, "保有継続", "適正株価未到達。")

    # struggling（業績苦戦・構造改革）
    target = recovery_target_price
    hit_target = (
        current_price is not None and target is not None and current_price >= target
    )
    if hit_target:
        return TakeProfitAlert(True, reached, group, "売却",
                               "株価が『回復後利益 × 市場平均PER』に到達。売却を検討。")
    return TakeProfitAlert(False, reached, group, "保有継続",
                           "回復後の目標株価に未到達。")


# ----------------------------------------------------------------------------
# 損切りアラート
# ----------------------------------------------------------------------------

@dataclass
class StopLossAlert:
    triggered: bool
    reasons: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _years_between(start_iso: Optional[str], end: date) -> Optional[float]:
    if not start_iso:
        return None
    try:
        y, m, d = (int(x) for x in start_iso.split("-")[:3])
        start = date(y, m, d)
    except (ValueError, TypeError):
        return None
    return (end - start).days / 365.25


def stop_loss_alert(
    *,
    scenario_broken: bool = False,
    pbr: Optional[float] = None,
    fscore: Optional[int] = None,
    value_trap_persist: bool = False,
    buy_date: Optional[str] = None,
    buy_price: Optional[float] = None,
    current_price: Optional[float] = None,
    today: Optional[date] = None,
    pbr_threshold: float = 1.0,
    fscore_healthy: int = 7,
    loss_years: float = DEFAULT_LOSS_YEARS,
) -> StopLossAlert:
    """損切りアラート（仕様書 4.8）。①〜③のいずれかで発火。"""
    today = today or date.today()
    reasons: list[str] = []

    # ① 想定シナリオ崩壊
    if scenario_broken:
        reasons.append("想定シナリオが崩壊")

    # ② バリュートラップ判定（低PBR×低Fスコアが継続）
    is_trap = classify_quadrant(pbr, fscore, pbr_threshold, fscore_healthy) == QUADRANT_VALUE_TRAP
    if is_trap and value_trap_persist:
        reasons.append("バリュートラップ（低PBR×低Fスコア）が継続")

    # ③ ①②が無くても 2年以上含み損が継続
    years = _years_between(buy_date, today)
    in_loss = (
        buy_price is not None and current_price is not None and current_price < buy_price
    )
    if in_loss and years is not None and years >= loss_years:
        reasons.append(f"含み損が{loss_years}年以上継続")

    return StopLossAlert(triggered=bool(reasons), reasons=reasons)


# ----------------------------------------------------------------------------
# ポジションサイズ提案
# ----------------------------------------------------------------------------

@dataclass
class PositionSizeSuggestion:
    recommended_weight: float   # 推奨保有比率（0〜max_weight）
    raw_score: float            # 自信度 × アップサイド％

    def to_dict(self) -> dict:
        return asdict(self)


def position_size(
    confidence: Optional[int],
    upside: Optional[float],
    max_weight: float = 0.20,
) -> PositionSizeSuggestion:
    """自信度(1-5) × アップサイド％ に応じて推奨保有比率を提示（仕様書 4.8）。"""
    c = confidence or 0
    up = max(upside or 0.0, 0.0)  # マイナス（割高）は 0 扱い
    raw = (c / 5.0) * up
    weight = min(max(raw, 0.0), max_weight)
    return PositionSizeSuggestion(recommended_weight=weight, raw_score=raw)


# ----------------------------------------------------------------------------
# 分散チェック
# ----------------------------------------------------------------------------

@dataclass
class DiversificationReport:
    count: int
    sector_counts: dict
    max_sector_share: Optional[float]
    warnings: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def diversification_check(
    holdings: list[dict],
    min_n: int = 5,
    max_n: int = 10,
    sector_concentration_limit: float = 0.4,
) -> DiversificationReport:
    """保有銘柄数と業種偏りをチェックする（仕様書 4.8）。

    holdings: [{"code": ..., "sector": ...}, ...]
    """
    count = len(holdings)
    sector_counts: dict[str, int] = {}
    for h in holdings:
        sec = h.get("sector") or "不明"
        sector_counts[sec] = sector_counts.get(sec, 0) + 1

    max_share: Optional[float] = None
    if count > 0:
        max_share = max(sector_counts.values()) / count

    warnings: list[str] = []
    if count < min_n:
        warnings.append(f"保有銘柄が少なすぎます（{count}件 < 目安{min_n}）")
    if count > max_n:
        warnings.append(f"保有銘柄が多すぎます（{count}件 > 目安{max_n}）")
    if max_share is not None and max_share > sector_concentration_limit:
        top = max(sector_counts, key=sector_counts.get)
        warnings.append(f"業種偏り：{top} が {max_share:.0%} を占めます")

    return DiversificationReport(
        count=count, sector_counts=sector_counts,
        max_sector_share=max_share, warnings=warnings,
    )


# ----------------------------------------------------------------------------
# 「今この株を非保有と仮定」再評価
# ----------------------------------------------------------------------------

@dataclass
class ReevaluationResult:
    would_buy: bool
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def reevaluate_as_new(
    *,
    margin_of_safety: Optional[float],
    fscore: Optional[int],
    fscore_healthy: int = 7,
) -> ReevaluationResult:
    """保有効果（行動バイアス）を外し、今から買うかを判定する（仕様書 4.8）。"""
    would_buy = (
        margin_of_safety is not None and margin_of_safety > 0
        and fscore is not None and fscore >= fscore_healthy
    )
    if would_buy:
        msg = "非保有だとしても買う水準（安全域プラス×財務健全）。保有継続は妥当。"
    else:
        msg = "非保有なら今は買わない水準。保有効果に注意し、売却も選択肢。"
    return ReevaluationResult(would_buy=would_buy, message=msg)
