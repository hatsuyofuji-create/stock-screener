"""適正株価・安全域＋業績予想シナリオ計算エンジン（仕様書 4.3 / 4〜6章・ツール⑤）。

構成:
- Park24 型シナリオ計算（STEP1）：売上・営業利益率・配当性向・一時損益から
  芋づる式に EPS/BPS/DPS/ROE を導出する。base / negative の2シナリオ。
- マルチプル法による適正株価（PER / PBR / 配当利回り基準）と安全域。
- 2シナリオからアップサイド／ダウンサイド／リスクリワード比。
- 妥当倍率（本質的価値の閾値）のデフォルト提案（過去平均 / 同業中央値、構造的割引 /
  一時的回帰）。

DB 非依存の純粋関数。金額の単位は入力側で統一すること。
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, asdict
from typing import Optional

# Park24 モデルの実効税率（仕様書 4.3 / 7章：純利益 = 営業利益 × 0.65）
PARK24_TAX_RATE = 0.35


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


# ----------------------------------------------------------------------------
# Park24 型 業績予想シナリオ計算（STEP1）
# ----------------------------------------------------------------------------

@dataclass
class ScenarioInputs:
    """1シナリオ分の予想入力（仕様書 4.3 STEP1）。"""

    scenario: str = "base"                 # base / negative
    revenue: Optional[float] = None        # 予想売上高
    operating_margin: Optional[float] = None  # 予想営業利益率
    payout_ratio: Optional[float] = None   # 配当性向（DPS を直接入力しない場合）
    dps: Optional[float] = None            # DPS を直接指定する場合
    one_time_items: float = 0.0            # 一時損益（減損など。純利益から差し引く正の値）
    effective_tax_rate: float = PARK24_TAX_RATE
    shares_outstanding: Optional[float] = None  # 発行済株式数
    prior_bps: Optional[float] = None      # 前期BPS（BPS 算出用）
    # 発行済株式数が無い場合のフォールバック（基準期からの比例スケール）
    base_net_income: Optional[float] = None
    base_eps: Optional[float] = None


@dataclass
class ScenarioResult:
    """シナリオ計算の結果（予想 EPS/BPS/DPS/ROE 等）。"""

    scenario: str
    operating_income: Optional[float] = None  # 営業利益
    net_income: Optional[float] = None         # 純利益
    eps: Optional[float] = None                # 予想EPS
    dps: Optional[float] = None                # 予想DPS
    bps: Optional[float] = None                # 予想BPS
    roe: Optional[float] = None                # 予想ROE（EPS ÷ 平均BPS）

    def to_dict(self) -> dict:
        return asdict(self)


def project_scenario(inp: ScenarioInputs) -> ScenarioResult:
    """Park24 型で予想 EPS/BPS/DPS/ROE を算出する（仕様書 4.3 STEP1）。

    営業利益 = 売上高 × 営業利益率
    純利益   = 営業利益 ×(1 − 実効税率) − 一時損益
    EPS      = 純利益 ÷ 発行済株式数（無ければ基準期からの比例スケール）
    DPS      = EPS × 配当性向（または直接入力）
    BPS      = 前期BPS + EPS − DPS
    ROE      = EPS ÷ 平均BPS(前期, 当期)
    """
    operating_income: Optional[float] = None
    if inp.revenue is not None and inp.operating_margin is not None:
        operating_income = inp.revenue * inp.operating_margin

    net_income: Optional[float] = None
    if operating_income is not None:
        net_income = operating_income * (1.0 - inp.effective_tax_rate) - (inp.one_time_items or 0.0)

    # EPS
    eps: Optional[float] = None
    if net_income is not None:
        if inp.shares_outstanding:
            eps = net_income / inp.shares_outstanding
        elif inp.base_net_income and inp.base_eps and inp.base_net_income != 0:
            # 株式数が無い場合、基準期の純利益比で EPS をスケール
            eps = inp.base_eps * (net_income / inp.base_net_income)

    # DPS
    dps: Optional[float] = None
    if inp.dps is not None:
        dps = inp.dps
    elif inp.payout_ratio is not None and eps is not None:
        dps = eps * inp.payout_ratio

    # BPS = 前期BPS + EPS − DPS
    bps: Optional[float] = None
    if inp.prior_bps is not None and eps is not None and dps is not None:
        bps = inp.prior_bps + eps - dps

    # ROE = EPS ÷ 平均BPS(前期, 当期)
    roe: Optional[float] = None
    if eps is not None and inp.prior_bps is not None and bps is not None:
        avg_bps = (inp.prior_bps + bps) / 2.0
        roe = _safe_div(eps, avg_bps)

    return ScenarioResult(
        scenario=inp.scenario,
        operating_income=operating_income,
        net_income=net_income,
        eps=eps,
        dps=dps,
        bps=bps,
        roe=roe,
    )


# ----------------------------------------------------------------------------
# マルチプル法による適正株価・安全域
# ----------------------------------------------------------------------------

@dataclass
class FairValue:
    """マルチプル法による適正株価と安全域（仕様書 4.3）。"""

    method: str                      # per / pbr / dividend
    fair_price: Optional[float]      # 適正株価
    margin_of_safety: Optional[float]  # 安全域％ = (適正株価 − 現在株価) ÷ 適正株価

    def to_dict(self) -> dict:
        return asdict(self)


def margin_of_safety(fair_price: Optional[float], current_price: Optional[float]) -> Optional[float]:
    """安全域％ = (適正株価 − 現在株価) ÷ 適正株価。負値（割高）も正しく扱う。"""
    if fair_price is None or current_price is None or fair_price == 0:
        return None
    return (fair_price - current_price) / fair_price


def fair_value_per(eps: Optional[float], fair_per: Optional[float],
                   current_price: Optional[float] = None) -> FairValue:
    """適正株価(PER基準) = 予想EPS × 妥当PER。"""
    fair = eps * fair_per if eps is not None and fair_per is not None else None
    return FairValue("per", fair, margin_of_safety(fair, current_price))


def fair_value_pbr(bps: Optional[float], fair_pbr: Optional[float],
                   current_price: Optional[float] = None) -> FairValue:
    """適正株価(PBR基準) = 予想BPS × 妥当PBR。"""
    fair = bps * fair_pbr if bps is not None and fair_pbr is not None else None
    return FairValue("pbr", fair, margin_of_safety(fair, current_price))


def fair_value_dividend(dps: Optional[float], fair_yield: Optional[float],
                        current_price: Optional[float] = None) -> FairValue:
    """適正株価(配当利回り基準) = 予想DPS ÷ 妥当配当利回り。"""
    fair = _safe_div(dps, fair_yield)
    return FairValue("dividend", fair, margin_of_safety(fair, current_price))


# ----------------------------------------------------------------------------
# 2シナリオ（レンジ）とリスクリワード
# ----------------------------------------------------------------------------

@dataclass
class RiskReward:
    """アップサイド／ダウンサイド／リスクリワード比（仕様書 4.3）。"""

    upside: Optional[float]         # (base適正株価 − 現在株価) ÷ 現在株価
    downside: Optional[float]       # (negative適正株価 − 現在株価) ÷ 現在株価
    risk_reward: Optional[float]    # アップサイド％ ÷ |ダウンサイド％|
    verdict: str                    # "損小利大" / "損大利小" / "判定不能"

    def to_dict(self) -> dict:
        return asdict(self)


def risk_reward(base_fair: Optional[float], negative_fair: Optional[float],
                current_price: Optional[float]) -> RiskReward:
    """2シナリオの適正株価と現在株価からリスクリワードを算出する。"""
    upside = _safe_div((base_fair - current_price) if base_fair is not None and current_price is not None else None,
                       current_price)
    downside = _safe_div((negative_fair - current_price) if negative_fair is not None and current_price is not None else None,
                         current_price)

    rr: Optional[float] = None
    verdict = "判定不能"
    if upside is not None and downside is not None and downside != 0:
        rr = upside / abs(downside)
        # 損小利大か？（リスクリワード比 > 1 で「損小利大」）
        verdict = "損小利大" if rr > 1 else "損大利小"
    return RiskReward(upside=upside, downside=downside, risk_reward=rr, verdict=verdict)


# ----------------------------------------------------------------------------
# 妥当倍率（本質的価値の閾値）の提案
# ----------------------------------------------------------------------------

def suggest_multiple(
    values: list[float],
    method: str = "median",
    adjustment: Optional[str] = None,
    factor: float = 0.8,
) -> Optional[float]:
    """妥当倍率のデフォルトを提案する（仕様書 4.3）。

    - method="mean"：対象企業の過去平均、"median"：同業他社の中央値。
    - adjustment="structural"：割安が構造的 → 過去平均から factor 分割り引く。
      adjustment="temporary"：一時的 → 過去平均に回帰（調整なし）。
    """
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    base = statistics.mean(clean) if method == "mean" else statistics.median(clean)
    if adjustment == "structural":
        return base * factor
    return base
