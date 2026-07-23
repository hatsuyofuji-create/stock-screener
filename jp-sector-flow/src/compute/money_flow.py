# -*- coding: utf-8 -*-
"""
セクター資金フロー（売買代金 ＋ 価格の方向）の計算。

考え方（表示専用・売買判断はしない）:
  1. 各銘柄の「売買代金（円）」を業種ごとに合計 → 業種の売買代金（＝活発さ）。億円換算。
  2. 売買代金は買い・売り両方の合計なので方向は分からない。方向は価格（終値）で見る：
     業種の等ウェイト株価指数の変化率を、15日・30日・150日の3期間で出す。
     プラス＝買い優勢🟢／マイナス＝売り優勢🔴。
  3. 「活発（売買代金 大）× 買い優勢（価格 上昇）」＝本当の資金流入と読める。
"""

from __future__ import annotations

import pandas as pd

HORIZONS = [15, 30, 150]  # 価格の方向を測る営業日数
SMOOTH_DAYS = 5           # 売買代金の移動平均日数（生成物の保存用）
_OKU = 1e8                # 円 → 億円


def _sector_price_index(close: pd.DataFrame, codes: list[str]) -> pd.Series | None:
    """業種内の銘柄を先頭=100 に正規化して等ウェイト平均した株価指数を返す。"""
    cols = [c for c in codes if c in close.columns]
    if not cols:
        return None
    sub = close[cols]
    first = sub.apply(lambda col: col.dropna().iloc[0] if col.notna().any() else pd.NA)
    idx = (sub.divide(first) * 100.0).mean(axis=1, skipna=True).dropna()
    return idx if len(idx) >= 2 else None


def _pct_change(idx: pd.Series, days: int) -> float:
    """株価指数の直近 days 営業日の変化率(%)。データが足りなければ最古との比較。"""
    past = idx.iloc[-(days + 1)] if len(idx) > days else idx.iloc[0]
    return round(float((idx.iloc[-1] / past - 1.0) * 100.0), 2)


def compute(
    turnover: pd.DataFrame,
    sector_map: dict[str, str],
    close: pd.DataFrame | None = None,
) -> dict:
    """
    turnover: 日付 × 銘柄コードの売買代金（円）
    close:    日付 × 銘柄コードの終値（価格の方向＝買い/売りの判定用）
    sector_map: 銘柄コード -> 業種名

    戻り値 dict:
      - "flow": DataFrame（日付 × 業種の売買代金[億円]・5日移動平均。保存用）
      - "ranking": DataFrame（rank, sector, turnover[億円], price_mom_15/30/150[%]）
      - "monthly": DataFrame（month, tri[兆円], days, partial。保存用）
      - "asof": 最終営業日（Timestamp）
    """
    if turnover.empty:
        raise ValueError("売買代金データが空です。")

    turnover = turnover.sort_index()

    # 業種ごとの列集合
    sectors: dict[str, list[str]] = {}
    for code in turnover.columns:
        sec = sector_map.get(str(code))
        if sec:
            sectors.setdefault(sec, []).append(code)
    if not sectors:
        raise ValueError("業種対応が空です（sector_map を確認）。")

    # 業種ごとの日次売買代金（円）→ 億円 → 5日移動平均（保存用）
    data = {sec: turnover[codes].sum(axis=1, skipna=True) for sec, codes in sectors.items()}
    flow_oku = pd.DataFrame(data).sort_index() / _OKU
    flow_ma = flow_oku.rolling(SMOOTH_DAYS, min_periods=1).mean()

    # ランキング: 直近の売買代金（億円）が大きい順
    latest = flow_ma.iloc[-1]
    ranking = (
        pd.DataFrame({"sector": latest.index, "turnover": latest.values})
        .sort_values("turnover", ascending=False)
        .reset_index(drop=True)
    )
    ranking.insert(0, "rank", range(1, len(ranking) + 1))
    ranking["turnover"] = ranking["turnover"].round(1)

    # 価格の方向（15日・30日・150日の変化率）
    close = close.sort_index() if (close is not None and not close.empty) else None
    pidx = {}
    if close is not None:
        pidx = {sec: _sector_price_index(close, codes) for sec, codes in sectors.items()}
    for d in HORIZONS:
        ranking[f"price_mom_{d}"] = ranking["sector"].map(
            lambda s, d=d: _pct_change(pidx[s], d) if pidx.get(s) is not None else None
        )

    # 全業種合計の月次売買代金（兆円）。生の売買代金（円）から集計（保存用）
    total_yen = turnover.sum(axis=1)
    grp = total_yen.groupby(total_yen.index.to_period("M"))
    monthly = pd.DataFrame({"tri": (grp.sum() / 1e12).round(2), "days": grp.count().astype(int)})
    monthly.index = monthly.index.astype(str)
    monthly = monthly.reset_index(names="month")
    monthly["partial"] = False
    if len(monthly):
        monthly.loc[monthly.index[-1], "partial"] = True

    return {
        "flow": flow_ma.round(1),
        "ranking": ranking,
        "monthly": monthly,
        "asof": flow_ma.index[-1],
    }
