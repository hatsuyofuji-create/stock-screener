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


def test_volume_alone_is_not_a_spike():
    df = _bars()
    i = 45
    df.iloc[i, df.columns.get_loc("close")] = df["close"].iloc[i - 1] * 1.06
    df.iloc[i, df.columns.get_loc("volume")] = 50000.0  # 出来高5倍でも 6% では急騰ではない
    assert detect_spikes(df, SpikeConfig()).empty
    df.iloc[i, df.columns.get_loc("close")] = df["close"].iloc[i - 1] * 1.08  # ちょうど 8% は急騰
    out = detect_spikes(df, SpikeConfig())
    assert len(out) == 1
    assert out["vol_ratio"].iloc[0] > 3.0  # 表示用に併記される


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


def test_down_and_both_directions():
    df = _bars()
    i, j = 20, 40
    c = df.columns.get_loc("close")
    df.iloc[i:, c] = df["close"].iloc[i:] * 0.90  # i 日目に -10% して、その水準が続く
    df.iloc[j:, c] = df["close"].iloc[j:] * 1.10  # j 日目に +10%
    assert list(detect_spikes(df, SpikeConfig(direction="up"))["date"]) == [df.index[j]]
    down = detect_spikes(df, SpikeConfig(direction="down"))
    assert list(down["date"]) == [df.index[i]] and down["direction"].iloc[0] == "down"
    both = detect_spikes(df, SpikeConfig(direction="both"))
    assert set(both["direction"]) == {"up", "down"} and len(both) == 2
    assert detect_spikes(df, SpikeConfig(direction="down", drop_pct=12.0)).empty
