# -*- coding: utf-8 -*-
"""
自由ペア分析 / 連動ランキング — 自己完結版（このファイル1つで全機能）

これ1ファイル＋起動バッチだけで動きます（src/ や universe/ フォルダ不要）。
    PRICE_PROVIDER=yahoo streamlit run app.py   # 本番（yfinance）
    streamlit run app.py                        # オフライン確認（synthetic）
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import os
import random
from dataclasses import dataclass, field

import pandas as pd
import streamlit as st

# ══════════════════════════════════════════════════════════════════════
#  探索ユニバース（埋め込み）— コード 名前 の1行1銘柄
# ══════════════════════════════════════════════════════════════════════
US_LEADERS = """
^SOX     フィラデルフィア半導体指数
^GSPC    S&P500
^IXIC    ナスダック総合
^DJI     NYダウ
^N225    日経平均
NVDA     エヌビディア
TSM      TSMC(米ADR)
AMD      AMD
MU       マイクロン
INTC     インテル
AVGO     ブロードコム
QCOM     クアルコム
TXN      テキサスインスツルメンツ
ASML     ASML
AMAT     アプライドマテリアルズ
LRCX     ラムリサーチ
KLAC     KLA
AAPL     アップル
MSFT     マイクロソフト
AMZN     アマゾン
GOOGL    アルファベット
META     メタ
TSLA     テスラ
FCX      フリーポート(銅)
CL=F     WTI原油先物
GC=F     金先物
HG=F     銅先物
"""

NIKKEI225 = """
6501  日立製作所
6503  三菱電機
6504  富士電機
6506  安川電機
6594  ニデック
6645  オムロン
6674  GSユアサ
6701  NEC
6702  富士通
6752  パナソニックHD
6753  シャープ
6758  ソニーグループ
6762  TDK
6770  アルプスアルパイン
6841  横河電機
6857  アドバンテスト
6861  キーエンス
6902  デンソー
6952  カシオ計算機
6954  ファナック
6971  京セラ
6976  太陽誘電
6981  村田製作所
6988  日東電工
6098  リクルートHD
6146  ディスコ
6920  レーザーテック
6963  ローム
6723  ルネサスエレクトロニクス
6479  ミネベアミツミ
6724  セイコーエプソン
4062  イビデン
3436  SUMCO
7735  SCREENホールディングス
7751  キヤノン
7752  リコー
8035  東京エレクトロン
7731  ニコン
7733  オリンパス
7741  HOYA
7762  シチズン時計
4543  テルモ
7201  日産自動車
7202  いすゞ自動車
7203  トヨタ自動車
7205  日野自動車
7211  三菱自動車
7261  マツダ
7267  ホンダ
7269  スズキ
7270  SUBARU
7272  ヤマハ発動機
6103  オークマ
6113  アマダ
6273  SMC
6301  コマツ
6302  住友重機械工業
6305  日立建機
6326  クボタ
6361  荏原製作所
6367  ダイキン工業
6471  日本精工
6472  NTN
6473  ジェイテクト
7004  カナデビア
7011  三菱重工業
7012  川崎重工業
7013  IHI
3401  帝人
3402  東レ
3405  クラレ
3407  旭化成
4004  レゾナックHD
4005  住友化学
4021  日産化学
4042  東ソー
4043  トクヤマ
4061  デンカ
4063  信越化学工業
4183  三井化学
4188  三菱ケミカルグループ
4208  UBE
4452  花王
4901  富士フイルムHD
4911  資生堂
3861  王子ホールディングス
3863  日本製紙
4151  協和キリン
4502  武田薬品工業
4503  アステラス製薬
4506  住友ファーマ
4507  塩野義製薬
4519  中外製薬
4523  エーザイ
4568  第一三共
4578  大塚ホールディングス
1332  ニッスイ
2002  日清製粉グループ本社
2269  明治ホールディングス
2282  日本ハム
2501  サッポロHD
2502  アサヒグループHD
2503  キリンHD
2531  宝ホールディングス
2801  キッコーマン
2802  味の素
2871  ニチレイ
2897  日清食品HD
2914  JT
3086  Jフロント リテイリング
3099  三越伊勢丹HD
3382  セブン&アイHD
8233  高島屋
8267  イオン
9983  ファーストリテイリング
3092  ZOZO
4661  オリエンタルランド
4689  LINEヤフー
4704  トレンドマイクロ
4751  サイバーエージェント
4755  楽天グループ
2413  エムスリー
4307  野村総合研究所
4324  電通グループ
4385  メルカリ
2432  ディー・エヌ・エー
9602  東宝
9613  NTTデータグループ
9697  カプコン
9766  コナミグループ
9735  セコム
9843  ニトリHD
9962  ミスミグループ本社
6178  日本郵政
7182  ゆうちょ銀行
8306  三菱UFJフィナンシャル・グループ
8308  りそなHD
8309  三井住友トラストHD
8316  三井住友フィナンシャルグループ
8331  千葉銀行
8354  ふくおかFG
8411  みずほフィナンシャルグループ
8253  クレディセゾン
8591  オリックス
8601  大和証券グループ本社
8604  野村ホールディングス
8630  SOMPOホールディングス
8697  日本取引所グループ
8725  MS&ADインシュアランスG
8750  第一生命ホールディングス
8766  東京海上ホールディングス
8795  T&Dホールディングス
8252  丸井グループ
2768  双日
8001  伊藤忠商事
8002  丸紅
8015  豊田通商
8031  三井物産
8053  住友商事
8058  三菱商事
5101  横浜ゴム
5108  ブリヂストン
5201  AGC
5202  日本板硝子
5214  日本電気硝子
5233  太平洋セメント
5301  東海カーボン
5332  TOTO
5333  日本ガイシ
5401  日本製鉄
5406  神戸製鋼所
5411  JFEホールディングス
5541  大平洋金属
5631  日本製鋼所
5703  日本軽金属HD
5706  三井金属鉱業
5711  三菱マテリアル
5713  住友金属鉱山
5714  DOWAホールディングス
5801  古河電気工業
5802  住友電気工業
5803  フジクラ
1605  INPEX
1662  石油資源開発
5019  出光興産
5020  ENEOSホールディングス
1721  コムシスHD
1801  大成建設
1802  大林組
1803  清水建設
1808  長谷工コーポレーション
1812  鹿島建設
1925  大和ハウス工業
1928  積水ハウス
1963  日揮ホールディングス
8801  三井不動産
8802  三菱地所
8804  東京建物
8830  住友不動産
9001  東武鉄道
9005  東急
9007  小田急電鉄
9008  京王電鉄
9009  京成電鉄
9020  東日本旅客鉄道
9021  西日本旅客鉄道
9022  東海旅客鉄道
9064  ヤマトホールディングス
9101  日本郵船
9104  商船三井
9107  川崎汽船
9147  NIPPON EXPRESS HD
9201  日本航空
9202  ANAホールディングス
9301  三菱倉庫
9501  東京電力HD
9502  中部電力
9503  関西電力
9531  東京ガス
9532  大阪ガス
9432  日本電信電話(NTT)
9433  KDDI
9434  ソフトバンク
9984  ソフトバンクグループ
"""

PRESETS: dict[str, str] = {
    "日経225＋米国リーダー（推奨・広い）": US_LEADERS + NIKKEI225,
    "日経225のみ": NIKKEI225,
    "米国リーダー・指数のみ": US_LEADERS,
}

# ══════════════════════════════════════════════════════════════════════
#  シンボル・期間ユーティリティ
# ══════════════════════════════════════════════════════════════════════
PERIODS: dict[str, tuple[str, int]] = {
    "半年": ("6mo", 120), "1年": ("1y", 245), "2年": ("2y", 490),
    "3年": ("3y", 735), "5年": ("5y", 1225),
}


def to_yahoo_symbol(code: str) -> str:
    s = code.strip().upper()
    if not s or s.startswith("^") or "." in s:
        return s
    if s.isdigit():
        return f"{s}.T"
    return s


def classify_market(code: str) -> str:
    s = code.strip().upper()
    if s.startswith("^"):
        if s in {"^N225", "^TPX"}:
            return "JP"
        return "US"
    if s.endswith((".KS", ".KQ")):
        return "KR"
    if s.endswith((".TW", ".TWO")):
        return "TW"
    if s.endswith(".T") or s.isdigit():
        return "JP"
    if "." in s:
        return "EU"
    return "US"


def default_lag(leader: str) -> int:
    return 1  # 米欧→日本＝翌営業日。同時間帯でも「遅れて張れる分」を既定1で測る。


def parse_universe(text: str) -> tuple[list[str], dict[str, str]]:
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


# ══════════════════════════════════════════════════════════════════════
#  コア統計（純Python）
# ══════════════════════════════════════════════════════════════════════
def pct_returns(prices: list[float]) -> list[float]:
    out = []
    for prev, cur in zip(prices, prices[1:]):
        out.append(0.0 if prev == 0 else cur / prev - 1.0)
    return out


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def linreg(x: list[float], y: list[float]) -> tuple[float, float, float]:
    n = len(x)
    if n < 2 or len(y) != n:
        return 0.0, 0.0, 0.0
    mx, my = _mean(x), _mean(y)
    sxx = sum((xi - mx) ** 2 for xi in x)
    syy = sum((yi - my) ** 2 for yi in y)
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    if sxx == 0.0:
        return 0.0, my, 0.0
    slope = sxy / sxx
    denom = (sxx * syy) ** 0.5
    r = sxy / denom if denom > 0 else 0.0
    return slope, my - slope * mx, r


def align(da, pa, db, pb):
    ma, mb = dict(zip(da, pa)), dict(zip(db, pb))
    common = sorted(set(ma) & set(mb))
    return common, [ma[d] for d in common], [mb[d] for d in common]


def classify_thickness(corr: float) -> str:
    a = abs(corr)
    return "太い" if a >= 0.25 else ("中" if a >= 0.15 else "細い")


@dataclass
class EventStat:
    n: int
    follow_rate: float
    avg_move: float
    direction: str


@dataclass
class PairResult:
    leader: str
    follower: str
    lag: int
    n_days: int
    beta: float
    corr: float
    thickness: str
    up: EventStat
    down: EventStat
    scatter: list = field(default_factory=list)
    overlay_dates: list = field(default_factory=list)
    overlay_leader: list = field(default_factory=list)
    overlay_follower: list = field(default_factory=list)


def _event_stat(lead_ret, foll_ret, threshold, direction):
    scatter, moves, follows = [], [], 0
    for lr, fr in zip(lead_ret, foll_ret):
        if direction == "up" and lr > threshold:
            followed = fr > 0
        elif direction == "down" and lr < -threshold:
            followed = fr < 0
        else:
            continue
        moves.append(fr)
        follows += 1 if followed else 0
        scatter.append((lr, fr, followed))
    n = len(moves)
    return EventStat(n, (follows / n) if n else 0.0, _mean(moves), direction), scatter


def analyze_pair(leader, follower, dl, pl, df_, pf, lag=1, threshold=0.03):
    dates, pl, pf = align(dl, pl, df_, pf)
    if len(dates) < lag + 3:
        e = EventStat(0, 0.0, 0.0, "up")
        return PairResult(leader, follower, lag, 0, 0.0, 0.0, "細い", e,
                          EventStat(0, 0.0, 0.0, "down"))
    lr, fr = pct_returns(pl), pct_returns(pf)
    if lag > 0:
        x, y = lr[:-lag], fr[lag:]
    else:
        x, y = lr, fr
    slope, _b, r = linreg(x, y)
    up, up_sc = _event_stat(x, y, threshold, "up")
    down, dn_sc = _event_stat(x, y, threshold, "down")
    bl, bf = pl[0] or 1.0, pf[0] or 1.0
    return PairResult(leader, follower, lag, len(x), slope, r,
                      classify_thickness(r), up, down, up_sc + dn_sc, dates,
                      [p / bl * 100 for p in pl], [p / bf * 100 for p in pf])


# ── 連動ランキング ─────────────────────────────────────────────────────
def corr_beta_at_lag(t_ret, c_ret, lag):
    if lag > 0:
        x, y = c_ret[:len(c_ret) - lag], t_ret[lag:]
    elif lag < 0:
        k = -lag
        x, y = c_ret[k:], t_ret[:len(t_ret) - k]
    else:
        x, y = c_ret, t_ret
    n = min(len(x), len(y))
    if n < 5:
        return 0.0, 0.0, n
    slope, _b, r = linreg(x[:n], y[:n])
    return slope, r, n


def _strength(c):
    a = abs(c)
    if a >= 0.6:
        return "非常に強い"
    if a >= 0.4:
        return "強い"
    if a >= 0.25:
        return "中"
    if a >= 0.15:
        return "弱い"
    return "ほぼ無"


@dataclass
class RankRow:
    symbol: str
    name: str
    n_days: int
    corr0: float
    best_lag: int
    best_corr: float
    best_beta: float
    relation: str
    strength: str
    lead_note: str


def rank_peers(target, td, tp, cands, names, mode="time_lag", min_days=30,
               lags=(-2, -1, 0, 1, 2, 3)):
    rows = []
    for sym, (cd, cp) in cands.items():
        if sym == target:
            continue
        _d, tpp, cpp = align(td, tp, cd, cp)
        if len(tpp) < min_days:
            continue
        t_ret, c_ret = pct_returns(tpp), pct_returns(cpp)
        beta0, corr0, _n0 = corr_beta_at_lag(t_ret, c_ret, 0)
        best_lag, best_corr, best_beta = 0, corr0, beta0
        for L in lags:
            b, r, n = corr_beta_at_lag(t_ret, c_ret, L)
            if n >= min_days and abs(r) > abs(best_corr):
                best_lag, best_corr, best_beta = L, r, b
        key = best_corr if mode == "time_lag" else corr0
        if best_lag > 0:
            note = f"{sym} が {best_lag}日先行"
        elif best_lag < 0:
            note = f"{target} が {-best_lag}日先行"
        else:
            note = "同時"
        rows.append(RankRow(sym, names.get(sym, ""), len(t_ret), corr0, best_lag,
                            best_corr, best_beta,
                            "順（連れ高）" if key >= 0 else "逆（ヘッジ候補）",
                            _strength(key), note))
    keyfn = ((lambda r: abs(r.best_corr)) if mode == "time_lag"
             else (lambda r: abs(r.corr0)))
    rows.sort(key=keyfn, reverse=True)
    return rows


# ══════════════════════════════════════════════════════════════════════
#  データ取得（yahoo / synthetic）
# ══════════════════════════════════════════════════════════════════════
def _business_days(n, end=_dt.date(2026, 7, 24)):
    days, d = [], end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d -= _dt.timedelta(days=1)
    return list(reversed(days))


def _synthetic(symbol, period):
    n = {"6mo": 120, "1y": 245, "2y": 490, "3y": 735, "5y": 1225}.get(period, 490)
    rng = random.Random(int(hashlib.sha256(symbol.encode()).hexdigest(), 16) % 2**32)
    price, closes = 100.0, []
    for _ in range(n):
        price *= (1 + rng.gauss(0.0004, 0.02))
        closes.append(round(price, 4))
    return _business_days(n), closes


def _yahoo(symbol, period):
    import yfinance as yf
    df = yf.download(symbol, period=period, interval="1d",
                     auto_adjust=True, progress=False, threads=False)
    if df is None or df.empty:
        raise RuntimeError(f"データ取得不可: {symbol}")
    close = df["Close"]
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]
    close = close.dropna()
    return [d.date().isoformat() for d in close.index], [float(v) for v in close.values]


@st.cache_data(show_spinner=False)
def load_history(symbol, period):
    provider = (os.getenv("PRICE_PROVIDER") or "yahoo").strip().lower()
    if provider in ("synthetic", "mock"):
        return _synthetic(symbol, period)
    return _yahoo(symbol, period)


# ══════════════════════════════════════════════════════════════════════
#  UI
# ══════════════════════════════════════════════════════════════════════
st.set_page_config(page_title="自由ペア分析", page_icon="🔎", layout="wide")
THRESHOLDS = {"±3%（標準）": 0.03, "±5%（大波のみ）": 0.05}


def tab_pair():
    st.caption("好きなペアをその場で測定。先行は日本株コード・米国ティッカー(MU/NVDA)・"
               "指数(^SOX)・韓国(.KS)・台湾(.TW)に対応。翌日相関とβが「遅れて伝わる分＝張れる余地」。")
    c1, c2, c3, c4, c5 = st.columns([2, 2, 1.5, 2, 1])
    leader_in = c1.text_input("先行", "TSM")
    follower_in = c2.text_input("後続", "6146")
    period = c3.selectbox("期間", list(PERIODS), index=2)
    thr_label = c4.selectbox("急変しきい値", list(THRESHOLDS))
    c5.write("")
    c5.button("⚡分析", use_container_width=True, key="p_go")

    leader, follower = to_yahoo_symbol(leader_in), to_yahoo_symbol(follower_in)
    yf_period = PERIODS[period][0]
    thr = THRESHOLDS[thr_label]
    try:
        dl, pl = load_history(leader, yf_period)
        df_, pf = load_history(follower, yf_period)
    except Exception as e:
        st.error(f"データ取得に失敗: {e}")
        return
    res = analyze_pair(leader, follower, dl, pl, df_, pf, default_lag(leader), thr)
    if res.n_days == 0:
        st.warning("共通の営業日が足りません。")
        return
    st.info(f"{res.leader} → {res.follower}（{res.n_days}日・しきい値±{thr*100:.0f}%・lag={res.lag}）")
    m = st.columns(4)
    m[0].metric("ベータ（先行1%→後続）", f"{res.beta*100:+.2f}%")
    m[1].metric("つながりの太さ", res.thickness, help=f"相関 r={res.corr:+.2f}")
    u, d = res.up, res.down
    m[2].metric(f"↑急騰時 追随率{' ⚠回数少' if u.n < 30 else ''}",
                f"{u.follow_rate*100:.1f}%", f"{u.n}回中・平均{u.avg_move*100:+.2f}%")
    m[3].metric(f"↓急落時 追随率{' ⚠回数少' if d.n < 30 else ''}",
                f"{d.follow_rate*100:.1f}%", f"{d.n}回中・平均{d.avg_move*100:+.2f}%")
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**株価の重ね描き（共通開始=100）**")
        st.line_chart(pd.DataFrame({res.leader: res.overlay_leader,
                                    res.follower: res.overlay_follower},
                                   index=pd.to_datetime(res.overlay_dates)))
    with g2:
        st.markdown("**急変日の散布図（先行→後続 %）**")
        if res.scatter:
            sc = pd.DataFrame([(lr*100, fr*100, "追随" if f else "逆行")
                               for lr, fr, f in res.scatter],
                              columns=["先行%", "後続%", "判定"])
            st.scatter_chart(sc, x="先行%", y="後続%", color="判定")
        else:
            st.write("急変日がありませんでした。")


def tab_rank():
    st.caption("候補1銘柄を入れると、ユニバースから動きが連動する銘柄を探して並べます。"
               "『先行→後続』重視だと、候補に先行している＝先行指標になりうる銘柄が上位に出ます。")
    c1, c2, c3, c4 = st.columns([2, 1.5, 2, 1.5])
    target_in = c1.text_input("候補銘柄", "6146", key="r_t")
    period = c2.selectbox("期間", list(PERIODS), index=2, key="r_p")
    mode_label = c3.selectbox("並べ方", ["時間差（先行→後続）重視", "同日連動を重視"], key="r_m")
    top = c4.number_input("表示件数", 5, 100, 20, key="r_top")
    mode = "time_lag" if mode_label.startswith("時間差") else "same_day"

    st.markdown("**探索ユニバース**（連動相手を探す銘柄群）")
    preset = st.selectbox("プリセット", list(PRESETS), index=0, key="r_pre")
    uni_text = st.text_area("ユニバース", PRESETS[preset].strip(), height=200,
                            key=f"r_uni_{preset}", label_visibility="collapsed",
                            help="1行1銘柄・`コード 名前`。米国株/指数もOK。自由に編集できます。")
    symbols, names = parse_universe(uni_text)
    st.caption(f"探索対象: 約{len(symbols)}銘柄"
               + ("（多いので取得に数分かかることがあります）" if len(symbols) > 60 else ""))
    only_leaders = st.checkbox("候補に『先行している』銘柄だけ表示（先行指標探し）", False)
    if not st.button("🔎 連動ランキングを出す", key="r_go"):
        st.info("候補銘柄とユニバースを確認して、ボタンを押してください。")
        return

    target = to_yahoo_symbol(target_in)
    yf_period = PERIODS[period][0]
    try:
        td, tp = load_history(target, yf_period)
    except Exception as e:
        st.error(f"候補 {target} を取得できません: {e}")
        return
    prog = st.progress(0.0, text="データ取得中…")
    hist, total = {}, max(1, len(symbols))
    for i, s in enumerate(symbols):
        if s != target:
            try:
                hist[s] = load_history(s, yf_period)
            except Exception:
                pass
        prog.progress((i + 1) / total, text=f"データ取得中… {i+1}/{total}")
    prog.empty()

    rows = rank_peers(target, td, tp, hist, names, mode)
    if only_leaders:
        rows = [r for r in rows if r.best_lag > 0]
    if not rows:
        st.warning("該当がありませんでした。")
        return
    st.success(f"{target} {names.get(target,'')} と連動する銘柄  上位{int(top)}"
               f"（{mode_label}・共通{rows[0].n_days}日で測定）")
    table = pd.DataFrame([{
        "銘柄": r.symbol, "名前": r.name, "相関": round(r.best_corr, 2),
        "β(%)": round(r.best_beta*100, 1), "関係": r.relation, "強さ": r.strength,
        "時間差": r.lead_note, "同日相関": round(r.corr0, 2),
    } for r in rows[:int(top)]])
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.bar_chart(table.set_index("銘柄")["相関"])
    st.caption("※ 過去の統計であり将来を保証しません。売買は自己責任で。")


st.markdown("### 🔎 自由ペア分析 / 連動ランキング")
t1, t2 = st.tabs(["ペア分析（1対1）", "連動ランキング（候補×みんな）"])
with t1:
    tab_pair()
with t2:
    tab_rank()
