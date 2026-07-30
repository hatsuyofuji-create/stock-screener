# -*- coding: utf-8 -*-
"""
JQuantsProvider: J-Quants API（V2・APIキー方式）で日本株の終値を取得する。

jp-sector-flow の実績ある実装（/equities/bars/daily を日付ごとに取得）を踏襲。
一度だけ「全銘柄 × 全営業日」の終値マトリクスを作り、以降は銘柄ごとに切り出す
（総当たりスキャンでは全銘柄を1系統の呼び出しで賄えるため効率的）。

認証（V2）:
  - ダッシュボードで発行した APIキーを環境変数 JQUANTS_API_KEY に設定
  - すべてのリクエストに  x-api-key: <APIキー>  ヘッダを付ける
  - ベースURL: https://api.jquants.com/v2（JQUANTS_BASE で上書き可）

注意: J-Quants の銘柄コードは5桁（例 トヨタ=72030）。Yahoo記法(7203.T)へは
「先頭4桁 + .T」で変換している。まれに変換が合わない銘柄はスキップされるだけで
落ちない。実データで最初に流すときに、必要ならこの変換だけ調整してください。
"""

from __future__ import annotations

import os
import time

import requests

from .provider import PriceProvider

_TIMEOUT = 30
# 期間ラベル→おおよその必要営業日数（yfinance period と整合）
_PERIOD_DAYS = {"6mo": 130, "1y": 250, "2y": 500, "3y": 750, "5y": 1250}


def _jq_code_to_yahoo(code: str) -> str | None:
    """J-Quants の5桁コードを Yahoo 記法（7203.T）へ。数字4桁が取れなければ None。"""
    c = str(code).strip()
    if len(c) == 5 and c.isdigit():
        return f"{c[:4]}.T"
    if len(c) == 4 and c.isdigit():
        return f"{c}.T"
    return None


class JQuantsProvider(PriceProvider):
    name = "jquants"

    def __init__(self) -> None:
        self.base = (os.getenv("JQUANTS_BASE") or "https://api.jquants.com/v2").rstrip("/")
        self._session = requests.Session()
        self._matrix: dict[str, list[tuple[str, float]]] | None = None  # yahoo -> [(date, close)]
        self._built_days = 0

    def _headers(self) -> dict[str, str]:
        key = os.getenv("JQUANTS_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "J-Quants の APIキーがありません。JQUANTS_API_KEY を設定してください（V2）。"
            )
        return {"x-api-key": key}

    def _get_paginated(self, path: str, params: dict, key: str) -> list[dict]:
        headers = self._headers()
        out: list[dict] = []
        params = dict(params)
        while True:
            r = self._session.get(f"{self.base}{path}", params=params,
                                  headers=headers, timeout=_TIMEOUT)
            if r.status_code >= 400:
                raise RuntimeError(f"J-Quants API {r.status_code} {path}: {r.text[:300]}")
            body = r.json()
            out.extend(body.get(key, []))
            nxt = body.get("pagination_key")
            if not nxt:
                break
            params["pagination_key"] = nxt
        return out

    @staticmethod
    def _first(row: dict, *names: str):
        for n in names:
            v = row.get(n)
            if v is not None and v != "":
                return v
        return None

    def _build_matrix(self, need_days: int) -> None:
        if self._matrix is not None and self._built_days >= need_days:
            return
        import datetime as dt
        matrix: dict[str, list[tuple[str, float]]] = {}
        got = 0
        d = dt.date.today()
        span = 0
        while got < need_days and span < need_days * 2 + 15:
            span += 1
            if d.weekday() >= 5:
                d -= dt.timedelta(days=1)
                continue
            ymd = d.isoformat()
            d -= dt.timedelta(days=1)
            rows = self._get_paginated("/equities/bars/daily", {"date": ymd}, key="data")
            time.sleep(0.25)  # レート制限対策
            if not rows:
                continue
            any_close = False
            for row in rows:
                code = str(self._first(row, "Code", "code", "LocalCode") or "").strip()
                ysym = _jq_code_to_yahoo(code)
                if not ysym:
                    continue
                c = self._first(row, "AdjC", "C", "Close", "AdjustmentClose")
                if c is None:
                    continue
                any_close = True
                matrix.setdefault(ysym, []).append((ymd, float(c)))
            if any_close:
                got += 1
        # 日付昇順に整える
        for ysym in matrix:
            matrix[ysym].sort(key=lambda t: t[0])
        if not matrix:
            raise RuntimeError("J-Quants から終値を取得できませんでした（認証・プランを確認）。")
        self._matrix = matrix
        self._built_days = got

    def get_close_history(self, symbol: str, period: str) -> tuple[list[str], list[float]]:
        need = _PERIOD_DAYS.get(period, 500)
        self._build_matrix(need)
        assert self._matrix is not None
        series = self._matrix.get(symbol.upper())
        if not series:
            raise RuntimeError(f"J-Quants に {symbol} のデータがありません。")
        dates = [d for d, _c in series]
        closes = [c for _d, c in series]
        return dates, closes

    def all_symbols(self) -> list[str]:
        assert self._matrix is not None
        return sorted(self._matrix.keys())


def list_jp_universe(period: str = "2y") -> list[str]:
    """日本株の全銘柄（Yahoo記法）を返す。総当たりスキャンの後続ユニバース用。"""
    p = JQuantsProvider()
    p._build_matrix(_PERIOD_DAYS.get(period, 500))
    return p.all_symbols()
