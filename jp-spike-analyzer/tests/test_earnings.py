import pandas as pd

from src.compute.earnings import evaluate
from src.data.jquants import STATEMENT_COLUMNS


def _row(date, doc, period, fy_end, op=None, fop=None, sales=None, nxt=None):
    r = {c: None for c in STATEMENT_COLUMNS}
    r.update({"disclosed_date": pd.Timestamp(date), "disclosed_time": "15:00", "doc_type": doc, "period": period,
              "fy_end": pd.Timestamp(fy_end), "operating_profit": op, "forecast_operating_profit": fop,
              "net_sales": sales, "next_fy_forecast_operating_profit": nxt})
    return r


def _df(rows):
    df = pd.DataFrame(rows, columns=STATEMENT_COLUMNS)
    for c in STATEMENT_COLUMNS[5:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def test_good_quarter_with_upward_revision():
    df = _df([
        _row("2025-11-05", "2QFinancialStatements_Consolidated_JP", "2Q", "2026-03-31", op=100e8, fop=200e8),
        _row("2026-08-05", "1QFinancialStatements_Consolidated_JP", "1Q", "2027-03-31", op=60e8, fop=220e8),
        _row("2026-11-05", "2QFinancialStatements_Consolidated_JP", "2Q", "2027-03-31", op=130e8, fop=240e8),
    ])
    ev = evaluate(df, 2)
    assert ev["kind"] == "決算" and ev["label"] == "好決算"
    assert round(ev["metrics"]["profit_yoy_pct"]) == 30
    assert round(ev["metrics"]["progress_pct"]) == 54
    assert round(ev["metrics"]["forecast_change_pct"], 1) == 9.1
    assert any("上方修正" in d for d in ev["details"])


def test_bad_quarter():
    df = _df([
        _row("2025-08-05", "1QFinancialStatements_Consolidated_JP", "1Q", "2026-03-31", op=100e8, fop=400e8),
        _row("2026-08-05", "1QFinancialStatements_Consolidated_JP", "1Q", "2027-03-31", op=70e8, fop=400e8),
    ])
    ev = evaluate(df, 1)
    assert ev["label"] == "悪決算"
    assert round(ev["metrics"]["profit_yoy_pct"]) == -30


def test_forecast_revision_rows():
    df = _df([
        _row("2026-05-10", "FYFinancialStatements_Consolidated_JP", "FY", "2026-03-31", op=300e8, fop=300e8, nxt=330e8),
        _row("2026-05-10", "FYFinancialStatements_Consolidated_JP", "FY", "2027-03-31", fop=330e8),
        _row("2026-09-01", "EarnForecastRevision", "", "2027-03-31", fop=300e8),
    ])
    ev = evaluate(df, 2)
    assert ev["label"] == "下方修正"
    assert round(ev["metrics"]["forecast_change_pct"], 1) == -9.1
    fy = evaluate(df, 0)
    assert fy["label"] == "好決算" and round(fy["metrics"]["next_fy_guidance_pct"]) == 10


def test_no_history_is_neutral():
    df = _df([_row("2026-08-05", "1QFinancialStatements_Consolidated_JP", "1Q", "2027-03-31", op=60e8, fop=300e8)])
    ev = evaluate(df, 0)
    assert ev["label"] in ("決算（並）", "悪決算")  # 進捗 20% なので弱め
    assert ev["metrics"]["profit_yoy_pct"] is None
