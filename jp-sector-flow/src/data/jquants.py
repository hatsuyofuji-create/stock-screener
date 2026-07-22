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

    # ------------------------------------------------------------ 売買代金履歴
    def get_turnover_history(self) -> pd.DataFrame:
        """
        直近 lookback_days 営業日の売買代金テーブル（日付 × 銘柄コード, 円）を返す（V2）。
        /equities/bars/daily の TurnoverValue（売買代金）を採用する。
        日付ごとに ?date=YYYY-MM-DD を叩くので、呼び出し回数 = 概ね営業日数。
        """
        self.get_sector_map()  # 先にセクター表を用意

        cal = pd.bdate_range(
            end=pd.Timestamp.today().normalize(),
            periods=int(self.lookback_days * 1.6) + 5,
        )
        series_by_date: dict[pd.Timestamp, pd.Series] = {}
        got = 0
        for day in reversed(cal):  # 新しい日から遡って必要日数だけ集める
            ymd = day.strftime("%Y-%m-%d")
            rows = self._get_paginated(
                "/equities/bars/daily", {"date": ymd}, key="data"
            )
            time.sleep(0.25)  # レート制限対策
            if not rows:
                continue  # 休場日など
            values: dict[str, float] = {}
            for row in rows:
                code = str(self._first(row, "Code", "code", "LocalCode") or "").strip()
                t = self._first(
                    row, "TurnoverValue", "turnoverValue", "Turnover",
                    "TrdVal", "TVal", "Val", "TradingValue",
                )
                if code and t is not None:
                    values[code] = float(t)
            if values:
                series_by_date[day] = pd.Series(values)
                got += 1
            else:
                # データはあるのに売買代金が取れない = フィールド名違い。即座に実名を出す。
                raise RuntimeError(
                    "売買代金フィールドを特定できませんでした。bars の実フィールド例: "
                    f"{list(rows[0].keys())}"
                )
            if got >= self.lookback_days:
                break

        if not series_by_date:
            raise RuntimeError(
                "J-Quants から売買代金データを取得できませんでした。"
                "認証・プラン・営業日を確認してください。"
            )

        df = pd.DataFrame(series_by_date).T.sort_index()
        df.index.name = "Date"
        return df
