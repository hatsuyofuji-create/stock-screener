# -*- coding: utf-8 -*-
"""
app.py — 決算と株価の反応 / 急騰・急落の要因（Streamlit・表示専用）。

モード1「決算と株価の反応」: 過去の決算・業績予想修正・配当予想修正を並べ、業績の数字と
  評価（好決算/悪決算/上方修正/下方修正/増配/減配）、翌営業日以降の株価の反応を表示する。
モード2「急騰・急落の要因」: 前日終値比 ±8% の日を抽出し、決算・適時開示・EDINET・ニュースと突き合わせる。
売買判断・発注は行わない。

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
from src.compute.reactions import BAD, GOOD  # noqa: E402
from src.data import edinet as edinet_mod  # noqa: E402
from src.data.provider import is_mock  # noqa: E402
from src.data.tdnet import TdnetStore  # noqa: E402

st.set_page_config(page_title="決算と株価の反応", page_icon="📈", layout="wide")


def _p(v):
    return "—" if v is None else f"{v:+.1f}%"


def _x(v):
    return "—" if v is None else f"{v:.1f}倍"


def _oku(v):
    return "—" if v is None else f"{v / 1e8:,.0f}"


# ================================================================ サイドバー
with st.sidebar:
    st.header("設定")
    mode = st.radio("モード", ["決算と株価の反応", "急騰・急落の要因"])
    code = st.text_input("銘柄コード", value="7203", max_chars=5)
    env_cfg = SpikeConfig.from_env()
    years = st.slider("遡る年数", min_value=1.0, max_value=5.0, value=float(min(env_cfg.years, 5.0)), step=0.5)
    if mode == "決算と株価の反応":
        include_dividend = st.checkbox("配当予想の修正も含める", value=True)
    else:
        direction_label = st.radio("対象", ["急騰", "急落", "両方"], horizontal=True)
        direction = {"急騰": "up", "急落": "down", "両方": "both"}[direction_label]
        pct = st.number_input("急騰: 前日終値比（%）以上", value=float(env_cfg.pct), step=0.5)
        drop_pct = st.number_input("急落: 前日終値比（%）以下", value=float(env_cfg.drop_pct), step=0.5)
        with_news = st.checkbox("ニュース見出しを取得（Google News）", value=True)
        with_edinet = st.checkbox("EDINET を照合", value=True)
    run = st.button("分析する", type="primary")

    st.divider()
    st.caption(f"データ提供元: {'mock（ダミー）' if is_mock() else 'jquants（本番）'}")
    if not is_mock() and mode != "決算と株価の反応":
        lo, hi = TdnetStore().coverage()
        st.caption("適時開示の蓄積: なし" if lo is None else f"適時開示の蓄積（公式）: {lo.date()}〜{hi.date()}")
        if not edinet_mod.has_key():
            st.caption("EDINET: キー未設定（EDINET_API_KEY）")


@st.cache_data(show_spinner=False, ttl=3600)
def _run_earnings(code: str, years: float, include_dividend: bool):
    logs: list[str] = []
    res = pipeline.analyze_earnings(code, years, include_dividend=include_dividend, log=logs.append)
    return res, res.pop("_bars"), logs


@st.cache_data(show_spinner=False, ttl=3600)
def _run_spikes(code: str, years: float, pct: float, drop_pct: float, direction: str, with_news: bool, with_edinet: bool):
    cfg = SpikeConfig(pct=pct, drop_pct=drop_pct, direction=direction)
    logs: list[str] = []
    res = pipeline.analyze(code, years, cfg=cfg, with_news=with_news, with_edinet=with_edinet, log=logs.append)
    return res, res.pop("_bars"), logs


key = f"result_{mode}"
if key not in st.session_state:
    st.session_state[key] = None
if run:
    if not code.strip():
        st.error("銘柄コードを入力してください。")
    else:
        with st.spinner("取得・分析中…（初回は J-Quants の取得に少し時間がかかります）"):
            try:
                if mode == "決算と株価の反応":
                    st.session_state[key] = _run_earnings(code.strip(), years, include_dividend)
                else:
                    st.session_state[key] = _run_spikes(code.strip(), years, pct, drop_pct, direction, with_news, with_edinet)
            except Exception as e:  # noqa: BLE001
                st.session_state[key] = None
                st.error(f"分析に失敗しました: {e}")


def _price_chart(bars: pd.DataFrame, marks: pd.DataFrame, color_field: str, domain: list[str], colors: list[str]):
    chart_df = bars.reset_index().rename(columns={bars.index.name or "index": "date"})[["date", "close"]]
    base = alt.Chart(chart_df).mark_line(color="#4C78A8").encode(
        x=alt.X("date:T", title=""), y=alt.Y("close:Q", title="終値", scale=alt.Scale(zero=False)),
    )
    if marks.empty:
        return base.properties(height=320)
    pts = alt.Chart(marks).mark_point(size=100, filled=True).encode(
        x="date:T", y="close:Q",
        color=alt.Color(f"{color_field}:N", scale=alt.Scale(domain=domain, range=colors), legend=alt.Legend(title="")),
        tooltip=[alt.Tooltip("date:T", title="日付"), alt.Tooltip(f"{color_field}:N", title="評価"),
                 alt.Tooltip("react:Q", title="翌日%", format="+.1f"), alt.Tooltip("note:N", title="内容")],
    )
    return (base + pts).properties(height=320)


# ================================================================ モード1: 決算と株価の反応
if mode == "決算と株価の反応":
    st.title("📈 決算と株価の反応")
    st.caption("過去の決算・業績予想修正・配当予想修正ごとに、業績の数字と評価、翌営業日以降の株価の動きを並べます。売買判断は行いません。")
    if st.session_state[key] is None:
        st.info("左のサイドバーで銘柄コードを入れて「分析する」を押してください。")
        st.stop()
    res, bars, logs = st.session_state[key]
    events, summary = res["events"], res["summary"]

    st.subheader(f"{res['name']}（{res['code']}）  {res['start']} 〜 {res['end']}")
    c = st.columns(4)
    c[0].metric("決算イベント", f"{len(events)} 件")
    good = [e for e in events if e["label"] in GOOD and e["react_pct"] is not None]
    bad = [e for e in events if e["label"] in BAD and e["react_pct"] is not None]
    c[1].metric("好材料（好決算・上方修正・増配）", f"{len(good)} 件",
                None if not good else f"翌日平均 {sum(e['react_pct'] for e in good) / len(good):+.1f}%")
    c[2].metric("悪材料（悪決算・下方修正・減配）", f"{len(bad)} 件",
                None if not bad else f"翌日平均 {sum(e['react_pct'] for e in bad) / len(bad):+.1f}%")
    honest = sum(1 for e in good if e["react_pct"] > 0) + sum(1 for e in bad if e["react_pct"] < 0)
    c[3].metric("評価どおりに動いた割合", "—" if not (good or bad) else f"{honest / (len(good) + len(bad)) * 100:.0f}%")
    with st.expander("取得ログ"):
        st.code("\n".join(logs))

    # チャート
    if events:
        marks = pd.DataFrame([{
            "date": pd.Timestamp(e["reaction_date"]), "close": e["close"], "評価": e["label"],
            "react": e["react_pct"] if e["react_pct"] is not None else 0.0,
            "note": f"{e['kind']} {e['period']} / " + " / ".join(e["details"][:2]),
        } for e in events])
        labels = list(dict.fromkeys(marks["評価"]))
        colors = ["#2E9E5B" if l in GOOD else ("#E45756" if l in BAD else "#8C8C8C") for l in labels]
        st.altair_chart(_price_chart(bars, marks, "評価", labels, colors), use_container_width=True)
    else:
        st.altair_chart(_price_chart(bars, pd.DataFrame(), "評価", [], []), use_container_width=True)
        st.warning("期間内に決算イベントがありませんでした。")
        st.stop()

    # 傾向
    st.subheader("傾向: 評価ごとの翌営業日の反応")
    st.dataframe(pd.DataFrame([{
        "評価": r["label"], "回数": r["n"], "翌日上昇": f"{r['n_up']} / {r['n']}",
        "翌日平均": _p(r["avg_react"]), "寄付平均": _p(r["avg_gap"]),
        "5日後平均": _p(r["avg_fwd_5"]), "20日後平均": _p(r["avg_fwd_20"]), "対TOPIX平均": _p(r["avg_relative"]),
    } for r in summary]), use_container_width=True, hide_index=True)

    # 一覧
    st.subheader("決算ごとの業績と株価の反応（億円）")
    rows = []
    for e in events:
        m = e["metrics"]
        if e["kind"] == "決算":
            sales, op, odp, np_ = m.get("net_sales"), m.get("operating_profit"), m.get("ordinary_profit"), m.get("profit")
        else:
            sales, op, odp, np_ = (m.get("forecast_forecast_sales"), m.get("forecast_forecast_operating_profit"),
                                   m.get("forecast_forecast_ordinary_profit"), m.get("forecast_forecast_profit"))
        rows.append({
            "発表日": f"{e['disclosed_date']} {e['disclosed_time']}",
            "種別": f"{e['kind']} {e['period']}".strip(),
            "評価": e["label"],
            "売上": _oku(sales), "営業利益": _oku(op), "経常利益": _oku(odp), "純利益": _oku(np_),
            "営業益 前年比": _p(m.get("yoy_operating_profit")),
            "進捗": "—" if m.get("progress_pct") is None else f"{m['progress_pct']:.0f}%",
            "予想修正": _p(m.get("forecast_change_pct")),
            "翌日": _p(e["react_pct"]), "寄付": _p(e["gap_pct"]), "出来高": _x(e["vol_ratio"]),
            "5日後": _p(e["fwd_5"]), "20日後": _p(e["fwd_20"]), "TOPIX": _p(e["topix_pct"]),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("売上・利益は決算なら実績（累計）、業績修正なら新しい通期予想。翌日以降は発表前の終値からの変化率。")

    # 詳細
    st.subheader("決算ごとの詳細")
    for e in events:
        mark = "🟢" if e["label"] in GOOD else ("🔴" if e["label"] in BAD else "⚪")
        head = f"{mark} {e['disclosed_date']} {e['disclosed_time']}　{e['kind']} {e['period']}　{e['label']}　→ 翌日 {_p(e['react_pct'])}"
        with st.expander(head):
            mcols = st.columns(6)
            mcols[0].metric("翌日", _p(e["react_pct"]))
            mcols[1].metric("寄付", _p(e["gap_pct"]))
            mcols[2].metric("高値 / 安値", f"{_p(e['high_pct'])} / {_p(e['low_pct'])}")
            mcols[3].metric("出来高", _x(e["vol_ratio"]))
            mcols[4].metric("5日後 / 20日後", f"{_p(e['fwd_5'])} / {_p(e['fwd_20'])}")
            mcols[5].metric("対TOPIX", _p(e["relative_pct"]))
            for line in e["details"]:
                st.write(f"・{line}")
    st.stop()

# ================================================================ モード2: 急騰・急落の要因
st.title("🚀 急騰・急落の要因")
st.caption("前日終値比 ±8% の日を抽出し、決算・適時開示・EDINET・ニュース見出し・TOPIX を並べて「その時何が起きていたか」を確認します。")
if st.session_state[key] is None:
    st.info("左のサイドバーで銘柄コードを入れて「分析する」を押してください。")
    st.stop()
res, bars, logs = st.session_state[key]
spikes = res["spikes"]

st.subheader(f"{res['name']}（{res['code']}）  {res['start']} 〜 {res['end']}")
c = st.columns(4)
c[0].metric("営業日数", f"{res['n_days']:,}")
n_up = sum(1 for s in spikes if s["direction"] == "up")
c[1].metric("急騰日 / 急落日", f"{n_up} 件 / {len(spikes) - n_up} 件")
c[2].metric("要因が特定できた日", f"{sum(1 for s in spikes if '材料不明' not in s['tags'])} 件")
c[3].metric("材料不明", f"{sum(1 for s in spikes if '材料不明' in s['tags'])} 件")
with st.expander("取得ログ"):
    st.code("\n".join(logs))

marks = pd.DataFrame([{"date": pd.Timestamp(s["date"]), "close": s["close"], "react": s["pct"],
                       "種別": "急騰" if s["direction"] == "up" else "急落", "note": " / ".join(s["tags"])} for s in spikes])
st.altair_chart(_price_chart(bars, marks, "種別", ["急騰", "急落"], ["#E45756", "#3B7DD8"]), use_container_width=True)
if not spikes:
    st.warning("条件に合う急騰・急落日がありませんでした。しきい値を下げてみてください。")
    st.stop()

st.subheader("急騰・急落日一覧")
st.dataframe(pd.DataFrame([{
    "種別": "▲急騰" if s["direction"] == "up" else "▼急落",
    "日付": s["date"], "前日比": _p(s["pct"]), "寄付ギャップ": _p(s["gap_pct"]), "出来高倍率": _x(s["vol_ratio"]),
    "TOPIX": _p(s["topix_pct"]), "5日後": _p(s["fwd_5"]), "20日後": _p(s["fwd_20"]), "要因タグ": " / ".join(s["tags"]),
} for s in spikes]), use_container_width=True, hide_index=True)

st.subheader("日ごとの詳細")
for s in spikes:
    mark = "▲" if s["direction"] == "up" else "▼"
    with st.expander(f"{mark} {s['date']}  {_p(s['pct'])}   〔{' / '.join(s['tags'])}〕"):
        m = st.columns(5)
        m[0].metric("前日比", _p(s["pct"]))
        m[1].metric("寄付ギャップ", _p(s["gap_pct"]))
        m[2].metric("出来高倍率", _x(s["vol_ratio"]))
        m[3].metric("TOPIX 同日", _p(s["topix_pct"]))
        m[4].metric("対TOPIX 超過", _p(s["relative_pct"]))
        st.caption(f"判定ルール: {s['rule']}　／　5日後 {_p(s['fwd_5'])}　20日後 {_p(s['fwd_20'])}")
        if s["statements"]:
            st.markdown("**決算・業績予想（J-Quants）**")
            for x in s["statements"]:
                st.write(f"- [{x['rel']}] {x['date']} {x['time']}　{x['kind']} {x['period']}　**{x['label']}**")
                for line in x["details"]:
                    st.write(f"　　・{line}")
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
                for x in s["news"][:20]:
                    st.write(f"- [{x.get('rel', '')}] {x['date']}　[{x['title']}]({x['url']})　{x['publisher']}")
            else:
                st.write("- 該当なし")
