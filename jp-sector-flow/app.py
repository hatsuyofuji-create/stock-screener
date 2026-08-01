# -*- coding: utf-8 -*-
"""
app.py — セクター資金フロー（売買代金＋価格の方向）の表示（Streamlit・表示専用）。

update_daily.py が書き出した db/ranking.csv を読んで、
  - 全業種ランキング（売買代金 大きい順）
  - 価格の方向（15日 / 30日 / 150日の株価変化＝🟢買い優勢／🔴売り優勢）
を表示するだけ。売買判断・発注ロジックは持たない。

起動: streamlit run app.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
DB_DIR = ROOT / "db"

st.set_page_config(page_title="セクター資金フロー", page_icon="📊", layout="wide")
st.title("📊 セクター資金フロー（売買代金＋価格の方向）")

rank_path = DB_DIR / "ranking.csv"
meta_path = DB_DIR / "meta.json"

if not rank_path.exists():
    st.warning("まだデータがありません。先に `python update_daily.py` を実行してください。")
    st.stop()

if meta_path.exists():
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    st.caption(
        f"基準日: {meta.get('asof', '-')} ／ 提供元: {meta.get('provider', '-')} "
        f"／ 更新: {meta.get('updated_at', '-')}"
    )

st.caption(
    "売買代金＝活発さ（買い・売りの合計）。買われているか売られているかは"
    "「価格の方向」（5/15/30/150日の株価変化 🟢買い優勢／🔴売り優勢）で判断します。"
)


def _dir(v):
    if v is None or pd.isna(v):
        return "—"
    return f"🟢 +{v:.1f}%" if v >= 0 else f"🔴 {v:.1f}%"


# 参考指標: SOX（米・半導体）。あれば上部に表示。
sox_path = DB_DIR / "sox.json"
if sox_path.exists():
    sox = json.loads(sox_path.read_text(encoding="utf-8"))
    mom = sox.get("mom", {})

    def _g(k):
        return mom.get(str(k), mom.get(k))

    st.subheader("参考：SOX指数（米・フィラデルフィア半導体株指数）")
    st.caption("日本の半導体・電気機器を先導する米国の指数。株価変化を 5/15/30/150日で。")
    c = st.columns(5)
    c[0].metric("最新値", f"{sox.get('level', 0):,.0f} pt")
    for i, d in enumerate((5, 15, 30, 150), start=1):
        c[i].metric(f"{d}日", _dir(_g(d)))
    st.divider()

ranking = pd.read_csv(rank_path)

show = ranking.copy()
for d in (5, 15, 30, 150):
    col = f"price_mom_{d}"
    show[col] = show[col].map(_dir) if col in show.columns else "—"
show["turnover"] = show["turnover"].map(lambda v: f"{v:,.0f}")
show = show[["rank", "sector", "turnover", "price_mom_5", "price_mom_15", "price_mom_30", "price_mom_150"]].rename(
    columns={
        "rank": "順位", "sector": "業種", "turnover": "売買代金(億円)",
        "price_mom_5": "5日", "price_mom_15": "15日", "price_mom_30": "30日", "price_mom_150": "150日",
    }
)
st.dataframe(show, hide_index=True, use_container_width=True, height=1200)

st.caption("※ 表示専用ツールです。売買判断・発注は行いません。活発（売買代金 大）×買い優勢＝資金流入と読めます。")
