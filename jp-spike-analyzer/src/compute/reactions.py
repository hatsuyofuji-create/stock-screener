# -*- coding: utf-8 -*-
"""
決算（決算短信・業績予想修正・配当予想修正）ごとに、株価がどう反応したかを計算する。

反応日の決め方:
  - 発表時刻が 15:00 より前 → 発表日当日（休場日なら次の営業日）
  - 15:00 以降           → 次の営業日
指標（すべて「反応日の前営業日の終値」を基準にした変化率）:
  react_pct  反応日の終値
  gap_pct    反応日の寄り付き
  high_pct   反応日の高値
  low_pct    反応日の安値
  fwd_5 / fwd_20  反応日から 5 / 20 営業日後の終値
  vol_ratio  反応日の出来高 ÷ 直近20日平均（反応日の前日まで）
  topix_pct  反応日の TOPIX（代用 ETF）騰落、relative_pct = react_pct - topix_pct
"""

from __future__ import annotations

import pandas as pd

from . import earnings

VOL_WINDOW = 20
FORWARD_DAYS = (5, 20)

GOOD = {"好決算", "上方修正", "増配"}
BAD = {"悪決算", "下方修正", "減配"}


def reaction_day(trading_days: pd.DatetimeIndex, disclosed_date: pd.Timestamp, disclosed_time: str) -> pd.Timestamp | None:
    """発表日と時刻から反応日（営業日）を返す。日足の範囲外なら None。"""
    d = pd.Timestamp(disclosed_date).normalize()
    t = str(disclosed_time or "").strip()
    before_close = bool(t) and t[:5] < "15:00"
    if before_close:
        pos = trading_days.searchsorted(d, side="left")   # d 以降の最初の営業日
    else:
        pos = trading_days.searchsorted(d, side="right")  # d より後の最初の営業日
    if pos >= len(trading_days) or pos == 0:
        return None
    return trading_days[pos]


def _pct(a, b):
    if a is None or b is None or pd.isna(a) or pd.isna(b) or float(b) == 0:
        return None
    return round((float(a) / float(b) - 1.0) * 100.0, 2)


def build_events(statements: pd.DataFrame, bars: pd.DataFrame, topix: pd.Series | None = None,
                 *, include_dividend: bool = True) -> list[dict]:
    """決算ごとの評価と株価反応をまとめた dict のリスト（新しい順）。"""
    if statements is None or statements.empty or bars is None or bars.empty:
        return []
    st = statements.sort_values(["disclosed_date", "disclosed_time"]).reset_index(drop=True)
    bars = bars.sort_index()
    days = pd.DatetimeIndex(bars.index).normalize()
    close = bars["close"]
    vol_avg = bars["volume"].shift(1).rolling(VOL_WINDOW, min_periods=5).mean() if "volume" in bars else None
    topix_pct = (topix.sort_index().pct_change() * 100.0) if topix is not None and len(topix) else None

    out: list[dict] = []
    for i in range(len(st)):
        row = st.iloc[i]
        kind = earnings.kind_of(row.get("doc_type", ""))
        if kind == "その他" or (kind == "配当修正" and not include_dividend):
            continue
        rd = reaction_day(days, row["disclosed_date"], row.get("disclosed_time"))
        if rd is None:
            continue
        pos = days.get_loc(rd)
        prev_close = float(close.iloc[pos - 1])
        ev = earnings.evaluate(st, i)
        b = bars.iloc[pos]
        rec = {
            "disclosed_date": pd.Timestamp(row["disclosed_date"]).strftime("%Y-%m-%d"),
            "disclosed_time": str(row.get("disclosed_time") or "")[:5],
            "reaction_date": rd.strftime("%Y-%m-%d"),
            "kind": ev["kind"],
            "period": str(row.get("period") or ""),
            "fy_end": "" if pd.isna(row.get("fy_end")) else pd.Timestamp(row["fy_end"]).strftime("%Y-%m"),
            "label": ev["label"],
            "score": ev["score"],
            "details": ev["details"],
            "metrics": {k: (None if v is None or pd.isna(v) else float(v)) for k, v in ev["metrics"].items()},
            "prev_close": prev_close,
            "close": float(b["close"]),
            "react_pct": _pct(b["close"], prev_close),
            "gap_pct": _pct(b.get("open"), prev_close),
            "high_pct": _pct(b.get("high"), prev_close),
            "low_pct": _pct(b.get("low"), prev_close),
            "vol_ratio": None if vol_avg is None or pd.isna(vol_avg.iloc[pos]) or vol_avg.iloc[pos] == 0
            else round(float(b["volume"]) / float(vol_avg.iloc[pos]), 2),
        }
        for n in FORWARD_DAYS:
            rec[f"fwd_{n}"] = _pct(close.iloc[pos + n], prev_close) if pos + n < len(close) else None
        tp = float(topix_pct.get(rd)) if topix_pct is not None and rd in topix_pct.index else None
        rec["topix_pct"] = None if tp is None or pd.isna(tp) else round(tp, 2)
        rec["relative_pct"] = None if rec["topix_pct"] is None or rec["react_pct"] is None else round(rec["react_pct"] - rec["topix_pct"], 2)
        out.append(rec)
    out.sort(key=lambda r: (r["disclosed_date"], r["disclosed_time"]), reverse=True)
    return out


def summarize(events: list[dict]) -> list[dict]:
    """評価ラベルごとの反応の傾向（回数・翌日上昇回数・平均）。"""
    groups: dict[str, list[dict]] = {}
    for e in events:
        groups.setdefault(e["label"], []).append(e)
    order = ["好決算", "決算（並）", "悪決算", "上方修正", "業績修正（据え置き）", "下方修正", "業績修正", "増配", "配当修正（据え置き）", "減配", "配当修正"]
    rows = []
    for label in sorted(groups, key=lambda l: order.index(l) if l in order else 99):
        g = [e for e in groups[label] if e["react_pct"] is not None]
        if not g:
            continue

        def avg(key):
            vals = [e[key] for e in g if e.get(key) is not None]
            return None if not vals else round(sum(vals) / len(vals), 2)

        rows.append({
            "label": label, "n": len(g),
            "n_up": sum(1 for e in g if e["react_pct"] > 0),
            "avg_react": avg("react_pct"), "avg_gap": avg("gap_pct"),
            "avg_fwd_5": avg("fwd_5"), "avg_fwd_20": avg("fwd_20"),
            "avg_relative": avg("relative_pct"),
        })
    return rows
