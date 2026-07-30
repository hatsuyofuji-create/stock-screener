# -*- coding: utf-8 -*-
"""
連動率（同方向率）と条件分解。

しんぽこさん設計の主指標。
  連動率 = 同じ日（ラグ考慮）に「同じ方向へ動いた」割合(%)。
           ランダムなら約50%、強く連れて動くほど70〜95%に上がる。
  条件分解:
    - 曜日別（月曜だけ95%、のような偏りを出す）
    - 期間別（直近 vs それ以前）＋トレンド（前50→今90 のように上がってきたか）

純Python。ネット不要で単体テストできる。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]


def _sign(v: float) -> int:
    return 1 if v > 0 else (-1 if v < 0 else 0)


def same_dir_rate(x: list[float], y: list[float]) -> tuple[float, int]:
    """
    同方向率を返す (rate, 有効日数)。
    どちらかが 0（動かない）の日は分母から除く。
    """
    n = 0
    agree = 0
    for a, b in zip(x, y):
        sa, sb = _sign(a), _sign(b)
        if sa == 0 or sb == 0:
            continue
        n += 1
        if sa == sb:
            agree += 1
    return (agree / n if n else 0.0), n


@dataclass
class CoactStat:
    overall: float                      # 全体の連動率(0..1)
    n: int                              # 有効日数
    weekday: dict[int, tuple[float, int]] = field(default_factory=dict)  # 0=月..4=金 -> (率, 日数)
    best_wd: int = -1                   # 連動率が最も高い曜日（-1=該当なし）
    best_wd_rate: float = 0.0
    best_wd_n: int = 0
    recent: float = 0.0                 # 直近ウィンドウの連動率
    prior: float = 0.0                  # それ以前の連動率
    trend: float = 0.0                  # recent - prior（＋なら上がってきた）

    def best_weekday_label(self) -> str:
        if self.best_wd < 0:
            return "-"
        return f"{WEEKDAYS_JP[self.best_wd]}曜 {self.best_wd_rate*100:.0f}%"

    def trend_label(self) -> str:
        if self.trend > 0.05:
            return f"上昇中(前{self.prior*100:.0f}→今{self.recent*100:.0f})"
        if self.trend < -0.05:
            return f"低下中(前{self.prior*100:.0f}→今{self.recent*100:.0f})"
        return f"横ばい(前{self.prior*100:.0f}→今{self.recent*100:.0f})"


def coactivity(
    dates: list[str], x: list[float], y: list[float],
    recent_frac: float = 0.5, min_wd_days: int = 8,
) -> CoactStat:
    """
    連動率と条件分解を計算する。

    dates : 各ペア（x[i], y[i]）に対応する「先行側の日付」(YYYY-MM-DD、昇順)
    x, y  : ラグ調整済みの先行/後続リターン列（同じ長さ）
    """
    overall, n = same_dir_rate(x, y)

    # 曜日別（0=月〜4=金）
    weekday: dict[int, tuple[float, int]] = {}
    best_wd, best_rate, best_n = -1, 0.0, 0
    buckets: dict[int, tuple[list[float], list[float]]] = {i: ([], []) for i in range(5)}
    for d, a, b in zip(dates, x, y):
        try:
            wd = _dt.date.fromisoformat(d).weekday()
        except ValueError:
            continue
        if wd < 5:
            buckets[wd][0].append(a)
            buckets[wd][1].append(b)
    for wd in range(5):
        r, c = same_dir_rate(buckets[wd][0], buckets[wd][1])
        weekday[wd] = (r, c)
        if c >= min_wd_days and r > best_rate:
            best_wd, best_rate, best_n = wd, r, c

    # 期間別（直近 recent_frac を「今」、残りを「以前」）＋トレンド
    m = len(x)
    k = max(1, int(m * recent_frac))
    prior, _ = same_dir_rate(x[:m - k], y[:m - k])
    recent, _ = same_dir_rate(x[m - k:], y[m - k:])

    return CoactStat(
        overall=overall, n=n, weekday=weekday,
        best_wd=best_wd, best_wd_rate=best_rate, best_wd_n=best_n,
        recent=recent, prior=prior, trend=recent - prior,
    )
