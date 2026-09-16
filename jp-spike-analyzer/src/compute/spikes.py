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

    判定: 前日終値 → 当日終値（翌営業日終値）の変化率 pct が
      急騰: cfg.pct % 以上 / 急落: -cfg.drop_pct % 以下（cfg.direction で up / down / both）。
    出来高倍率・寄付ギャップは表示用に併記するだけで、判定には使わない。
    """
    cfg = cfg or SpikeConfig()
    if bars is None or bars.empty or "close" not in bars:
        return pd.DataFrame(columns=["date", "close", "pct", "gap_pct", "high_pct", "vol_ratio", "direction", "reason"])
    df = add_features(bars, cfg)
    up = df["pct"] >= cfg.pct
    down = df["pct"] <= -cfg.drop_pct
    if cfg.direction == "up":
        mask = up
    elif cfg.direction == "down":
        mask = down
    else:
        mask = up | down
    hit = df[mask].copy()
    hit["direction"] = np.where(hit["pct"] >= 0, "up", "down")
    hit["reason"] = np.where(hit["pct"] >= 0, f"前日終値比+{cfg.pct:g}%以上", f"前日終値比-{cfg.drop_pct:g}%以下")
    cols = ["close", "pct", "gap_pct", "high_pct", "vol_ratio", "direction", "reason"] + [f"fwd_{n}" for n in cfg.forward_days]
    out = hit[cols].reset_index().rename(columns={"index": "date"})
    if "date" not in out.columns:  # index 名が date だった場合
        out = out.rename(columns={bars.index.name or "index": "date"})
    return out.sort_values("date", ascending=False).reset_index(drop=True)
