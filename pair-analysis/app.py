# -*- coding: utf-8 -*-
"""
自由ペア分析 / 連動ランキング（Streamlit UI）

    PRICE_PROVIDER=yahoo streamlit run app.py     # 本番（yfinance）
    streamlit run app.py                          # オフライン確認（synthetic）

タブ1「ペア分析」    : 先行→後続を1ペアだけ その場で測る（スクショの画面）。
タブ2「連動ランキング」: 候補1銘柄と連動する相手をユニバースから探して並べる。
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from src.analysis import analyze_pair
from src.data.provider import get_provider
from src.rank import rank_peers
from src.universe import PERIODS, default_lag, to_yahoo_symbol

st.set_page_config(page_title="自由ペア分析", page_icon="🔎", layout="wide")

THRESHOLDS = {"±3%（標準）": 0.03, "±5%（大波のみ）": 0.05}
DEFAULT_UNIVERSE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "universe", "leaders_jp_us.txt")


@st.cache_data(show_spinner=False)
def _load(symbol: str, yf_period: str):
    return get_provider().get_close_history(symbol, yf_period)


# ── タブ1: ペア分析 ─────────────────────────────────────────────────────
def tab_pair():
    st.caption(
        "好きなペアをその場で測定。先行は日本株コード・米国ティッカー(MU/NVDA)・"
        "指数(^SOX)・韓国(.KS)・台湾(.TW)に対応。翌日相関とβが「遅れて伝わる分＝張れる余地」。"
    )
    c1, c2, c3, c4, c5 = st.columns([2, 2, 1.5, 2, 1])
    leader_in = c1.text_input("先行", value="TSM")
    follower_in = c2.text_input("後続", value="6146")
    period_label = c3.selectbox("期間", list(PERIODS), index=list(PERIODS).index("2年"))
    thr_label = c4.selectbox("急変しきい値", list(THRESHOLDS))
    c5.write("")
    c5.button("⚡分析", use_container_width=True, key="pair_go")

    leader, follower = to_yahoo_symbol(leader_in), to_yahoo_symbol(follower_in)
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
    m1.metric("ベータ（先行1%→後続）", f"{res.beta*100:+.2f}%", help=f"全{res.n_days}営業日")
    m2.metric("つながりの太さ", res.thickness, help=f"相関 r={res.corr:+.2f}")
    u, d = res.up, res.down
    m3.metric(f"↑急騰時 追随率{' ⚠回数少' if u.n < 30 else ''}",
              f"{u.follow_rate*100:.1f}%", f"{u.n}回中・平均{u.avg_move*100:+.2f}%")
    m4.metric(f"↓急落時 追随率{' ⚠回数少' if d.n < 30 else ''}",
              f"{d.follow_rate*100:.1f}%", f"{d.n}回中・平均{d.avg_move*100:+.2f}%")

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**株価の重ね描き（共通開始=100）**")
        st.line_chart(pd.DataFrame(
            {res.leader: res.overlay_leader, res.follower: res.overlay_follower},
            index=pd.to_datetime(res.overlay_dates)))
    with g2:
        st.markdown("**急変日の散布図（先行→後続 %）**")
        if res.scatter:
            sc = pd.DataFrame(
                [(lr * 100, fr * 100, "追随" if f else "逆行") for lr, fr, f in res.scatter],
                columns=["先行%", "後続%", "判定"])
            st.scatter_chart(sc, x="先行%", y="後続%", color="判定")
        else:
            st.write("急変日がありませんでした（しきい値を緩めてください）。")


# ── タブ2: 連動ランキング ───────────────────────────────────────────────
def tab_rank():
    st.caption(
        "候補1銘柄を入れると、ユニバースの中から動きが連動する銘柄を探して並べます。"
        "『先行→後続』重視だと、候補に先行している＝先行指標になりうる銘柄が上位に出ます。"
    )
    c1, c2, c3, c4 = st.columns([2, 1.5, 2, 1.5])
    target_in = c1.text_input("候補銘柄", value="6146", key="rk_target")
    period_label = c2.selectbox("期間", list(PERIODS),
                                index=list(PERIODS).index("2年"), key="rk_period")
    mode_label = c3.selectbox("並べ方", ["時間差（先行→後続）重視", "同日連動を重視"],
                              key="rk_mode")
    top = c4.number_input("表示件数", 5, 100, 20, key="rk_top")
    mode = "time_lag" if mode_label.startswith("時間差") else "same_day"

    st.markdown("**探索ユニバース**（1行1銘柄・`コード 名前`。米国株/指数もOK）")
    default_text = ""
    try:
        with open(DEFAULT_UNIVERSE, encoding="utf-8") as f:
            default_text = f.read()
    except OSError:
        default_text = "^SOX 半導体指数\nNVDA エヌビディア\n8035 東京エレクトロン\n6857 アドバンテスト"
    uni_text = st.text_area("ユニバース", value=default_text, height=180,
                            label_visibility="collapsed")
    only_leaders = st.checkbox("候補に『先行している』銘柄だけ表示（先行指標探し）", value=False)
    go = st.button("🔎 連動ランキングを出す", key="rk_go")
    if not go:
        st.info("候補銘柄とユニバースを確認して、ボタンを押してください。")
        return

    # テキストエリアの内容を一時ファイル同等に解釈
    symbols, names = _parse_universe_text(uni_text)
    target = to_yahoo_symbol(target_in)
    yf_period, _n = PERIODS[period_label]

    prog = st.progress(0.0, text="データ取得中…")
    try:
        td, tp = _load(target, yf_period)
    except Exception as e:  # noqa: BLE001
        st.error(f"候補 {target} を取得できません: {e}")
        return
    hist: dict[str, tuple[list[str], list[float]]] = {}
    total = max(1, len(symbols))
    for i, s in enumerate(symbols):
        if s != target:
            try:
                hist[s] = _load(s, yf_period)
            except Exception:  # noqa: BLE001 - 取得不可はスキップ
                pass
        prog.progress((i + 1) / total, text=f"データ取得中… {i+1}/{total}")
    prog.empty()

    rows = rank_peers(target, td, tp, hist, names=names, mode=mode)
    if only_leaders:
        rows = [r for r in rows if r.best_lag > 0]
    if not rows:
        st.warning("該当がありませんでした。ユニバース・期間を見直してください。")
        return

    st.success(f"{target} {names.get(target,'')} と連動する銘柄  上位{int(top)}"
               f"（{mode_label}・共通{rows[0].n_days}日で測定）")
    table = pd.DataFrame([{
        "銘柄": r.symbol, "名前": r.name,
        "相関": round(r.best_corr, 2),
        "β(%)": round(r.best_beta * 100, 1),
        "関係": r.relation, "強さ": r.strength,
        "時間差": r.lead_note, "同日相関": round(r.corr0, 2),
    } for r in rows[:int(top)]])
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.bar_chart(table.set_index("銘柄")["相関"])
    st.caption("※ 過去の統計であり将来を保証しません。売買は自己責任で。")


def _parse_universe_text(text: str):
    symbols, names, seen = [], {}, set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        sym = to_yahoo_symbol(parts[0])
        if sym in seen:
            continue
        seen.add(sym)
        symbols.append(sym)
        if len(parts) > 1:
            names[sym] = parts[1].strip()
    return symbols, names


# ── レイアウト ──────────────────────────────────────────────────────────
st.markdown("### 🔎 自由ペア分析 / 連動ランキング")
t1, t2 = st.tabs(["ペア分析（1対1）", "連動ランキング（候補×みんな）"])
with t1:
    tab_pair()
with t2:
    tab_rank()
