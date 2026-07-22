# -*- coding: utf-8 -*-
"""
セクター資金フロー（売買代金ベース）の計算。

考え方（表示専用・売買判断はしない）:
  1. 各銘柄の「売買代金（円）」を業種ごとに合計し、業種の日次売買代金を作る。
  2. 見やすさのため 億円 に換算し、5営業日の移動平均で均す（日々の振れを緩和）。
  3. 金額の大きい業種＝実際に多くのお金が売買されている＝資金が入っている、と読む。
  4. 直近 MOMENTUM_DAYS 日の売買代金の変化率で「勢い」を出す（増加＝資金が入りつつある）。
"""

from __future__ import annotations

import pandas as pd

MOMENTUM_DAYS = 5  # 資金フローの勢いを測る日数
SMOOTH_DAYS = 5    # 表示用の移動平均日数（売買代金は日々の振れが大きいため）
_OKU = 1e8         # 円 → 億円


def compute(turnover: pd.DataFrame, sector_map: dict[str, str]) -> dict:
    """
    turnover: 日付 × 銘柄コードの売買代金（円）テーブル
    sector_map: 銘柄コード -> 業種名

    戻り値 dict:
      - "flow": DataFrame（index=日付, columns=業種, values=売買代金[億円]・5日移動平均）
      - "ranking": DataFrame（rank, sector, turnover[億円], momentum[%]）
      - "monthly": DataFrame（month, tri[兆円], days, partial）… 全業種合計の月次
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

    # 業種ごとの日次売買代金（円）→ 億円
    data: dict[str, pd.Series] = {}
    for sec, codes in sectors.items():
        data[sec] = turnover[codes].sum(axis=1, skipna=True)
    flow_oku = pd.DataFrame(data).sort_index() / _OKU

    # 表示用に移動平均で均す
    flow_ma = flow_oku.rolling(SMOOTH_DAYS, min_periods=1).mean()

    # ランキング: 直近の売買代金（億円）が大きい順
    latest = flow_ma.iloc[-1]
    past = flow_ma.iloc[-(MOMENTUM_DAYS + 1)] if len(flow_ma) > MOMENTUM_DAYS else flow_ma.iloc[0]
    momentum = (latest / past - 1.0) * 100.0

    ranking = (
        pd.DataFrame(
            {"sector": latest.index, "turnover": latest.values, "momentum": momentum.values}
        )
        .sort_values("turnover", ascending=False)
        .reset_index(drop=True)
    )
    ranking.insert(0, "rank", range(1, len(ranking) + 1))
    ranking["turnover"] = ranking["turnover"].round(1)
    ranking["momentum"] = ranking["momentum"].round(2)

    # 全業種合計の月次売買代金（兆円）。生の売買代金（円）から集計する。
    total_yen = turnover.sum(axis=1)
    grp = total_yen.groupby(total_yen.index.to_period("M"))
    monthly = pd.DataFrame({"tri": (grp.sum() / 1e12).round(2), "days": grp.count().astype(int)})
    monthly.index = monthly.index.astype(str)
    monthly = monthly.reset_index(names="month")
    monthly["partial"] = False
    if len(monthly):
        monthly.loc[monthly.index[-1], "partial"] = True  # 最新月は途中の可能性あり

    return {
        "flow": flow_ma.round(1),
        "ranking": ranking,
        "monthly": monthly,
        "asof": flow_ma.index[-1],
    }
