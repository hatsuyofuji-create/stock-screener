import numpy as np
import pandas as pd

from config import SpikeConfig
from src.compute.spikes import add_features, detect_spikes


def _bars(n=60, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2026-01-05", periods=n)
    close = 1000 + np.cumsum(rng.normal(0, 2, n))
    df = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                       "close": close, "volume": np.full(n, 10000.0)}, index=dates)
    df.index.name = "date"
    return df


def test_detects_pct_spike():
    df = _bars()
    i = 40
    df.iloc[i, df.columns.get_loc("close")] = df["close"].iloc[i - 1] * 1.10
    out = detect_spikes(df, SpikeConfig())
    assert list(out["date"]) == [df.index[i]]
    assert abs(out["pct"].iloc[0] - 10.0) < 1e-6
    assert "8%" in out["reason"].iloc[0]


def test_detects_volume_spike_only_with_volume():
    df = _bars()
    i = 45
    df.iloc[i, df.columns.get_loc("close")] = df["close"].iloc[i - 1] * 1.06
    assert detect_spikes(df, SpikeConfig()).empty  # 6% だけでは急騰ではない
    df.iloc[i, df.columns.get_loc("volume")] = 50000.0  # 5倍
    out = detect_spikes(df, SpikeConfig())
    assert len(out) == 1
    assert out["vol_ratio"].iloc[0] > 3.0
    assert "出来高" in out["reason"].iloc[0]


def test_forward_returns_and_gap():
    df = _bars()
    i = 20
    prev = df["close"].iloc[i - 1]
    df.iloc[i, df.columns.get_loc("open")] = prev * 1.05
    df.iloc[i, df.columns.get_loc("close")] = prev * 1.09
    df.iloc[i + 5, df.columns.get_loc("close")] = prev * 1.09 * 1.02
    f = add_features(df, SpikeConfig())
    assert abs(f["gap_pct"].iloc[i] - 5.0) < 1e-6
    assert abs(f["fwd_5"].iloc[i] - 2.0) < 1e-6


def test_empty_input():
    assert detect_spikes(pd.DataFrame()).empty
