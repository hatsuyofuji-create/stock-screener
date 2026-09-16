# -*- coding: utf-8 -*-
"""
決算・業績予想修正・配当予想修正の数値評価。

J-Quants /fins/summary の行を、同じ会社の過去の行と比べて
「好決算 / 並 / 悪決算 / 上方修正 / 下方修正 / 増配 / 減配」を判定し、根拠の数字を文章にする。

比較の考え方（点数は営業利益 OP を軸にする。OP が無い業種は経常利益で代用）:
  - 前年同期比:   同じ期種別（1Q/2Q/3Q/FY）で決算期末が1年前の行と比べる（売上・営業・経常・純利益）
  - 進捗率:       四半期の累計 OP ÷ その時点の通期予想 OP（1Q 25% / 2Q 50% / 3Q 75% が目安）
  - 予想の修正:   通期予想を、同じ決算期の直前の行の通期予想と比べる
  - 通期の着地:   FY 行の実績 OP を、直前の通期予想と比べる（上振れ / 下振れ）
  - 来期予想:     FY 行の来期予想 OP を、今期実績と比べる
  - 配当:         年間配当予想を、同じ決算期の直前の行と比べる
"""

from __future__ import annotations

import pandas as pd

EXPECTED_PROGRESS = {"1Q": 0.25, "2Q": 0.50, "3Q": 0.75}

# 表示名と、実績・通期予想・来期予想の列名
FIELDS = [
    ("売上", "net_sales", "forecast_sales", "next_fy_forecast_sales"),
    ("営業利益", "operating_profit", "forecast_operating_profit", "next_fy_forecast_operating_profit"),
    ("経常利益", "ordinary_profit", "forecast_ordinary_profit", "next_fy_forecast_ordinary_profit"),
    ("純利益", "profit", "forecast_profit", "next_fy_forecast_profit"),
]


def oku(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{float(v) / 1e8:,.0f}億円"


def _pct(a, b):
    """a が b に対して何%か（比率-1）。b が 0 以下や欠損なら None。"""
    if a is None or b is None or pd.isna(a) or pd.isna(b) or float(b) <= 0:
        return None
    return (float(a) / float(b) - 1.0) * 100.0


def _num(v):
    return None if v is None or pd.isna(v) else float(v)


def _profit_col(statements: pd.DataFrame) -> str:
    """営業利益が全く無い会社（銀行など）は経常利益を使う。"""
    if "operating_profit" in statements and statements["operating_profit"].notna().any():
        return "operating_profit"
    return "ordinary_profit"


def kind_of(doc_type: str) -> str:
    t = str(doc_type)
    if "DividendForecastRevision" in t:
        return "配当修正"
    if "ForecastRevision" in t:
        return "業績修正"
    if "FinancialStatements" in t or "決算" in t:
        return "決算"
    return "その他"


def _yoy_line(name, cur, prev):
    """実績の前年同期比を1行にする。黒字転換・赤字転落も扱う。"""
    cur, prev = _num(cur), _num(prev)
    if cur is None:
        return None, None
    if prev is None:
        return f"{name} {oku(cur)}", None
    if prev > 0 and cur > 0:
        y = (cur / prev - 1) * 100
        return f"{name} {oku(cur)}（前年同期比 {y:+.1f}%）", y
    if prev <= 0 < cur:
        return f"{name} {oku(cur)}（黒字転換、前年 {oku(prev)}）", None
    if cur <= 0 < prev:
        return f"{name} {oku(cur)}（赤字転落、前年 {oku(prev)}）", None
    return f"{name} {oku(cur)}（前年 {oku(prev)}）", None


def evaluate(statements: pd.DataFrame, idx: int) -> dict:
    """statements（disclosed_date 昇順）の idx 行を評価する。

    戻り値: {"kind", "label", "score", "details": [str], "metrics": {...}}
      metrics は表に出す数値（売上/営業/経常/純利益の実績と前年比、進捗、修正幅、会社予想比、来期予想、配当）
    """
    row = statements.iloc[idx]
    kind = kind_of(row.get("doc_type", ""))
    col = _profit_col(statements)
    pname = "営業利益" if col == "operating_profit" else "経常利益"
    fcol = "forecast_operating_profit" if col == "operating_profit" else "forecast_ordinary_profit"
    fy_end = row.get("fy_end")
    period = str(row.get("period") or "")
    op, fop = _num(row.get(col)), _num(row.get(fcol))
    details: list[str] = []
    metrics: dict = {}
    score = 0

    # 同じ決算期の直前の行（予想修正・配当修正の比較対象）
    prev_same_fy = None
    if fy_end is not None and not pd.isna(fy_end):
        earlier = statements.iloc[:idx]
        same = earlier[earlier["fy_end"] == fy_end]
        if kind == "配当修正":
            same = same[same["forecast_dividend_annual"].notna()]
        else:
            same = same[same[fcol].notna()]
        if not same.empty:
            prev_same_fy = same.iloc[-1]

    # ---- 配当予想修正
    if kind == "配当修正":
        new = _num(row.get("forecast_dividend_annual"))
        metrics["dividend_forecast"] = new
        if prev_same_fy is not None and new is not None:
            old = _num(prev_same_fy.get("forecast_dividend_annual"))
            metrics["dividend_prev"] = old
            if old is not None:
                diff = new - old
                label = "増配" if diff > 0 else ("減配" if diff < 0 else "配当修正（据え置き）")
                details.append(f"年間配当予想 {old:g}円 → {new:g}円（{diff:+g}円）")
                return {"kind": kind, "label": label, "score": 1 if diff > 0 else (-1 if diff < 0 else 0),
                        "details": details, "metrics": metrics}
        details.append(f"年間配当予想 {'—' if new is None else f'{new:g}円'}（比較対象なし）")
        return {"kind": kind, "label": "配当修正", "score": 0, "details": details, "metrics": metrics}

    # ---- 業績予想修正
    if kind == "業績修正":
        chg_main = None
        for name, _c, f, _n in FIELDS:
            new = _num(row.get(f))
            old = _num(prev_same_fy.get(f)) if prev_same_fy is not None else None
            chg = _pct(new, old)
            metrics[f"forecast_{f}"] = new
            metrics[f"forecast_change_{f}"] = chg
            if chg is not None:
                details.append(f"通期{name}予想 {oku(old)} → {oku(new)}（{chg:+.1f}%）")
            elif new is not None:
                details.append(f"通期{name}予想 {oku(new)}")
            if f == fcol:
                chg_main = chg
        metrics["forecast_change_pct"] = chg_main
        if chg_main is None:
            return {"kind": kind, "label": "業績修正", "score": 0, "details": details or ["比較対象なし"], "metrics": metrics}
        label = "上方修正" if chg_main >= 0.5 else ("下方修正" if chg_main <= -0.5 else "業績修正（据え置き）")
        return {"kind": kind, "label": label, "score": 1 if chg_main >= 0.5 else (-1 if chg_main <= -0.5 else 0),
                "details": details, "metrics": metrics}

    if kind != "決算":
        return {"kind": kind, "label": kind, "score": 0, "details": [], "metrics": {}}

    # ---- 決算短信: 前年同期比（4項目）
    prev_year = None
    if fy_end is not None and not pd.isna(fy_end):
        earlier = statements.iloc[:idx]
        target = fy_end - pd.DateOffset(years=1)
        cand = earlier[(earlier["period"] == period)
                       & ((earlier["fy_end"] - target).abs() <= pd.Timedelta(days=45))
                       & earlier[col].notna()]
        if not cand.empty:
            prev_year = cand.iloc[-1]
    for name, c, _f, _n in FIELDS:
        line, y = _yoy_line(name, row.get(c), prev_year.get(c) if prev_year is not None else None)
        metrics[c] = _num(row.get(c))
        metrics[f"yoy_{c}"] = y
        if line:
            details.append(line)
    yoy = metrics.get(f"yoy_{col}")
    if prev_year is not None and op is not None:
        prev_op = _num(prev_year.get(col))
        if yoy is not None:
            score += 1 if yoy >= 10 else (-1 if yoy <= -10 else 0)
        elif prev_op is not None:
            score += 1 if (prev_op <= 0 < op) else (-1 if (op <= 0 < prev_op) else 0)
    metrics["profit_yoy_pct"] = yoy

    if period in EXPECTED_PROGRESS:
        prog = None if op is None or fop is None or fop <= 0 else op / fop * 100
        metrics["progress_pct"] = prog
        if prog is not None:
            exp = EXPECTED_PROGRESS[period] * 100
            details.append(f"通期{pname}予想に対する進捗 {prog:.0f}%（{period} の目安 {exp:.0f}%）")
            score += 1 if prog - exp >= 5 else (-1 if prog - exp <= -5 else 0)
        chg = _pct(fop, prev_same_fy[fcol]) if prev_same_fy is not None else None
        metrics["forecast_change_pct"] = chg
        if chg is not None and abs(chg) >= 0.5:
            details.append(f"通期{pname}予想を {chg:+.1f}% {'上方' if chg > 0 else '下方'}修正（{oku(prev_same_fy[fcol])} → {oku(fop)}）")
            score += 1 if chg > 0 else -1
    elif period.upper().startswith("FY"):
        beat = _pct(op, prev_same_fy[fcol]) if prev_same_fy is not None else None
        metrics["vs_forecast_pct"] = beat
        if beat is not None:
            details.append(f"通期{pname} 会社予想比 {beat:+.1f}%（予想 {oku(prev_same_fy[fcol])}）")
            score += 1 if beat >= 3 else (-1 if beat <= -3 else 0)
        nxt_col = "next_fy_forecast_operating_profit" if col == "operating_profit" else "next_fy_forecast_ordinary_profit"
        nxt = _num(row.get(nxt_col))
        guide = _pct(nxt, op)
        metrics["next_fy_guidance_pct"] = guide
        if guide is not None:
            details.append(f"来期{pname}予想 {oku(nxt)}（今期比 {guide:+.1f}%）")
            score += 1 if guide >= 10 else (-1 if guide <= -10 else 0)
        else:
            details.append("来期予想: データなし")
    div = _num(row.get("forecast_dividend_annual"))
    metrics["dividend_forecast"] = div
    if prev_same_fy is not None and div is not None:
        old = _num(prev_same_fy.get("forecast_dividend_annual"))
        if old is not None and abs(div - old) >= 0.01:
            details.append(f"年間配当予想 {old:g}円 → {div:g}円")

    label = "好決算" if score >= 1 else ("悪決算" if score <= -1 else "決算（並）")
    return {"kind": kind, "label": label, "score": score, "details": details, "metrics": metrics}
