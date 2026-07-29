# -*- coding: utf-8 -*-
"""
連動ランキング — 候補1銘柄 vs ユニバース（多銘柄）で、動きが連動する相手を探す。

「総当たり(N×N)」ではなく「候補×みんな(1×N)」なので計算量は N に比例するだけ。
日経225なら225回、東証全体でも約4000回で、普通のPCで十分動く。

2つの見方:
  - 同日連動（lag=0）  : 同じ日に一緒に動くか（連れ高／連れ安）
  - 時間差（先行→後続）: 何日かずらすと最も連動が強くなる関係
                         → 「この銘柄が動くと、翌日に候補が動く」先行指標探し
"""

from __future__ import annotations

from dataclasses import dataclass

from .analysis import align, linreg, pct_returns


def corr_beta_at_lag(
    target_ret: list[float], cand_ret: list[float], lag: int,
) -> tuple[float, float, int]:
    """
    候補を lag 日ずらしたときの (beta, 相関r, 標本数) を返す。

    lag>0 : 候補が target に対して lag 日「先行」（候補の動き → lag日後に target）
    lag<0 : target が候補に対して先行
    lag=0 : 同日
    """
    if lag > 0:
        x = cand_ret[:len(cand_ret) - lag]
        y = target_ret[lag:]
    elif lag < 0:
        k = -lag
        x = cand_ret[k:]
        y = target_ret[:len(target_ret) - k]
    else:
        x, y = cand_ret, target_ret
    n = min(len(x), len(y))
    if n < 5:
        return 0.0, 0.0, n
    slope, _b, r = linreg(x[:n], y[:n])
    return slope, r, n


def _strength(corr: float) -> str:
    a = abs(corr)
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
    corr0: float          # 同日相関
    beta0: float          # 同日ベータ
    best_lag: int         # 相関が最大化するラグ（+:候補が先行 / -:候補が後続）
    best_corr: float      # そのラグでの相関
    best_beta: float
    relation: str         # 「順（連れ高）」/「逆（ヘッジ候補）」
    strength: str         # best_corr の強さラベル
    lead_note: str        # 「候補が2日先行」等の説明（target 視点）


def _lead_note(target: str, symbol: str, lag: int) -> str:
    if lag > 0:
        return f"{symbol} が {lag}日先行"
    if lag < 0:
        return f"{target} が {-lag}日先行"
    return "同時"


def rank_peers(
    target: str,
    target_dates: list[str], target_prices: list[float],
    candidates: dict[str, tuple[list[str], list[float]]],
    names: dict[str, str] | None = None,
    lags: tuple[int, ...] = (-2, -1, 0, 1, 2, 3),
    mode: str = "time_lag",     # "time_lag" or "same_day"
    min_days: int = 30,
) -> list[RankRow]:
    """
    target に対して各候補の連動を測り、強い順に並べる。

    - mode="same_day": 同日相関 |corr0| で並べる（素直な連動銘柄）。
    - mode="time_lag": ラグ全体で最も強い |corr| で並べる（先行→後続を含む）。
    銘柄ごとに共通営業日で突き合わせてからリターン化するので、市場（日本/米国）が
    違っても営業日カレンダーの差を吸収できる。
    """
    names = names or {}
    rows: list[RankRow] = []

    for sym, (c_dates, c_prices) in candidates.items():
        if sym == target:
            continue
        # 共通営業日で突き合わせ（米国×日本のカレンダー差を吸収）
        _d, tp, cp = align(target_dates, target_prices, c_dates, c_prices)
        if len(tp) < min_days:
            continue
        t_ret = pct_returns(tp)
        c_ret = pct_returns(cp)

        beta0, corr0, _n0 = corr_beta_at_lag(t_ret, c_ret, 0)

        # ラグ全体で最も相関の強い点を探す
        best_lag, best_corr, best_beta = 0, corr0, beta0
        for L in lags:
            b, r, n = corr_beta_at_lag(t_ret, c_ret, L)
            if n < min_days:
                continue
            if abs(r) > abs(best_corr):
                best_lag, best_corr, best_beta = L, r, b

        key_corr = best_corr if mode == "time_lag" else corr0
        rows.append(RankRow(
            symbol=sym,
            name=names.get(sym, ""),
            n_days=len(t_ret),
            corr0=corr0,
            beta0=beta0,
            best_lag=best_lag,
            best_corr=best_corr,
            best_beta=best_beta,
            relation="順（連れ高）" if key_corr >= 0 else "逆（ヘッジ候補）",
            strength=_strength(key_corr),
            lead_note=_lead_note(target, sym, best_lag),
        ))

    keyfn = ((lambda r: abs(r.best_corr)) if mode == "time_lag"
             else (lambda r: abs(r.corr0)))
    rows.sort(key=keyfn, reverse=True)
    return rows
