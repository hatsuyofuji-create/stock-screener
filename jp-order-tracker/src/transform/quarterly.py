# -*- coding: utf-8 -*-
"""
=====================================================================
 累計 → 各Q単独 への変換
=====================================================================
 決算短信の受注高は、多くが「累計（その期までの合計）」で書かれています。
   - Q1 累計 = Q1単独
   - Q2 累計 = 上期(Q1+Q2)
   - Q3 累計 = 9ヶ月(Q1+Q2+Q3)
   - FY(通期) = Q1+Q2+Q3+Q4
 なので「各Q単独」を出すには、累計どうしを引き算します。
   - 単独Q1 = 累計Q1
   - 単独Q2 = 累計Q2 - 累計Q1
   - 単独Q3 = 累計Q3 - 累計Q2
   - 単独Q4 = 通期     - 累計Q3

 一方、会社によっては最初から「単独（当四半期）」で載せている場合もあります。
 その場合は引き算せず、そのまま使います（period_type で判定）。

 金額の単位は会社ごとに「百万円」「億円」などバラバラなので、
 ここで全部 百万円 に正規化します（1億円 = 100百万円）。
=====================================================================
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ---- 単位の正規化 --------------------------------------------------

_UNIT_TO_MILLION = {
    "百万円": 1.0,
    "million_yen": 1.0,
    "億円": 100.0,     # 1億円 = 100百万円
    "億": 100.0,
    "円": 1e-6,        # 1円 = 0.000001百万円
    "千円": 1e-3,      # 1千円 = 0.001百万円
}


def to_million_yen(value: Optional[float], unit: str) -> Optional[float]:
    """任意単位の金額を『百万円』にそろえる。value が None ならそのまま None。"""
    if value is None:
        return None
    if unit not in _UNIT_TO_MILLION:
        raise ValueError(f"未知の単位です: {unit!r}（百万円/億円/千円/円 に対応）")
    return round(value * _UNIT_TO_MILLION[unit], 3)


# ---- 累計 → 単独 ---------------------------------------------------

def cumulative_to_single(cumulative: dict[int, Optional[float]]) -> dict[int, Optional[float]]:
    """
    累計値の辞書 {1: Q1累計, 2: Q2累計, 3: Q3累計, 4: 通期} を受け取り、
    各Q単独 {1:.., 2:.., 3:.., 4:..} を返す。

    ある四半期の累計が欠けている(None)場合、その差分で計算する単独値は None になる。
    """
    single: dict[int, Optional[float]] = {}
    single[1] = cumulative.get(1)
    for q in (2, 3, 4):
        cur = cumulative.get(q)
        prev = cumulative.get(q - 1)
        single[q] = None if (cur is None or prev is None) else round(cur - prev, 3)
    return single


# ---- データ構造 ---------------------------------------------------

@dataclass
class DocumentExtraction:
    """1つの短信PDFから抜き出した受注高（LLM抽出の結果を入れる箱）。"""
    code: str                       # 銘柄コード 例 "6141"
    company: str                    # 会社名
    fiscal_year: str                # 決算期 例 "2026-12" / "2026-03"
    quarter: int                    # 1,2,3,4（4=通期/本決算）
    period_type: str                # "cumulative"(累計) か "quarter"(単独)
    unit: str                       # "百万円" / "億円" など
    total: Optional[float]          # 受注高 合計（元単位のまま）
    segments: dict[str, Optional[float]] = field(default_factory=dict)  # セグメント別（元単位）

    def total_million(self) -> Optional[float]:
        return to_million_yen(self.total, self.unit)

    def segments_million(self) -> dict[str, Optional[float]]:
        return {k: to_million_yen(v, self.unit) for k, v in self.segments.items()}


@dataclass
class QuarterlyOrders:
    """1銘柄・1決算期分の、各Q単独 受注高（百万円）。"""
    code: str
    company: str
    fiscal_year: str
    # セグメント名 -> {1:単独Q1, 2:単独Q2, 3:単独Q3, 4:単独Q4}（百万円）
    single_by_segment: dict[str, dict[int, Optional[float]]]
    # 合計 {1..4}
    single_total: dict[int, Optional[float]]


def build_quarterly(docs: list[DocumentExtraction]) -> list[QuarterlyOrders]:
    """
    複数の短信抽出結果（同一銘柄・複数四半期を含む）から、
    (銘柄, 決算期) ごとに『各Q単独 受注高（百万円）』を組み立てる。
    """
    # (code, fiscal_year) でグループ化
    groups: dict[tuple[str, str], list[DocumentExtraction]] = {}
    for d in docs:
        groups.setdefault((d.code, d.fiscal_year), []).append(d)

    results: list[QuarterlyOrders] = []
    for (code, fy), items in groups.items():
        company = next((d.company for d in items if d.company), code)

        # そのグループに出てくる全セグメント名を集める
        seg_names: set[str] = set()
        for d in items:
            seg_names.update(d.segments.keys())

        # --- 合計の各Q単独 ---
        cum_total: dict[int, Optional[float]] = {}
        direct_total: dict[int, Optional[float]] = {}
        for d in items:
            v = d.total_million()
            if d.period_type == "quarter":
                direct_total[d.quarter] = v      # 既に単独ならそのまま
            else:
                cum_total[d.quarter] = v         # 累計は後で引き算
        single_total = cumulative_to_single(cum_total)
        single_total.update({q: v for q, v in direct_total.items() if v is not None})

        # --- セグメント別の各Q単独 ---
        single_by_segment: dict[str, dict[int, Optional[float]]] = {}
        for seg in seg_names:
            cum_seg: dict[int, Optional[float]] = {}
            direct_seg: dict[int, Optional[float]] = {}
            for d in items:
                v = to_million_yen(d.segments.get(seg), d.unit)
                if d.period_type == "quarter":
                    direct_seg[d.quarter] = v
                else:
                    cum_seg[d.quarter] = v
            s = cumulative_to_single(cum_seg)
            s.update({q: v for q, v in direct_seg.items() if v is not None})
            single_by_segment[seg] = s

        results.append(QuarterlyOrders(
            code=code, company=company, fiscal_year=fy,
            single_by_segment=single_by_segment, single_total=single_total,
        ))

    results.sort(key=lambda r: (r.code, r.fiscal_year))
    return results
