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
            r.raise_for_status()
            body = r.json()
            out.extend(body.get(key, []))
            nxt = body.get("pagination_key")
            if not nxt:
                break
            params["pagination_key"] = nxt
        return out

    # ------------------------------------------------------------ セクター表
    def get_sector_map(self) -> dict[str, str]:
        """/listed/info から 銘柄コード -> 33業種名（東証33業種）の対応を作る。"""
        if self._sector_map:
            return dict(self._sector_map)

        rows = self._get_paginated("/listed/info", {}, key="info")
        smap: dict[str, str] = {}
        for row in rows:
            code = str(row.get("Code", "")).strip()
            sector = (
                row.get("Sector33CodeName")
                or row.get("Sector17CodeName")
                or "その他"
            )
            if code:
                smap[code] = sector
        self._sector_map = smap
        return dict(smap)

    # ------------------------------------------------------------ 売買代金履歴
    def get_turnover_history(self) -> pd.DataFrame:
        """
        直近 lookback_days 営業日の売買代金テーブル（日付 × 銘柄コード, 円）を返す。
        daily_quotes の TurnoverValue（売買代金）を採用する。
        日付ごとに /prices/daily_quotes?date=YYYY-MM-DD を叩くので、
        呼び出し回数 = 概ね営業日数。レート制限に配慮して少し待つ。
        """
        self.get_sector_map()  # 先にセクター表を用意（トークンも温まる）

        # 余裕を持って多めの暦日を候補にし、データが返った日だけ採用する
        cal = pd.bdate_range(
            end=pd.Timestamp.today().normalize(),
            periods=int(self.lookback_days * 1.6) + 5,
        )
        series_by_date: dict[pd.Timestamp, pd.Series] = {}
        got = 0
        for day in reversed(cal):  # 新しい日から遡って必要日数だけ集める
            ymd = day.strftime("%Y-%m-%d")
            rows = self._get_paginated(
                "/prices/daily_quotes", {"date": ymd}, key="daily_quotes"
            )
            time.sleep(0.25)  # レート制限対策
            if not rows:
                continue  # 休場日など
            values: dict[str, float] = {}
            for row in rows:
                code = str(row.get("Code", "")).strip()
                t = row.get("TurnoverValue")  # 売買代金（円）
                if code and t is not None:
                    values[code] = float(t)
            if values:
                series_by_date[day] = pd.Series(values)
                got += 1
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
