# -*- coding: utf-8 -*-
"""
=====================================================================
 J-Quants(V2) 決算発表予定日の取得
=====================================================================
 ★重要★ J-Quants(有料版でも)には『受注高』そのものは入っていません。
   受注高は短信PDF本文/補足情報にしか無いためです（このアプリは
   受注高をPDFから抽出します。→ src/extract/llm.py）。

 では J-Quants は何に使うか:
   - 「どの銘柄が、いつ、どの四半期を開示したか」を知り、
     取得すべき短信PDFを特定するのに使う（開示日の当たりをつける）。
   - 会社名・業種などの周辺情報。

 認証（2025-12-22 以降のアカウントは V2 = APIキー方式）:
   - ダッシュボードで発行した APIキーを環境変数 JQUANTS_API_KEY に設定
   - すべてのリクエストに  x-api-key: <APIキー>  ヘッダを付ける
   - ベース: https://api.jquants.com/v2  （JQUANTS_BASE で上書き可）
   参考: https://jpx-jquants.com/en/spec/migration-v1-v2
=====================================================================
"""

from __future__ import annotations
import os
import time
from typing import Optional

import requests

_BASE = os.environ.get("JQUANTS_BASE", "https://api.jquants.com/v2")


def _headers() -> dict:
    key = os.environ.get("JQUANTS_API_KEY")
    if not key:
        raise RuntimeError(
            "JQUANTS_API_KEY が未設定です。J-Quants のダッシュボードで"
            "APIキーを発行し、環境変数に設定してください。"
        )
    return {"x-api-key": key}


def _get(path: str, params: Optional[dict] = None, retries: int = 4) -> dict:
    """GET（ネットワーク失敗時のみ指数バックオフで再試行）。"""
    url = f"{_BASE}{path}"
    delay = 2.0
    last: Optional[Exception] = None
    for _ in range(retries):
        try:
            r = requests.get(url, headers=_headers(), params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            last = e
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"J-Quants 取得に失敗: {url} ({last})")


def announcements(code: Optional[str] = None) -> list[dict]:
    """
    決算発表予定日の一覧を返す（/fins/announcement）。
    code を指定するとその銘柄で絞り込む（API仕様に応じて簡易フィルタ）。

    返り値の各要素はおおむね: Date, Code, CompanyName, FiscalYear,
    FiscalQuarter, SectorName など（フィールド名は仕様に準拠）。
    """
    data = _get("/fins/announcement")
    rows = data.get("announcement", data.get("announcements", []))
    if code:
        code4 = str(code)
        rows = [r for r in rows if str(r.get("Code", "")).startswith(code4)]
    return rows
