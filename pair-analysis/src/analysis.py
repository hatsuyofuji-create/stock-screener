# -*- coding: utf-8 -*-
"""
先行→後続（リード・ラグ）分析のコア計算。

方針:
  - ここは **純Python**（pandas / numpy 不要）。データ取得やUIから独立させ、
    ネット接続なしで単体テストできるようにする。
  - 入力は「日付（昇順の文字列）」と「終値（float）」の2列だけ。提供元は
    data/provider.py 経由で差し替える（yahoo / synthetic）。

用語:
  - 先行 (leader):  先に動く銘柄・指数（例: TSMC, ^SOX）
  - 後続 (follower): 遅れて動く銘柄（例: 6146 ディスコ）
  - lag: 後続を先行に対して何営業日ずらして測るか。米欧→日本は 1（翌営業日）、
         同時間帯（日本→日本 など）の「連れ高確認」は 0。
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── 基本統計（純Python） ────────────────────────────────────────────────

def pct_returns(prices: list[float]) -> list[float]:
    """終値リストから日次リターン（前日比）を返す。長さは len-1。"""
    out: list[float] = []
    for prev, cur in zip(prices, prices[1:]):
        if prev == 0:
            out.append(0.0)
        else:
            out.append(cur / prev - 1.0)
    return out


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def linreg(x: list[float], y: list[float]) -> tuple[float, float, float]:
    """
    最小二乗回帰 y = slope*x + intercept と ピアソン相関 r を返す。
    データ不足や分散ゼロなら (0, 0, 0)。
    """
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
    intercept = my - slope * mx
    denom = (sxx * syy) ** 0.5
    r = sxy / denom if denom > 0 else 0.0
    return slope, intercept, r


def align(
    dates_a: list[str], prices_a: list[float],
    dates_b: list[str], prices_b: list[float],
) -> tuple[list[str], list[float], list[float]]:
    """2系列を共通日付（昇順）で突き合わせる。"""
    map_a = dict(zip(dates_a, prices_a))
    map_b = dict(zip(dates_b, prices_b))
    common = sorted(set(map_a) & set(map_b))
    return common, [map_a[d] for d in common], [map_b[d] for d in common]


# ── 結果コンテナ ────────────────────────────────────────────────────────

@dataclass
class EventStat:
    """しきい値を超えた急変日についての追随集計（上げ／下げの片側）。"""
    n: int                      # 該当した急変日数
    follow_rate: float          # 追随率（同方向に動いた割合 0..1）
    avg_move: float             # 後続の平均リターン（lag日後）
    direction: str              # "up" / "down"


@dataclass
class PairResult:
    leader: str
    follower: str
    lag: int
    n_days: int                 # 回帰に使った営業日数
    beta: float                 # 先行1に対する後続の動き（回帰の傾き）
    corr: float                 # ピアソン相関 r（＝つながりの太さ）
    thickness: str              # "太い" / "中" / "細い"
    up: EventStat
    down: EventStat
    scatter: list[tuple[float, float, bool]] = field(default_factory=list)
    #        (先行リターン, 後続リターン, 追随フラグ)
    overlay_dates: list[str] = field(default_factory=list)
    overlay_leader: list[float] = field(default_factory=list)   # 開始=100で正規化
    overlay_follower: list[float] = field(default_factory=list)


# ── 太さ判定 ────────────────────────────────────────────────────────────

def classify_thickness(corr: float, warm: float = 0.15, hot: float = 0.25) -> str:
    """相関の絶対値から「太い/中/細い」を判定（翌営業日は ±0.15/0.25 が目安）。"""
    a = abs(corr)
    if a >= hot:
        return "太い"
    if a >= warm:
        return "中"
    return "細い"


# ── メイン ──────────────────────────────────────────────────────────────

def _event_stat(
    lead_ret: list[float], foll_ret_lagged: list[float],
    threshold: float, direction: str,
) -> tuple[EventStat, list[tuple[float, float, bool]]]:
    """
    先行が threshold を超えて急変した日を抽出し、後続(lag後)の追随を集計する。
    direction="up" は先行>+thr かつ後続>0 を追随、"down" は先行<-thr かつ後続<0。
    """
    scatter: list[tuple[float, float, bool]] = []
    moves: list[float] = []
    follows = 0
    for lr, fr in zip(lead_ret, foll_ret_lagged):
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
    stat = EventStat(
        n=n,
        follow_rate=(follows / n) if n else 0.0,
        avg_move=_mean(moves),
        direction=direction,
    )
    return stat, scatter


def analyze_pair(
    leader: str, follower: str,
    dates_l: list[str], prices_l: list[float],
    dates_f: list[str], prices_f: list[float],
    lag: int = 1,
    threshold: float = 0.03,
) -> PairResult:
    """
    先行→後続の連動を測る。

    - beta / corr は全営業日で測る（しきい値に依らない）。
    - up / down のイベント集計は threshold を超えた急変日だけで測る。
    - lag>0 のとき、後続を lag 日ぶん未来にずらして先行に対応させる
      （米欧→日本の「翌営業日に伝わる分」を測るため）。
    """
    dates, pl, pf = align(dates_l, prices_l, dates_f, prices_f)
    if len(dates) < lag + 3:
        empty = EventStat(0, 0.0, 0.0, "up")
        return PairResult(
            leader, follower, lag, 0, 0.0, 0.0, "細い",
            empty, EventStat(0, 0.0, 0.0, "down"),
        )

    lead_ret = pct_returns(pl)     # 長さ N-1、日 t は dates[t+1] のリターン
    foll_ret = pct_returns(pf)

    # 後続を lag 日ぶん未来へずらして先行に対応させる
    if lag > 0:
        x = lead_ret[:-lag]
        y = foll_ret[lag:]
    else:
        x = lead_ret
        y = foll_ret

    slope, _intercept, r = linreg(x, y)
    up_stat, up_sc = _event_stat(x, y, threshold, "up")
    down_stat, down_sc = _event_stat(x, y, threshold, "down")

    # 重ね描き（共通開始=100 で正規化）
    base_l = pl[0] or 1.0
    base_f = pf[0] or 1.0
    overlay_l = [p / base_l * 100.0 for p in pl]
    overlay_f = [p / base_f * 100.0 for p in pf]

    return PairResult(
        leader=leader,
        follower=follower,
        lag=lag,
        n_days=len(x),
        beta=slope,
        corr=r,
        thickness=classify_thickness(r),
        up=up_stat,
        down=down_stat,
        scatter=up_sc + down_sc,
        overlay_dates=dates,
        overlay_leader=overlay_l,
        overlay_follower=overlay_f,
    )
