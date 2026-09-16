# -*- coding: utf-8 -*-
"""
JQuantsProvider: J-Quants API（V2・APIキー方式）から銘柄単位でデータを取得する。

  - 認証: すべてのリクエストに x-api-key: <APIキー> ヘッダ（JQUANTS_API_KEY）
  - ベースURL: https://api.jquants.com/v2（JQUANTS_BASE で上書き可）
  - 参考: https://jpx-jquants.com/en/spec/migration-v1-v2

Light プランの前提:
  - 日足は過去5年ぶん。決算情報（/fins/statements）は使える。
  - 33業種指数は Standard 以上なので、市場全体の動きは TOPIX だけを見る。

フィールド名は V2 の短縮名（C, AdjC, Vo, Va …）を第一候補にしつつ、V1 風の名前にも
フォールバックする（jp-sector-flow/src/data/jquants.py と同じ考え方）。
取得結果は db/cache/ に1日キャッシュして、Streamlit の再実行で API を叩き直さない。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

from .provider import PriceProvider, normalize_code

_TIMEOUT = 30
_CACHE_TTL_SEC = 24 * 3600


def _first(row: dict, *names: str):
    for n in names:
        v = row.get(n)
        if v is not None and v != "":
            return v
    return None


class JQuantsProvider(PriceProvider):
    name = "jquants"

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.base = (os.getenv("JQUANTS_BASE") or "https://api.jquants.com/v2").rstrip("/")
        self.cache_dir = cache_dir or (Path(__file__).resolve().parents[2] / "db" / "cache" / "jquants")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._session = requests.Session()

    # ------------------------------------------------------------------ 認証
    def _headers(self) -> dict[str, str]:
        key = os.getenv("JQUANTS_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "J-Quants の APIキーがありません。ダッシュボードで発行した "
                "APIキーを JQUANTS_API_KEY に設定してください（V2 は APIキー方式）。"
            )
        return {"x-api-key": key}

    # -------------------------------------------------------------- 取得補助
    def _get_paginated(self, path: str, params: dict, keys: tuple[str, ...] = ("data",)) -> list[dict]:
        """pagination_key 対応の GET。keys のいずれかの配列を全ページ連結して返す。"""
        headers = self._headers()
        out: list[dict] = []
        params = dict(params)
        while True:
            r = self._session.get(f"{self.base}{path}", params=params, headers=headers, timeout=_TIMEOUT)
            if r.status_code >= 400:
                raise RuntimeError(f"J-Quants API {r.status_code} {self.base}{path} : {r.text[:400]}")
            body = r.json()
            for k in keys:
                if isinstance(body.get(k), list):
                    out.extend(body[k])
                    break
            nxt = body.get("pagination_key")
            if not nxt:
                break
            params["pagination_key"] = nxt
            time.sleep(0.2)
        return out

    def _cached(self, key: str, fetch):
        """key に対応する JSON キャッシュが新しければそれを、無ければ fetch() して保存。"""
        p = self.cache_dir / f"{key}.json"
        if p.exists() and (time.time() - p.stat().st_mtime) < _CACHE_TTL_SEC:
            return json.loads(p.read_text(encoding="utf-8"))
        rows = fetch()
        p.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return rows

    # ---------------------------------------------------------------- 日足
    def get_daily_bars(self, code: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        code = normalize_code(code)
        params = {"code": code, "from": start.strftime("%Y-%m-%d"), "to": end.strftime("%Y-%m-%d")}
        rows = self._cached(
            f"bars_{code}_{params['from']}_{params['to']}",
            lambda: self._get_paginated("/equities/bars/daily", params, keys=("data", "daily_quotes")),
        )
        if not rows:
            raise RuntimeError(
                f"J-Quants から {code} の日足が取れませんでした。銘柄コード・プラン・期間を確認してください。"
            )
        recs = []
        for row in rows:
            d = _first(row, "Date", "D", "date")
            if d is None:
                continue
            recs.append({
                "date": pd.Timestamp(d),
                "open": _first(row, "AdjO", "O", "AdjustmentOpen", "Open"),
                "high": _first(row, "AdjH", "H", "AdjustmentHigh", "High"),
                "low": _first(row, "AdjL", "L", "AdjustmentLow", "Low"),
                "close": _first(row, "AdjC", "C", "AdjustmentClose", "Close"),
                "volume": _first(row, "AdjVo", "Vo", "AdjustmentVolume", "Volume"),
                "turnover": _first(row, "Va", "TurnoverValue"),
            })
        if not recs:
            raise RuntimeError(f"日足の日付フィールドを特定できませんでした。実フィールド例: {list(rows[0].keys())}")
        df = pd.DataFrame(recs).set_index("date").sort_index()
        df = df.apply(pd.to_numeric, errors="coerce")
        if df["close"].isna().all():
            raise RuntimeError(f"終値フィールドを特定できませんでした。実フィールド例: {list(rows[0].keys())}")
        return df

    # ---------------------------------------------------------------- 決算
    def get_statements(self, code: str) -> pd.DataFrame:
        code = normalize_code(code)
        rows = self._cached(
            f"statements_{code}",
            lambda: self._get_paginated("/fins/statements", {"code": code}, keys=("data", "statements")),
        )
        recs = []
        for row in rows:
            d = _first(row, "DisclosedDate", "DiscDate", "Date", "D")
            if d is None:
                continue
            recs.append({
                "disclosed_date": pd.Timestamp(d),
                "disclosed_time": _first(row, "DisclosedTime", "DiscTime", "Time") or "",
                "doc_type": _first(row, "TypeOfDocument", "DocType", "TypeOfDoc") or "",
                "period": _first(row, "TypeOfCurrentPeriod", "CurPeriodType", "PeriodType") or "",
                "net_sales": _first(row, "NetSales", "Sales", "NS"),
                "operating_profit": _first(row, "OperatingProfit", "OP", "OpProfit"),
                "profit": _first(row, "Profit", "NP", "NetProfit"),
                "eps": _first(row, "EarningsPerShare", "EPS"),
                "forecast_operating_profit": _first(row, "ForecastOperatingProfit", "FcstOP", "FOP"),
                "forecast_profit": _first(row, "ForecastProfit", "FcstNP", "FNP"),
            })
        cols = ["disclosed_date", "disclosed_time", "doc_type", "period", "net_sales",
                "operating_profit", "profit", "eps", "forecast_operating_profit", "forecast_profit"]
        if not recs:
            return pd.DataFrame(columns=cols)
        df = pd.DataFrame(recs)[cols]
        for c in cols[4:]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.sort_values(["disclosed_date", "disclosed_time"]).reset_index(drop=True)

    # --------------------------------------------------------------- TOPIX
    def get_market_index(self, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
        """TOPIX 終値。V2 の /indices/bars/daily（code=0000）→ 旧 /indices/topix の順に試す。
        取れなくても本体は続行する（空 Series を返す）。"""
        frm, to = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

        def fetch():
            errors = []
            for path, params in (
                ("/indices/bars/daily", {"code": "0000", "from": frm, "to": to}),
                ("/indices/topix", {"from": frm, "to": to}),
            ):
                try:
                    rows = self._get_paginated(path, params, keys=("data", "topix", "indices"))
                    if rows:
                        return rows
                except Exception as e:  # noqa: BLE001
                    errors.append(str(e)[:120])
            print(f"[jquants] TOPIX を取得できませんでした（地合い判定なしで続行）: {errors}")
            return []

        rows = self._cached(f"topix_{frm}_{to}", fetch)
        vals = {}
        for row in rows:
            d = _first(row, "Date", "D", "date")
            c = _first(row, "C", "Close", "AdjC")
            if d is not None and c is not None:
                vals[pd.Timestamp(d)] = float(c)
        return pd.Series(vals, dtype="float64").sort_index()

    # ------------------------------------------------------------- 銘柄名
    def get_company_name(self, code: str) -> str:
        code = normalize_code(code)
        try:
            rows = self._cached(
                f"master_{code}",
                lambda: self._get_paginated("/equities/master", {"code": code}, keys=("data", "info")),
            )
        except Exception as e:  # noqa: BLE001
            print(f"[jquants] 銘柄名を取得できませんでした: {str(e)[:120]}")
            return code
        for row in rows:
            n = _first(row, "CoName", "CompanyName", "Name", "CoNm")
            if n:
                return str(n)
        return code
