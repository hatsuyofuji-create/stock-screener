import numpy as np
import pandas as pd

from src.compute.reactions import build_events, reaction_day, summarize
from src.data.jquants import STATEMENT_COLUMNS


def _bars():
    dates = pd.bdate_range("2026-01-05", periods=60)
    close = np.full(60, 1000.0)
    close[10:] = 1080.0   # 1/19 に +8%
    close[15:] = 1100.0
    close[30:] = 1200.0
    df = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
                       "volume": np.full(60, 1000.0)}, index=dates)
    df.iloc[10, df.columns.get_loc("open")] = 1050.0
    df.iloc[10, df.columns.get_loc("volume")] = 5000.0
    df.index.name = "date"
    return df


def _st(rows):
    df = pd.DataFrame(rows, columns=STATEMENT_COLUMNS)
    for c in STATEMENT_COLUMNS[5:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def test_reaction_day_rule():
    days = pd.bdate_range("2026-01-05", periods=10)
    assert reaction_day(days, pd.Timestamp("2026-01-07"), "15:30") == pd.Timestamp("2026-01-08")
    assert reaction_day(days, pd.Timestamp("2026-01-07"), "13:00") == pd.Timestamp("2026-01-07")
    assert reaction_day(days, pd.Timestamp("2026-01-10"), "15:30") == pd.Timestamp("2026-01-12")  # 土曜発表→月曜
    assert reaction_day(days, pd.Timestamp("2026-01-30"), "15:30") is None  # 範囲外


def test_build_events_metrics():
    bars = _bars()
    st = _st([
        {"disclosed_date": pd.Timestamp("2025-01-16"), "disclosed_time": "15:00", "doc_type": "3QFinancialStatements_Consolidated_JP",
         "period": "3Q", "fy_end": pd.Timestamp("2025-03-31"), "operating_profit": 100e8, "forecast_operating_profit": 130e8},
        {"disclosed_date": pd.Timestamp("2026-01-16"), "disclosed_time": "15:00", "doc_type": "3QFinancialStatements_Consolidated_JP",
         "period": "3Q", "fy_end": pd.Timestamp("2026-03-31"), "operating_profit": 120e8, "forecast_operating_profit": 140e8},
    ])
    topix = pd.Series(np.linspace(2000, 2010, 60), index=bars.index)
    ev = build_events(st, bars, topix)
    assert len(ev) == 1  # 2025 年の行は日足の範囲外なので反応は計算しない（前年同期比の比較にだけ使う）
    e = ev[0]
    assert e["reaction_date"] == "2026-01-19" and e["label"] == "好決算"
    assert e["react_pct"] == 8.0 and e["gap_pct"] == 5.0 and e["vol_ratio"] == 5.0
    assert e["fwd_5"] == 10.0 and e["fwd_20"] == 20.0
    assert e["topix_pct"] is not None and abs(e["relative_pct"] - (8.0 - e["topix_pct"])) < 1e-9
    s = summarize(ev)
    assert s[0]["label"] == "好決算" and s[0]["n"] == 1 and s[0]["n_up"] == 1 and s[0]["avg_react"] == 8.0


def test_dividend_toggle():
    bars = _bars()
    st = _st([
        {"disclosed_date": pd.Timestamp("2026-01-16"), "disclosed_time": "15:00", "doc_type": "DividendForecastRevision",
         "period": "", "fy_end": pd.Timestamp("2026-03-31"), "forecast_dividend_annual": 50.0},
    ])
    assert len(build_events(st, bars, None, include_dividend=True)) == 1
    assert build_events(st, bars, None, include_dividend=False) == []
