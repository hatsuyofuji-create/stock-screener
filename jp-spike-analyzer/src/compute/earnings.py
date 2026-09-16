# -*- coding: utf-8 -*-
"""
決算・業績予想修正の数値評価。

J-Quants /fins/summary の行（decl: 決算短信 or 業績予想修正）を、同じ会社の過去の行と比べて
「好決算 / 悪決算 / 上方修正 / 下方修正」を判定し、根拠の数字を文章にする。

比較の考え方（営業利益 OP を軸にする。OP が無い業種は経常利益で代用）:
  - 前年同期比:   同じ期種別（1Q/2Q/3Q/FY）で決算期末が1年前の行と比べる
  - 進捗率:       四半期の累計 OP ÷ その時点の通期予想 OP（1Q 25% / 2Q 50% / 3Q 75% が目安）
  - 予想の修正:   通期予想 OP を、同じ決算期の直前の行の通期予想と比べる
  - 通期の着地:   FY 行の実績 OP を、直前の通期予想と比べる（上振れ / 下振れ）
  - 来期予想:     FY 行の来期予想 OP を、今期実績と比べる
"""

from __future__ import annotations

import pandas as pd

EXPECTED_PROGRESS = {"1Q": 0.25, "2Q": 0.50, "3Q": 0.75}


def _oku(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v / 1e8:,.0f}億円"


def _pct(a, b):
    """a が b に対して何%か（比率-1）。b が 0 以下や欠損なら None。"""
    if a is None or b is None or pd.isna(a) or pd.isna(b) or b <= 0:
        return None
    return (float(a) / float(b) - 1.0) * 100.0


def _profit_col(statements: pd.DataFrame) -> str:
    """営業利益が全く無い会社（銀行など）は経常利益を使う。"""
    if "operating_profit" in statements and statements["operating_profit"].notna().any():
        return "operating_profit"
    return "ordinary_profit"


def _kind(doc_type: str) -> str:
    t = str(doc_type)
    if "DividendForecastRevision" in t:
        return "配当予想修正"
    if "ForecastRevision" in t:
        return "業績修正"
    if "FinancialStatements" in t or "決算" in t:
        return "決算"
    return "その他"


def evaluate(statements: pd.DataFrame, idx: int) -> dict:
    """statements（disclosed_date 昇順）の idx 行を評価する。

    戻り値: {"kind", "label", "score", "details": [str], "metrics": {...}}
    """
    row = statements.iloc[idx]
    kind = _kind(row.get("doc_type", ""))
    col = _profit_col(statements)
    pname = "営業利益" if col == "operating_profit" else "経常利益"
    fcol = "forecast_operating_profit" if col == "operating_profit" else "forecast_operating_profit"
    fy_end = row.get("fy_end")
    period = str(row.get("period") or "")
    op = row.get(col)
    fop = row.get(fcol)
    details: list[str] = []
    metrics: dict = {}
    score = 0

    # 同じ決算期の直前の行（予想修正の比較対象）
    prev_same_fy = None
    if fy_end is not None and not pd.isna(fy_end):
        earlier = statements.iloc[:idx]
        same = earlier[(earlier["fy_end"] == fy_end) & earlier[fcol].notna()]
        if not same.empty:
            prev_same_fy = same.iloc[-1]

    if kind == "配当予想修正":
        return {"kind": kind, "label": "配当予想修正", "score": 0, "details": ["配当予想の修正"], "metrics": {}}

    if kind == "業績修正":
        if prev_same_fy is not None:
            chg = _pct(fop, prev_same_fy[fcol])
            metrics["forecast_change_pct"] = chg
            if chg is not None:
                label = "上方修正" if chg >= 0.5 else ("下方修正" if chg <= -0.5 else "業績修正（据え置き）")
                score = 1 if chg >= 0.5 else (-1 if chg <= -0.5 else 0)
                details.append(f"通期{pname}予想 {_oku(prev_same_fy[fcol])} → {_oku(fop)}（{chg:+.1f}%）")
                s_chg = _pct(row.get("forecast_sales"), prev_same_fy.get("forecast_sales"))
                if s_chg is not None:
                    details.append(f"通期売上予想 {s_chg:+.1f}%")
                return {"kind": kind, "label": label, "score": score, "details": details, "metrics": metrics}
        details.append(f"通期{pname}予想 {_oku(fop)}（比較対象なし）")
        return {"kind": kind, "label": "業績修正", "score": 0, "details": details, "metrics": metrics}

    if kind != "決算":
        return {"kind": kind, "label": kind, "score": 0, "details": [], "metrics": {}}

    # ---- 決算短信
    # 前年同期比
    yoy = None
    if fy_end is not None and not pd.isna(fy_end):
        earlier = statements.iloc[:idx]
        target = fy_end - pd.DateOffset(years=1)
        cand = earlier[(earlier["period"] == period)
                       & ((earlier["fy_end"] - target).abs() <= pd.Timedelta(days=45))
                       & earlier[col].notna()]
        if not cand.empty:
            prev_op = cand.iloc[-1][col]
            metrics["prev_year_profit"] = None if pd.isna(prev_op) else float(prev_op)
            if op is not None and not pd.isna(op):
                if prev_op > 0 and op > 0:
                    yoy = _pct(op, prev_op)
                    details.append(f"{pname} {_oku(op)}（前年同期比 {yoy:+.1f}%）")
                    score += 1 if yoy >= 10 else (-1 if yoy <= -10 else 0)
                elif prev_op <= 0 < op:
                    details.append(f"{pname} {_oku(op)}（黒字転換、前年 {_oku(prev_op)}）"); score += 1
                elif op <= 0 < prev_op:
                    details.append(f"{pname} {_oku(op)}（赤字転落、前年 {_oku(prev_op)}）"); score -= 1
                else:
                    details.append(f"{pname} {_oku(op)}（前年 {_oku(prev_op)}）")
            s_yoy = _pct(row.get("net_sales"), cand.iloc[-1].get("net_sales"))
            if s_yoy is not None:
                details.append(f"売上 {_oku(row.get('net_sales'))}（前年同期比 {s_yoy:+.1f}%）")
                metrics["sales_yoy_pct"] = s_yoy
    if yoy is None and not details and op is not None and not pd.isna(op):
        details.append(f"{pname} {_oku(op)}（前年同期の比較データなし）")
    metrics["profit_yoy_pct"] = yoy

    if period in EXPECTED_PROGRESS:
        # 進捗率（通期予想に対して）
        prog = None if op is None or fop is None or pd.isna(op) or pd.isna(fop) or fop <= 0 else float(op) / float(fop) * 100
        metrics["progress_pct"] = prog
        if prog is not None:
            exp = EXPECTED_PROGRESS[period] * 100
            gap = prog - exp
            details.append(f"通期予想に対する進捗 {prog:.0f}%（{period} の目安 {exp:.0f}%）")
            score += 1 if gap >= 5 else (-1 if gap <= -5 else 0)
        # 決算と同時の予想修正
        if prev_same_fy is not None:
            chg = _pct(fop, prev_same_fy[fcol])
            metrics["forecast_change_pct"] = chg
            if chg is not None and abs(chg) >= 0.5:
                details.append(f"通期{pname}予想を {chg:+.1f}% {'上方' if chg > 0 else '下方'}修正（{_oku(prev_same_fy[fcol])} → {_oku(fop)}）")
                score += 1 if chg > 0 else -1
    elif period == "FY" or period.upper().startswith("FY"):
        # 通期の着地（直前予想比）
        if prev_same_fy is not None:
            beat = _pct(op, prev_same_fy[fcol])
            metrics["vs_forecast_pct"] = beat
            if beat is not None:
                details.append(f"通期{pname} 会社予想比 {beat:+.1f}%（予想 {_oku(prev_same_fy[fcol])}）")
                score += 1 if beat >= 3 else (-1 if beat <= -3 else 0)
        # 来期予想
        nxt = row.get("next_fy_forecast_operating_profit") if col == "operating_profit" else None
        guide = _pct(nxt, op)
        metrics["next_fy_guidance_pct"] = guide
        if guide is not None:
            details.append(f"来期{pname}予想 {_oku(nxt)}（今期比 {guide:+.1f}%）")
            score += 1 if guide >= 10 else (-1 if guide <= -10 else 0)
        elif nxt is None or pd.isna(nxt):
            details.append("来期予想: データなし")

    label = "好決算" if score >= 1 else ("悪決算" if score <= -1 else "決算（並）")
    return {"kind": kind, "label": label, "score": score, "details": details, "metrics": metrics}
