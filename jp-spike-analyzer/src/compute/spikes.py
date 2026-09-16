# -*- coding: utf-8 -*-
"""
急騰日の検出。

入力: 日足 DataFrame（index=日付, columns=open/high/low/close/volume/...）
出力: 急騰日ごとの DataFrame
  date, close, pct（前日比%）, gap_pct（寄り付きの前日終値比%）, vol_ratio（出来高/20日平均）,
  high_pct（高値ベースの前日比%）, fwd_5, fwd_20（急騰日終値からN営業日後の終値の変化%）, reason
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import SpikeConfig  # noqa: E402


def add_features(bars: pd.DataFrame, cfg: SpikeConfig) -> pd.DataFrame:
    """日足に pct / gap_pct / vol_ratio / high_pct / fwd_N 列を足して返す。"""
    df = bars.copy().sort_index()
    prev_close = df["close"].shift(1)
    df["pct"] = (df["close"] / prev_close - 1.0) * 100.0
    df["gap_pct"] = (df["open"] / prev_close - 1.0) * 100.0 if "open" in df else np.nan
    df["high_pct"] = (df["high"] / prev_close - 1.0) * 100.0 if "high" in df else np.nan
    if "volume" in df:
        avg = df["volume"].shift(1).rolling(cfg.vol_window, min_periods=max(5, cfg.vol_window // 2)).mean()
        df["vol_ratio"] = df["volume"] / avg
    else:
        df["vol_ratio"] = np.nan
    for n in cfg.forward_days:
        df[f"fwd_{n}"] = (df["close"].shift(-n) / df["close"] - 1.0) * 100.0
    return df


def detect_spikes(bars: pd.DataFrame, cfg: SpikeConfig | None = None) -> pd.DataFrame:
    """急騰日を抽出する。

    判定:
      - pct >= cfg.pct
      - または pct >= cfg.pct_with_volume かつ vol_ratio >= cfg.vol_ratio
    """
    cfg = cfg or SpikeConfig()
    if bars is None or bars.empty or "close" not in bars:
        return pd.DataFrame(columns=["date", "close", "pct", "gap_pct", "high_pct", "vol_ratio", "reason"])
    df = add_features(bars, cfg)
    by_pct = df["pct"] >= cfg.pct
    by_vol = (df["pct"] >= cfg.pct_with_volume) & (df["vol_ratio"] >= cfg.vol_ratio)
    hit = df[by_pct | by_vol].copy()
    hit["reason"] = np.where(
        by_pct[hit.index], f"前日比{cfg.pct:g}%以上", f"前日比{cfg.pct_with_volume:g}%以上＋出来高{cfg.vol_ratio:g}倍以上"
    )
    cols = ["close", "pct", "gap_pct", "high_pct", "vol_ratio", "reason"] + [f"fwd_{n}" for n in cfg.forward_days]
    out = hit[cols].reset_index().rename(columns={"index": "date"})
    if "date" not in out.columns:  # index 名が date だった場合
        out = out.rename(columns={bars.index.name or "index": "date"})
    return out.sort_values("date", ascending=False).reset_index(drop=True)
