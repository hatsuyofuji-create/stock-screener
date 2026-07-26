# -*- coding: utf-8 -*-
"""
MockProvider: 鍵なしで pipeline を通すためのダミー提供元。

EdinetClient と同じ2つの入口を持つ:
  - list_securities_reports(days) -> list[docmeta]
  - fetch_segments(docmeta)       -> list[str]

同一 run 内に「1年前の有報」と「今回の有報」を両方入れてあるので、
検知ロジック（過去→今回の差分）まで含めて一巡を確認できる。
7203 は今回 “新規事業” が増える設定（＝新セグメント検知が1件出る）。
"""

from __future__ import annotations

from datetime import date

name = "mock"

# docID -> セグメント名一覧
_SEGMENTS = {
    "MOCK-7203-2024": ["自動車", "金融"],
    "MOCK-7203-2025": ["自動車", "金融", "新モビリティ"],   # ← 新セグメント
    "MOCK-6758-2024": ["ゲーム", "音楽", "映画"],
    "MOCK-6758-2025": ["ゲーム", "音楽", "映画"],             # 変化なし
}

_DOCS = [
    {
        "docID": "MOCK-7203-2024", "secCode": "72030", "ticker": "7203",
        "edinetCode": "E00001", "filerName": "モック自動車", "periodEnd": "2024-03-31",
        "submitDate": "2024-06-20", "docTypeCode": "120", "docDescription": "有価証券報告書",
    },
    {
        "docID": "MOCK-7203-2025", "secCode": "72030", "ticker": "7203",
        "edinetCode": "E00001", "filerName": "モック自動車", "periodEnd": "2025-03-31",
        "submitDate": "2025-06-20", "docTypeCode": "120", "docDescription": "有価証券報告書",
    },
    {
        "docID": "MOCK-6758-2024", "secCode": "67580", "ticker": "6758",
        "edinetCode": "E00002", "filerName": "モック電機", "periodEnd": "2024-03-31",
        "submitDate": "2024-06-21", "docTypeCode": "120", "docDescription": "有価証券報告書",
    },
    {
        "docID": "MOCK-6758-2025", "secCode": "67580", "ticker": "6758",
        "edinetCode": "E00002", "filerName": "モック電機", "periodEnd": "2025-03-31",
        "submitDate": "2025-06-21", "docTypeCode": "120", "docDescription": "有価証券報告書",
    },
]


class MockProvider:
    name = "mock"

    def list_securities_reports(self, days: list[date | str]) -> list[dict]:
        return [dict(d) for d in _DOCS]

    def fetch_segments(self, meta: dict) -> list[str]:
        return list(_SEGMENTS.get(meta.get("docID", ""), []))
