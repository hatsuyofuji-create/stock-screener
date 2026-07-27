"""Fスコア計算エンジン（仕様書 4.2 / 7章・ツール⑦）。

9項目を Yes=1 / No=0 で採点し合計（0〜9）。7以上＝財務健全、3以下＝不健全。
比較は「最新期」対「前期」。

- 実績版：EDINET/TDnet の確定値（RawFinancials）を使用。
- 予想版：最新期の値をユーザー予想（Forecast）に差し替えて算出。
  → `build_forecast_snapshot()` で最新実績に予想値を上書きした RawFinancials を作り、
     それを最新期として compute_fscore に渡す。

判定ルール（欠損値の扱い）:
- 採点に必要な値が欠損（None）で判定できない項目は No=0 とする（安全側）。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, replace
from typing import Optional

from .financials import RawFinancials, compute_metrics

# 健全/不健全のしきい値（仕様書 7章）
HEALTHY_THRESHOLD = 7   # 7以上＝財務健全
UNHEALTHY_THRESHOLD = 3  # 3以下＝不健全


@dataclass
class FScoreItem:
    """Fスコア1項目の採点結果。"""

    number: int          # 項目番号 1〜9
    name: str            # 項目名
    category: str        # 収益性 / 安全性 / 生産性
    passed: bool         # Yes=True(1点) / No=False(0点)
    detail: str          # 判定根拠（値の説明）

    @property
    def score(self) -> int:
        return 1 if self.passed else 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["score"] = self.score
        return d


@dataclass
class FScoreResult:
    """Fスコアの総合結果。"""

    total: int                 # 合計（0〜9）
    items: list[FScoreItem]
    mode: str                  # "actual"（実績版）/ "forecast"（予想版）

    @property
    def is_healthy(self) -> bool:
        return self.total >= HEALTHY_THRESHOLD

    @property
    def is_unhealthy(self) -> bool:
        return self.total <= UNHEALTHY_THRESHOLD

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "mode": self.mode,
            "is_healthy": self.is_healthy,
            "is_unhealthy": self.is_unhealthy,
            "items": [i.to_dict() for i in self.items],
        }


def _gt(a: Optional[float], b: Optional[float]) -> bool:
    """a > b。いずれか欠損なら False（安全側）。"""
    return a is not None and b is not None and a > b


def _lt(a: Optional[float], b: Optional[float]) -> bool:
    """a < b。いずれか欠損なら False。"""
    return a is not None and b is not None and a < b


def _lte(a: Optional[float], b: Optional[float]) -> bool:
    """a <= b。いずれか欠損なら False。"""
    return a is not None and b is not None and a <= b


def compute_fscore(
    latest: RawFinancials,
    prior: RawFinancials,
    mode: str = "actual",
    effective_tax_rate: float = 0.30,
) -> FScoreResult:
    """最新期(latest)と前期(prior)の RawFinancials から Fスコアを算出する。"""

    m_latest = compute_metrics(latest, effective_tax_rate=effective_tax_rate)
    m_prior = compute_metrics(prior, effective_tax_rate=effective_tax_rate)

    items: list[FScoreItem] = []

    # --- 収益性 ---
    # 1. 純利益 > 0
    ni = latest.net_income
    items.append(FScoreItem(
        1, "純利益 > 0", "収益性",
        passed=(ni is not None and ni > 0),
        detail=f"純利益={ni}",
    ))

    # 2. 営業CF > 0
    ocf = latest.operating_cf
    items.append(FScoreItem(
        2, "営業CF > 0", "収益性",
        passed=(ocf is not None and ocf > 0),
        detail=f"営業CF={ocf}",
    ))

    # 3. ROA(最新期) > ROA(前期)（改善）
    items.append(FScoreItem(
        3, "ROA 改善（最新期 > 前期）", "収益性",
        passed=_gt(m_latest.roa, m_prior.roa),
        detail=f"ROA {m_prior.roa} → {m_latest.roa}",
    ))

    # 4. 営業CF > 純利益（利益の質）
    items.append(FScoreItem(
        4, "営業CF > 純利益（利益の質）", "収益性",
        passed=_gt(latest.operating_cf, latest.net_income),
        detail=f"営業CF={latest.operating_cf} vs 純利益={latest.net_income}",
    ))

    # 5. 営業利益率(最新期) > 営業利益率(前期)（改善）
    items.append(FScoreItem(
        5, "営業利益率 改善（最新期 > 前期）", "収益性",
        passed=_gt(m_latest.operating_margin, m_prior.operating_margin),
        detail=f"営業利益率 {m_prior.operating_margin} → {m_latest.operating_margin}",
    ))

    # --- 安全性 ---
    # 6. 有利子負債÷総資産(最新期) < 前期（減少）
    items.append(FScoreItem(
        6, "有利子負債比率 低下（最新期 < 前期）", "安全性",
        passed=_lt(m_latest.debt_to_assets, m_prior.debt_to_assets),
        detail=f"有利子負債÷総資産 {m_prior.debt_to_assets} → {m_latest.debt_to_assets}",
    ))

    # 7. 流動比率(最新期) > 前期（改善）
    items.append(FScoreItem(
        7, "流動比率 改善（最新期 > 前期）", "安全性",
        passed=_gt(m_latest.current_ratio, m_prior.current_ratio),
        detail=f"流動比率 {m_prior.current_ratio} → {m_latest.current_ratio}",
    ))

    # 8. 資本金(最新期) <= 資本金(前期)（増資していない）
    items.append(FScoreItem(
        8, "増資していない（資本金 最新期 <= 前期）", "安全性",
        passed=_lte(latest.capital_stock, prior.capital_stock),
        detail=f"資本金 {prior.capital_stock} → {latest.capital_stock}",
    ))

    # --- 生産性 ---
    # 9. 総資産回転率(最新期) > 前期（改善）
    items.append(FScoreItem(
        9, "総資産回転率 改善（最新期 > 前期）", "生産性",
        passed=_gt(m_latest.total_asset_turnover, m_prior.total_asset_turnover),
        detail=f"総資産回転率 {m_prior.total_asset_turnover} → {m_latest.total_asset_turnover}",
    ))

    total = sum(i.score for i in items)
    return FScoreResult(total=total, items=items, mode=mode)


def build_forecast_snapshot(base: RawFinancials, forecast_overrides: dict) -> RawFinancials:
    """予想版Fスコア用に、最新実績(base)へ予想値を上書きした RawFinancials を作る。

    予想Excel（Forecast）から得られる項目のみ上書きし、CF や BS 明細など予想に無い
    項目は最新実績を引き継ぐ（仕様書 4.2「最新期の値をユーザー予想に差し替えて算出」）。

    forecast_overrides の例:
      {"revenue": 1200, "operating_income": 180, "net_income": 117,
       "ordinary_income": 180, "capital_stock": 100}
    """
    valid = {k: v for k, v in forecast_overrides.items() if hasattr(base, k)}
    return replace(base, **valid)
