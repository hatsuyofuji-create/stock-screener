# -*- coding: utf-8 -*-
"""
JQuantsProvider: J-Quants API（V2）からデータを取得する提供元。

■ 認証について（V2・2026-07 時点）
  2025-12-22 以降に登録したアカウントは V2 のみ。V1 のトークン方式
  （/token/auth_user → /token/auth_refresh → Bearer）は廃止され、
  **APIキー方式**に変わった（V1 エンドポイントは 410 Gone を返す）。

  使い方はシンプル:
    - ダッシュボードで「APIキー」を発行する
    - すべてのリクエストに  x-api-key: <APIキー>  ヘッダを付けるだけ
    - ベースURLは https://api.jquants.com/v2

  参考: https://jpx-jquants.com/en/spec/migration-v1-v2
"""

from __future__ import annotations

import os
import time

import pandas as pd
import requests

from .provider import DataProvider

_TIMEOUT = 30


class JQuantsProvider(DataProvider):
    name = "jquants"

    def __init__(self) -> None:
        self.base = (os.getenv("JQUANTS_BASE") or "https://api.jquants.com/v2").rstrip("/")
        self.lookback_days = int(os.getenv("JQUANTS_LOOKBACK_DAYS", "250"))
        self._session = requests.Session()
        self._sector_map: dict[str, str] = {}
        self._turnover_df: pd.DataFrame | None = None
        self._close_df: pd.DataFrame | None = None

    # ------------------------------------------------------------------ 認証
    def _headers(self) -> dict[str, str]:
        """V2 の APIキー認証ヘッダ（x-api-key）を返す。"""
        key = os.getenv("JQUANTS_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "J-Quants の APIキーがありません。ダッシュボードで発行した "
                "APIキーを JQUANTS_API_KEY に設定してください（V2 は APIキー方式）。"
            )
        return {"x-api-key": key}

    # -------------------------------------------------------------- 取得補助
    def _get_paginated(self, path: str, params: dict, key: str) -> list[dict]:
        """pagination_key に対応した GET。key で指定した配列を全ページ連結して返す。"""
        headers = self._headers()
        out: list[dict] = []
        params = dict(params)
        while True:
            r = self._session.get(
                f"{self.base}{path}", params=params, headers=headers, timeout=_TIMEOUT
            )
            if r.status_code >= 400:
                # J-Quants が返すエラー本文をそのまま見せて原因を切り分けやすくする
                raise RuntimeError(
                    f"J-Quants API {r.status_code} {self.base}{path} : {r.text[:400]}"
                )
            body = r.json()
            out.extend(body.get(key, []))
            nxt = body.get("pagination_key")
            if not nxt:
                break
            params["pagination_key"] = nxt
        return out

    @staticmethod
    def _first(row: dict, *names: str):
        """候補のフィールド名から最初に見つかった非空の値を返す。"""
        for n in names:
            v = row.get(n)
            if v is not None and v != "":
                return v
        return None

    @staticmethod
    def _find_sector(row: dict):
        """33業種名を柔軟に探す（V2 は S33Nm。フィールド名の揺れに対応）。"""
        v = JQuantsProvider._first(
            row, "S33Nm", "Sector33CodeName", "Sector33Name", "sector33CodeName"
        )
        if v:
            return v
        return JQuantsProvider._first(
            row, "S17Nm", "Sector17CodeName", "Sector17Name"
        )

    # ------------------------------------------------------------ セクター表
    def get_sector_map(self) -> dict[str, str]:
        """/equities/master から 銘柄コード -> 33業種名（東証33業種）の対応を作る（V2）。"""
        if self._sector_map:
            return dict(self._sector_map)

        rows = self._get_paginated("/equities/master", {}, key="data")
        if not rows:
            raise RuntimeError("J-Quants /equities/master が空でした。")
        smap: dict[str, str] = {}
        for row in rows:
            code = str(self._first(row, "Code", "code", "LocalCode") or "").strip()
            sector = self._find_sector(row) or "その他"
            if code:
                smap[code] = sector
        # 業種名が取れず全部「その他」なら、実際のフィールド名をログに出して気づけるように
        if len(set(smap.values())) <= 1:
            raise RuntimeError(
                "33業種名フィールドを特定できませんでした。master の実フィールド例: "
                f"{list(rows[0].keys())}"
            )
        self._sector_map = smap
        return dict(smap)

    # ------------------------------------------------------ 売買代金＋終値履歴
    def _fetch_bars(self) -> None:
        """
        直近 lookback_days 営業日ぶんの日次バーを1回だけ取得し、
        売買代金（Va）と終値（AdjC/C）の2テーブルを同時に作る（API呼び出しは1系統）。
        /equities/bars/daily を日付ごとに叩く（呼び出し回数 = 概ね営業日数）。
        """
        if self._turnover_df is not None:
            return
        self.get_sector_map()  # 先にセクター表を用意

        cal = pd.bdate_range(
            end=pd.Timestamp.today().normalize(),
            periods=int(self.lookback_days * 1.6) + 5,
        )
        turn_by_date: dict[pd.Timestamp, pd.Series] = {}
        close_by_date: dict[pd.Timestamp, pd.Series] = {}
        got = 0
        for day in reversed(cal):  # 新しい日から遡って必要日数だけ集める
            ymd = day.strftime("%Y-%m-%d")
            rows = self._get_paginated(
                "/equities/bars/daily", {"date": ymd}, key="data"
            )
            time.sleep(0.25)  # レート制限対策
            if not rows:
                continue  # 休場日など
            tvals: dict[str, float] = {}
            cvals: dict[str, float] = {}
            for row in rows:
                code = str(self._first(row, "Code", "code", "LocalCode") or "").strip()
                if not code:
                    continue
                # V2 bars は超短縮名: Va=Value(売買代金), Vo=Volume, C=Close, AdjC=調整後終値
                t = self._first(row, "Va", "TurnoverValue", "turnoverValue", "Turnover", "Val")
                c = self._first(row, "AdjC", "C", "Close", "AdjustmentClose")
                if t is not None:
                    tvals[code] = float(t)
                if c is not None:
                    cvals[code] = float(c)
            if tvals:
                turn_by_date[day] = pd.Series(tvals)
                if cvals:
                    close_by_date[day] = pd.Series(cvals)
                got += 1
            else:
                # データはあるのに売買代金が取れない = フィールド名違い。即座に実名を出す。
                raise RuntimeError(
                    "売買代金フィールドを特定できませんでした。bars の実フィールド例: "
                    f"{list(rows[0].keys())}"
                )
            if got >= self.lookback_days:
                break

        if not turn_by_date:
            raise RuntimeError(
                "J-Quants から売買代金データを取得できませんでした。"
                "認証・プラン・営業日を確認してください。"
            )

        self._turnover_df = pd.DataFrame(turn_by_date).T.sort_index()
        self._turnover_df.index.name = "Date"
        self._close_df = pd.DataFrame(close_by_date).T.sort_index()
        self._close_df.index.name = "Date"

    def get_turnover_history(self) -> pd.DataFrame:
        self._fetch_bars()
        assert self._turnover_df is not None
        return self._turnover_df.copy()

    def get_close_history(self) -> pd.DataFrame:
        self._fetch_bars()
        assert self._close_df is not None
        return self._close_df.copy()
