"""景気局面セレクター（仕様書 4.4 / 6章）。

現在の景気局面に応じて適正株価計算の「主指標」を自動切替し、各指標の信頼度を示す。
シクリカル銘柄は PER の高低を反転解釈する。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

# 景気局面 → 主指標＋推奨する適正株価の基準（per / pbr / dividend）。
# 仕様書 4.4 のルールテーブル。
BUSINESS_CYCLE_TABLE: dict[str, dict] = {
    "底・底からの回復": {
        "indicators": ["低PSR", "低PBR", "ネットキャッシュ÷時価総額"],
        "method": "pbr",
    },
    "回復の初期": {
        "indicators": ["高い増益率"],
        "method": "per",
    },
    "順調な拡大": {
        "indicators": ["低PER"],
        "method": "per",
    },
    "拡大の後期": {
        "indicators": ["低PER", "高リビジョン"],
        "method": "per",
    },
    "拡大の最終局面": {
        "indicators": ["高ROE", "低EV/EBITDA"],
        "method": "per",
    },
    "後退の初期": {
        "indicators": ["高配当利回り", "低EV/EBITDA"],
        "method": "dividend",
    },
    "後退の中期": {
        "indicators": ["低PBR", "高自己資本比率"],
        "method": "pbr",
    },
    "後退の後期": {
        "indicators": ["高ROE", "高自己資本比率", "ネットキャッシュ÷時価総額"],
        "method": "pbr",
    },
}

PHASES = tuple(BUSINESS_CYCLE_TABLE.keys())


@dataclass
class BusinessCycleSelection:
    phase: str
    primary_indicators: list[str]
    recommended_method: str            # per / pbr / dividend
    indicator_confidence: dict         # 指標名 → 信頼度（高 / 中）
    is_cyclical: bool
    cyclical_note: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def select_business_cycle(phase: str, is_cyclical: bool = False) -> BusinessCycleSelection:
    """景気局面から主指標・推奨基準・信頼度を返す（仕様書 4.4）。

    シクリカル銘柄フラグが立っている場合は PER の高低を反転解釈し、
    PBR・ネットキャッシュ÷時価総額を前面に出す（推奨基準を pbr に上書き）。
    """
    if phase not in BUSINESS_CYCLE_TABLE:
        raise ValueError(f"未知の景気局面: {phase}. 選択肢: {PHASES}")

    entry = BUSINESS_CYCLE_TABLE[phase]
    indicators = list(entry["indicators"])
    method = entry["method"]

    # 主指標の先頭を信頼度「高」、以降を「中」とする。
    confidence = {ind: ("高" if i == 0 else "中") for i, ind in enumerate(indicators)}

    cyclical_note = None
    if is_cyclical:
        cyclical_note = (
            "シクリカル銘柄：PER の高低を反転解釈（底＝高PERが買い、ピーク＝低PERが売り）。"
            "PBR・ネットキャッシュ÷時価総額を前面に出す。"
        )
        # PER を主指標にしない（PBR を前面に）
        method = "pbr"

    return BusinessCycleSelection(
        phase=phase,
        primary_indicators=indicators,
        recommended_method=method,
        indicator_confidence=confidence,
        is_cyclical=is_cyclical,
        cyclical_note=cyclical_note,
    )
