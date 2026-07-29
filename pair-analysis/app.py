# -*- coding: utf-8 -*-
"""
自由ペア分析（Streamlit UI）— 先行→後続の連動を「その場で」測る。

    PRICE_PROVIDER=yahoo streamlit run app.py     # 本番（yfinance）
    streamlit run app.py                          # オフライン確認（synthetic）

スクショの「自由ペア分析（その場で計算・約5秒）」を再現:
  入力（先行 / 後続 / 期間 / 急変しきい値） → ベータ・太さ・↑↓の追随集計 →
  株価の重ね描き（共通開始=100）＋ 急変日の散布図（追随/逆行）。
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.analysis import analyze_pair
from src.data.provider import get_provider
from src.universe import PERIODS, default_lag, to_yahoo_symbol

st.set_page_config(page_title="自由ペア分析", page_icon="🔎", layout="wide")

st.markdown("### 🔎 自由ペア分析（その場で計算・約5秒）")
st.caption(
    "好きなペアをその場で測定。日本→日本もOK（例: 先行6857 → 後続6146）。"
    "先行は日本株コード・米国ティッカー(MU/NVDA)・指数(^SOX)・韓国(.KS)・台湾(.TW)に対応。"
    "同時間帯ペアの当日追随は「連れ高の確認」、翌日相関とβが「遅れて伝わる分＝張れる余地」です。"
)

THRESHOLDS = {"±3%（標準）": 0.03, "±5%（大波のみ）": 0.05}

c1, c2, c3, c4, c5 = st.columns([2, 2, 1.5, 2, 1])
with c1:
    leader_in = st.text_input("先行", value="TSM")
with c2:
    follower_in = st.text_input("後続", value="6146")
with c3:
    period_label = st.selectbox("期間", list(PERIODS), index=list(PERIODS).index("2年"))
with c4:
    thr_label = st.selectbox("急変しきい値", list(THRESHOLDS))
with c5:
    st.write("")
    go = st.button("⚡分析", use_container_width=True)


@st.cache_data(show_spinner=False)
def _load(symbol: str, yf_period: str):
    return get_provider().get_close_history(symbol, yf_period)


def render():
    leader = to_yahoo_symbol(leader_in)
    follower = to_yahoo_symbol(follower_in)
    yf_period, _n = PERIODS[period_label]
    threshold = THRESHOLDS[thr_label]
    lag = default_lag(leader)

    try:
        dl, pl = _load(leader, yf_period)
        df_, pf = _load(follower, yf_period)
    except Exception as e:  # noqa: BLE001
        st.error(f"データ取得に失敗: {e}")
        return

    res = analyze_pair(leader, follower, dl, pl, df_, pf, lag=lag, threshold=threshold)
    if res.n_days == 0:
        st.warning("共通の営業日が足りません。シンボルや期間を見直してください。")
        return

    st.info(f"{res.leader} → {res.follower}"
            f"（{res.n_days}日・しきい値±{threshold*100:.0f}%・lag={res.lag}）")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("ベータ（先行1%→後続）", f"{res.beta*100:+.2f}%",
              help=f"全{res.n_days}営業日で測定")
    m2.metric("つながりの太さ", res.thickness, help=f"相関 r={res.corr:+.2f}（±0.15/0.25 が目安）")
    u, d = res.up, res.down
    warn_u = " ⚠回数少" if u.n < 30 else ""
    warn_d = " ⚠回数少" if d.n < 30 else ""
    m3.metric(f"↑急騰時 追随率{warn_u}", f"{u.follow_rate*100:.1f}%",
              f"{u.n}回中・平均{u.avg_move*100:+.2f}%")
    m4.metric(f"↓急落時 追随率{warn_d}", f"{d.follow_rate*100:.1f}%",
              f"{d.n}回中・平均{d.avg_move*100:+.2f}%")

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**株価の重ね描き（共通開始=100）**")
        overlay = pd.DataFrame(
            {res.leader: res.overlay_leader, res.follower: res.overlay_follower},
            index=pd.to_datetime(res.overlay_dates),
        )
        st.line_chart(overlay)
    with g2:
        st.markdown("**急変日の散布図（先行→後続 %）**")
        if res.scatter:
            sc = pd.DataFrame(
                [(lr * 100, fr * 100, "追随" if f else "逆行")
                 for lr, fr, f in res.scatter],
                columns=["先行%", "後続%", "判定"],
            )
            st.scatter_chart(sc, x="先行%", y="後続%", color="判定")
        else:
            st.write("急変日がありませんでした（しきい値を緩めてください）。")

    st.caption("※ 表示・検証用。過去の統計であり将来を保証しません。売買は自己責任で。")


if go or True:  # 初期表示でも既定ペアを描画
    render()
