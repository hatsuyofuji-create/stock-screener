# -*- coding: utf-8 -*-
"""
app.py — セクター資金フロー（売買代金）の表示（Streamlit・表示専用）。

update_daily.py が書き出した db/ の CSV を読んで、
  - 今日のランキング（売買代金 上位）
  - 業種別 売買代金（億円）の推移グラフ
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

st.set_page_config(page_title="セクター資金フロー（売買代金）", page_icon="📊", layout="wide")
st.title("📊 セクター資金フロー（売買代金）")

flow_path = DB_DIR / "turnover.csv"
rank_path = DB_DIR / "ranking.csv"
meta_path = DB_DIR / "meta.json"

if not flow_path.exists() or not rank_path.exists():
    st.warning("まだデータがありません。先に `python update_daily.py` を実行してください。")
    st.stop()

# メタ情報
if meta_path.exists():
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    st.caption(
        f"基準日: {meta.get('asof', '-')} ／ 提供元: {meta.get('provider', '-')} "
        f"／ 更新: {meta.get('updated_at', '-')}"
    )

ranking = pd.read_csv(rank_path)
flow_df = pd.read_csv(flow_path, index_col=0, parse_dates=True)

# 全業種合計 売買代金（月次・兆円）— グラフの上に表示
mon_path = DB_DIR / "monthly.csv"
if mon_path.exists():
    mon = pd.read_csv(mon_path).tail(8)
    st.subheader("全業種合計 売買代金（月次・兆円）")
    for c, (_, row) in zip(st.columns(len(mon)), mon.iterrows()):
        c.metric(str(row["month"])[2:], f"{row['tri']:.1f} 兆円")
        c.caption(f"途中 {int(row['days'])}日" if row["partial"] else f"{int(row['days'])}日")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("今日のランキング（売買代金）")

    def _dir(pm):
        if pm is None or pd.isna(pm):
            return "— 不明"
        return f"🟢買い優勢 +{pm:.1f}%" if pm >= 0 else f"🔴売り優勢 {pm:.1f}%"

    show = ranking.copy()
    if "price_mom" in show.columns:
        show["price_mom"] = show["price_mom"].map(_dir)
    else:
        show["price_mom"] = "—"
    show["turnover"] = show["turnover"].map(lambda v: f"{v:,.1f}")
    show = show[["rank", "sector", "turnover", "price_mom"]].rename(
        columns={"rank": "順位", "sector": "業種", "turnover": "売買代金(億円)", "price_mom": "価格の方向(5日)"}
    )
    st.dataframe(show, hide_index=True, use_container_width=True)

with col2:
    st.subheader("業種別 売買代金（億円）の推移")
    default = ranking.head(5)["sector"].tolist()
    chosen = st.multiselect(
        "表示する業種", options=list(flow_df.columns), default=default
    )
    if chosen:
        st.line_chart(flow_df[chosen])
    else:
        st.info("業種を選ぶとグラフが表示されます。")

st.caption("※ 表示専用ツールです。売買判断・発注は行いません。売買代金は5営業日の移動平均。")
