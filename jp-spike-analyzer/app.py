# -*- coding: utf-8 -*-
"""
app.py — 急騰日の要因分析（Streamlit・表示専用）。

銘柄コードを入れると、期間内の急騰日と「その時何が起きていたか」
（決算・適時開示・EDINET・ニュース見出し・TOPIX）を並べる。売買判断・発注は行わない。

起動: streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from config import SpikeConfig  # noqa: E402
from src import pipeline  # noqa: E402
from src.data import edinet as edinet_mod  # noqa: E402
from src.data.provider import is_mock  # noqa: E402
from src.data.tdnet import TdnetStore  # noqa: E402

st.set_page_config(page_title="急騰要因アナライザー", page_icon="🚀", layout="wide")
st.title("🚀 急騰日の要因分析")
st.caption("過去の急騰日を抽出し、決算・適時開示・EDINET・ニュース見出し・TOPIX を並べて「その時何が起きていたか」を確認します。売買判断は行いません。")

# ---------------------------------------------------------------- サイドバー
with st.sidebar:
    st.header("設定")
    code = st.text_input("銘柄コード", value="7203", max_chars=5)
    years = st.slider("遡る年数", min_value=1.0, max_value=5.0, value=3.0, step=0.5)
    env_cfg = SpikeConfig.from_env()
    pct = st.number_input("急騰: 前日比（%）以上", value=float(env_cfg.pct), step=0.5)
    pct_v = st.number_input("または 前日比（%）以上 ＋", value=float(env_cfg.pct_with_volume), step=0.5)
    vol_r = st.number_input("出来高が20日平均の（倍）以上", value=float(env_cfg.vol_ratio), step=0.5)
    with_news = st.checkbox("ニュース見出しを取得（Google News）", value=True)
    with_edinet = st.checkbox("EDINET を照合", value=True)
    run = st.button("分析する", type="primary")

    st.divider()
    mode = "mock（ダミー）" if is_mock() else "jquants（本番）"
    st.caption(f"データ提供元: {mode}")
    if not is_mock():
        lo, hi = TdnetStore().coverage()
        if lo is None:
            st.caption("適時開示の蓄積: なし（`python update_daily.py --days 30` で開始）")
        else:
            st.caption(f"適時開示の蓄積（公式）: {lo.date()}〜{hi.date()}")
        if not edinet_mod.has_key():
            st.caption("EDINET: キー未設定（EDINET_API_KEY）")


@st.cache_data(show_spinner=False, ttl=3600)
def _run(code: str, years: float, pct: float, pct_v: float, vol_r: float, with_news: bool, with_edinet: bool):
    cfg = SpikeConfig(pct=pct, pct_with_volume=pct_v, vol_ratio=vol_r)
    logs: list[str] = []
    res = pipeline.analyze(code, years, cfg=cfg, with_news=with_news, with_edinet=with_edinet, log=logs.append)
    bars = res.pop("_bars")
    return res, bars, logs


if "result" not in st.session_state:
    st.session_state["result"] = None
if run:
    if not code.strip():
        st.error("銘柄コードを入力してください。")
    else:
        with st.spinner("取得・分析中…（初回は J-Quants / ニュース取得に時間がかかります）"):
            try:
                st.session_state["result"] = _run(code.strip(), years, pct, pct_v, vol_r, with_news, with_edinet)
            except Exception as e:  # noqa: BLE001
                st.session_state["result"] = None
                st.error(f"分析に失敗しました: {e}")

if st.session_state["result"] is None:
    st.info("左のサイドバーで銘柄コードを入れて「分析する」を押してください。")
    st.stop()

res, bars, logs = st.session_state["result"]
spikes = res["spikes"]

# ---------------------------------------------------------------- サマリ
st.subheader(f"{res['name']}（{res['code']}）  {res['start']} 〜 {res['end']}")
c = st.columns(4)
c[0].metric("営業日数", f"{res['n_days']:,}")
c[1].metric("急騰日", f"{len(spikes)} 件")
tagged = sum(1 for s in spikes if not any(t in ("材料不明", "ニュースのみ") for t in s["tags"]))
c[2].metric("要因が特定できた日", f"{tagged} 件")
c[3].metric("材料不明", f"{sum(1 for s in spikes if '材料不明' in s['tags'])} 件")
with st.expander("取得ログ"):
    st.code("\n".join(logs))

# ---------------------------------------------------------------- チャート
chart_df = bars.reset_index().rename(columns={bars.index.name or "index": "date"})[["date", "close"]]
base = alt.Chart(chart_df).mark_line(color="#4C78A8").encode(
    x=alt.X("date:T", title=""), y=alt.Y("close:Q", title="終値", scale=alt.Scale(zero=False)),
)
if spikes:
    sp_df = pd.DataFrame([{"date": pd.Timestamp(s["date"]), "close": s["close"], "pct": s["pct"],
                           "tags": " / ".join(s["tags"])} for s in spikes])
    pts = alt.Chart(sp_df).mark_point(color="#E45756", size=90, filled=True).encode(
        x="date:T", y="close:Q",
        tooltip=[alt.Tooltip("date:T", title="日付"), alt.Tooltip("pct:Q", title="前日比%", format="+.1f"),
                 alt.Tooltip("tags:N", title="要因")],
    )
    st.altair_chart((base + pts).properties(height=320), use_container_width=True)
else:
    st.altair_chart(base.properties(height=320), use_container_width=True)

if not spikes:
    st.warning("条件に合う急騰日がありませんでした。しきい値を下げてみてください。")
    st.stop()

# ---------------------------------------------------------------- 一覧
def _p(v):
    return "—" if v is None else f"{v:+.1f}%"


table = pd.DataFrame([{
    "日付": s["date"], "前日比": _p(s["pct"]), "寄付ギャップ": _p(s["gap_pct"]),
    "出来高倍率": "—" if s["vol_ratio"] is None else f"{s['vol_ratio']:.1f}倍",
    "TOPIX": _p(s["topix_pct"]), "5日後": _p(s["fwd_5"]), "20日後": _p(s["fwd_20"]),
    "要因タグ": " / ".join(s["tags"]),
} for s in spikes])
st.subheader("急騰日一覧")
st.dataframe(table, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------- 詳細
st.subheader("急騰日ごとの詳細")
for s in spikes:
    head = f"{s['date']}  {_p(s['pct'])}   〔{' / '.join(s['tags'])}〕"
    with st.expander(head, expanded=False):
        m = st.columns(5)
        m[0].metric("前日比", _p(s["pct"]))
        m[1].metric("寄付ギャップ", _p(s["gap_pct"]))
        m[2].metric("出来高倍率", "—" if s["vol_ratio"] is None else f"{s['vol_ratio']:.1f}倍")
        m[3].metric("TOPIX 同日", _p(s["topix_pct"]))
        m[4].metric("対TOPIX 超過", _p(s["relative_pct"]))
        st.caption(f"判定ルール: {s['rule']}　／　5日後 {_p(s['fwd_5'])}　20日後 {_p(s['fwd_20'])}")

        if s["statements"]:
            st.markdown("**決算発表（J-Quants）**")
            for x in s["statements"]:
                op = "" if x["operating_profit"] is None else f"　営業利益 {x['operating_profit']/1e8:,.0f}億円"
                fop = "" if x["forecast_operating_profit"] is None else f"　通期予想 {x['forecast_operating_profit']/1e8:,.0f}億円"
                st.write(f"- [{x['rel']}] {x['date']} {x['time']}　{x['doc_type']} {x['period']}{op}{fop}")

        st.markdown("**適時開示（TDnet）**")
        if s["disclosures"]:
            for x in s["disclosures"]:
                link = f"[{x['title']}]({x['url']})" if x["url"] else x["title"]
                st.write(f"- [{x['rel']}] {x['date']} {x['time']}　`{x['tag']}`　{link}")
        else:
            st.write("- 該当なし（蓄積期間外の可能性あり。`backfill_tdnet.py` で過去分を補完できます）")

        if with_edinet:
            st.markdown("**EDINET**")
            if s["edinet"]:
                for x in s["edinet"]:
                    link = f"[{x['description']}]({x['url']})" if x["url"] else x["description"]
                    st.write(f"- [{x['rel']}] {x['date']}　{link}　提出者: {x['filer']}")
            else:
                st.write("- 該当なし")

        if with_news:
            st.markdown("**ニュース見出し**")
            if s["news"]:
                for x in s["news"][:15]:
                    st.write(f"- {x['date']}　[{x['title']}]({x['url']})　{x['publisher']}")
            else:
                st.write("- 該当なし")
