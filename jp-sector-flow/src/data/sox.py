# -*- coding: utf-8 -*-
"""
SOX（フィラデルフィア半導体株指数・米国）の参考データ取得。

J-Quants は日本株専用のため、SOX は yfinance（ティッカー ^SOX）で別取得する。
日本の電気機器・半導体を先導する指標として、参考表示に使う。

取得失敗（ネットワーク等）でも本体を止めないよう、失敗時は None を返す。
"""

from __future__ import annotations

HORIZONS = [5, 15, 30, 150]  # money_flow.HORIZONS と揃える


def get_sox() -> dict | None:
    """
    戻り値 dict（失敗時 None）:
      - "level": 最新値
      - "asof": 最新値の日付（YYYY-MM-DD）
      - "mom": {5:%, 15:%, 30:%, 150:%}  各期間の変化率
    """
    try:
        import yfinance as yf

        hist = yf.Ticker("^SOX").history(period="1y", interval="1d")
        close = hist["Close"].dropna()
        if len(close) < 2:
            print("[SOX] 終値データが不足")
            return None
        level = float(close.iloc[-1])
        asof = close.index[-1].strftime("%Y-%m-%d")
        mom: dict[int, float] = {}
        for d in HORIZONS:
            past = close.iloc[-(d + 1)] if len(close) > d else close.iloc[0]
            mom[d] = round(float((level / past - 1.0) * 100.0), 2)
        return {"level": round(level, 1), "asof": asof, "mom": mom}
    except Exception as e:  # 取得失敗で本体を止めない
        print(f"[SOX取得失敗] {type(e).__name__}: {e}")
        return None
