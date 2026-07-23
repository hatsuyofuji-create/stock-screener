# -*- coding: utf-8 -*-
"""
MockProvider: 鍵なしで動作確認するための擬似データ提供元。

セクターごとに乱数ウォークの「売買代金（円）」を生成する。乱数は固定シード
なので、実行するたびに概ね同じ結果が出る（動作確認・デモに向く）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .provider import DataProvider

# 東証33業種（J-Quants の Sector33CodeName と同じ区分）。デモ用の擬似データ。
_SECTORS = [
    "水産・農林業",
    "鉱業",
    "建設業",
    "食料品",
    "繊維製品",
    "パルプ・紙",
    "化学",
    "医薬品",
    "石油・石炭製品",
    "ゴム製品",
    "ガラス・土石製品",
    "鉄鋼",
    "非鉄金属",
    "金属製品",
    "機械",
    "電気機器",
    "輸送用機器",
    "精密機器",
    "その他製品",
    "電気・ガス業",
    "陸運業",
    "海運業",
    "空運業",
    "倉庫・運輸関連業",
    "情報・通信業",
    "卸売業",
    "小売業",
    "銀行業",
    "証券・商品先物取引業",
    "保険業",
    "その他金融業",
    "不動産業",
    "サービス業",
]

# 各セクターに割り当てるダミー銘柄数
_TICKERS_PER_SECTOR = 3


class MockProvider(DataProvider):
    name = "mock"

    def __init__(self, days: int = 250, seed: int = 42) -> None:
        self.days = days
        self.seed = seed
        self._turnover: pd.DataFrame | None = None
        self._close: pd.DataFrame | None = None
        self._sector: dict[str, str] = {}
        self._build()

    def _build(self) -> None:
        rng = np.random.default_rng(self.seed)
        # 直近 days 営業日ぶんの日付（土日は除く）
        dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=self.days)

        # 進捗 0→1（ゆるやかなトレンドを掛けるための時間軸）
        t = np.linspace(0.0, 1.0, self.days)

        cols: dict[str, np.ndarray] = {}       # 売買代金（円）
        price_cols: dict[str, np.ndarray] = {}  # 終値（円）
        sector_map: dict[str, str] = {}
        code = 1000
        for _s_idx, sector in enumerate(_SECTORS):
            # 業種ごとに規模（基準の売買代金）と、1年での資金の入り／抜けを変える。
            # 売買代金は累積発散しないよう「基準×トレンド×日々のばらつき」で作る。
            base_oku = rng.uniform(60.0, 550.0)   # 1銘柄あたりの基準売買代金（億円）
            drift_total = rng.normal(0.0, 0.35)   # 1年での対数変化（±約35%）
            trend = np.exp(drift_total * t)       # 1.0 → exp(drift_total)
            jitter = 0.13 + rng.random() * 0.06   # 日々のばらつき幅
            # 価格は別のドリフト（買い/売り優勢の方向をデモで出すため）
            price_drift = rng.normal(0.0002, 0.0006)
            price_vol = 0.012 + rng.random() * 0.006
            for _ in range(_TICKERS_PER_SECTOR):
                code += 1
                ticker = str(code)
                noise = np.exp(rng.normal(0.0, jitter, size=self.days))  # 非累積の日次ノイズ
                level = base_oku * 1e8 * trend * noise  # 円ベースの売買代金
                cols[ticker] = level
                rets = rng.normal(price_drift, price_vol, size=self.days)
                price = 1000.0 * np.exp(np.cumsum(rets))  # 終値（累積＝トレンドを持つ）
                price_cols[ticker] = price
                sector_map[ticker] = sector

        self._turnover = pd.DataFrame(cols, index=dates).round(0)
        self._close = pd.DataFrame(price_cols, index=dates).round(2)
        self._sector = sector_map

    def get_turnover_history(self) -> pd.DataFrame:
        assert self._turnover is not None
        return self._turnover.copy()

    def get_close_history(self) -> pd.DataFrame:
        assert self._close is not None
        return self._close.copy()

    def get_sector_map(self) -> dict[str, str]:
        return dict(self._sector)
