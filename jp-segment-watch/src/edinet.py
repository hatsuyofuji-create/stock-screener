# -*- coding: utf-8 -*-
"""
EDINET API v2 クライアント。

■ なぜ J-Quants ではなく EDINET なのか
  やりたいのは「決算開示の“事業セグメント”を時系列で見て、過去1年に
  なかったセグメントが増えた銘柄を検知する」こと。
  J-Quants の財務API（/fins/statements, /fins/fs_details）は決算短信の
  サマリー財務値や BS/PL/CF の標準科目までで、**事業セグメントの内訳
  （報告セグメント軸の内訳・セグメント名）は返さない**。
  一方 EDINET は有価証券報告書の XBRL を配布しており、セグメント情報が
  「セグメント軸（〜SegmentsAxis）＋会社独自メンバー」として正規に入って
  いる。そこでセグメントの本体は EDINET から取得する。

■ 認証（V2・APIキー方式）
  EDINET API v2 は購読キー（Subscription-Key）が必須。金融庁の EDINET
  「アカウント管理」で無料発行し、環境変数 EDINET_API_KEY に設定する。
  すべてのリクエストに ?Subscription-Key=<KEY> を付ける。

  参考: EDINET API 仕様書（Version 2, 金融庁 企業開示課）
        https://api.edinet-fsa.go.jp/api/v2

■ 使うエンドポイント
  - GET /documents.json?date=YYYY-MM-DD&type=2
        指定日に提出された書類の一覧（メタデータ）。results[] を返す。
  - GET /documents/{docID}?type=1
        当該書類の XBRL 一式（ZIP バイナリ）。type=5 は CSV、type=2 は PDF。

  有価証券報告書は docTypeCode == "120"（訂正版は "130"）。
"""

from __future__ import annotations

import os
import time
from datetime import date, timedelta

import requests

_BASE = "https://api.edinet-fsa.go.jp/api/v2"
_TIMEOUT = 60
# 有価証券報告書。訂正版(130)は既定では追わない（ノイズ源になりやすい）。
DOC_TYPE_YUHO = "120"


class EdinetError(RuntimeError):
    """EDINET API 由来のエラー。"""


class EdinetClient:
    """EDINET API v2 の薄いラッパ（一覧取得と ZIP ダウンロードだけ）。"""

    name = "edinet"

    def __init__(self, api_key: str | None = None, *, sleep: float = 0.4) -> None:
        self.base = (os.getenv("EDINET_BASE") or _BASE).rstrip("/")
        self.api_key = (api_key if api_key is not None else os.getenv("EDINET_API_KEY", "")).strip()
        if not self.api_key:
            raise EdinetError(
                "EDINET の APIキーがありません。金融庁 EDINET の『アカウント管理』で "
                "購読キーを発行し、EDINET_API_KEY に設定してください。"
            )
        self._sleep = sleep
        self._session = requests.Session()

    # ------------------------------------------------------------- 内部ヘルパ
    def _params(self, extra: dict) -> dict:
        p = dict(extra)
        p["Subscription-Key"] = self.api_key
        return p

    def _get(self, path: str, params: dict, *, want_json: bool):
        url = f"{self.base}{path}"
        r = self._session.get(url, params=self._params(params), timeout=_TIMEOUT)
        time.sleep(self._sleep)  # レート制限に配慮して毎回少し待つ
        if r.status_code >= 400:
            raise EdinetError(f"EDINET {r.status_code} {path} : {r.text[:300]}")
        return r.json() if want_json else r.content

    # ---------------------------------------------------------------- 一覧取得
    def list_documents(self, on: date | str) -> list[dict]:
        """指定日に提出された書類メタデータ（results[]）を返す。"""
        ymd = on if isinstance(on, str) else on.strftime("%Y-%m-%d")
        body = self._get("/documents.json", {"date": ymd, "type": "2"}, want_json=True)
        # metadata.status が "404" 等でも results は無い/空になるだけなので握って返す
        return body.get("results") or []

    def list_securities_reports(self, days: list[date | str]) -> list[dict]:
        """
        複数日ぶんの一覧から、有価証券報告書（XBRLあり・取消なし・証券コードあり）
        だけを抽出して返す。docmeta（正規化済みdict）のリスト。
        """
        out: list[dict] = []
        seen: set[str] = set()
        for d in days:
            for row in self.list_documents(d):
                meta = _normalize(row)
                if meta is None:
                    continue
                if meta["docID"] in seen:
                    continue
                seen.add(meta["docID"])
                out.append(meta)
        return out

    # -------------------------------------------------------------- ダウンロード
    def download_xbrl_zip(self, doc_id: str) -> bytes:
        """当該書類の XBRL 一式 ZIP（type=1）をバイト列で返す。"""
        content = self._get(f"/documents/{doc_id}", {"type": "1"}, want_json=False)
        # ZIP マジックバイト（PK\x03\x04）でなければ、エラーJSON等が返っている
        if content[:2] != b"PK":
            raise EdinetError(
                f"docID={doc_id} の ZIP を取得できませんでした（先頭={content[:16]!r}）。"
            )
        return content


def _normalize(row: dict) -> dict | None:
    """documents.json の1行を、監視で使うキーだけの dict に整える。対象外なら None。"""
    if str(row.get("docTypeCode") or "") != DOC_TYPE_YUHO:
        return None
    if str(row.get("xbrlFlag") or "0") != "1":
        return None  # XBRL が無い書類はセグメントを取れない
    if str(row.get("withdrawalStatus") or "0") != "0":
        return None  # 取下げ・取消は対象外
    sec = str(row.get("secCode") or "").strip()
    if not sec:
        return None  # ファンド等、証券コードが無いものは対象外
    return {
        "docID": str(row.get("docID") or "").strip(),
        "secCode": sec,
        "ticker": _ticker(sec),
        "edinetCode": str(row.get("edinetCode") or "").strip(),
        "filerName": str(row.get("filerName") or "").strip(),
        "periodEnd": str(row.get("periodEnd") or "").strip(),
        "submitDate": str(row.get("submitDateTime") or "").strip()[:10],
        "docTypeCode": DOC_TYPE_YUHO,
        "docDescription": str(row.get("docDescription") or "").strip(),
    }


def _ticker(sec_code: str) -> str:
    """EDINET の証券コード（5桁, 末尾0）を4桁ティッカーに直す。それ以外はそのまま。"""
    if len(sec_code) == 5 and sec_code.endswith("0"):
        return sec_code[:4]
    return sec_code


def recent_days(window: int, *, end: date | None = None) -> list[date]:
    """end（既定=今日）から遡って window 日ぶんの日付リスト（新しい順）。"""
    end = end or date.today()
    return [end - timedelta(days=i) for i in range(max(1, window))]
