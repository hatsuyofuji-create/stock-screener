# -*- coding: utf-8 -*-
"""
EDINET API v2（金融庁）から、日付ごとの提出書類一覧を取り、銘柄で絞る。

  GET https://api.edinet-fsa.go.jp/api/v2/documents.json?date=YYYY-MM-DD&type=2
      &Subscription-Key=<EDINET_API_KEY>
  → {"results": [{"docID", "secCode"(5桁), "filerName", "docTypeCode",
                  "docDescription", "submitDateTime", "withdrawalStatus", ...}]}

書類の閲覧: https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?<docID>

急騰日と照合したい書類種別（docTypeCode）:
  120 有価証券報告書 / 140 四半期報告書 / 160 半期報告書 / 180 臨時報告書
  170 自己株券買付状況報告書 / 240 公開買付届出書 / 350 大量保有報告書 / 360 変更報告書
キーが無ければ照合をスキップする（本体は続行）。
日付ごとの結果は db/cache/edinet/ にキャッシュする（過去日は変わらない）。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

from .provider import normalize_code

EDINET_BASE = "https://api.edinet-fsa.go.jp/api/v2"
VIEW_URL = "https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?{doc_id}"
_TIMEOUT = 30
COLUMNS = ["date", "code", "filer", "doc_type_code", "description", "url", "doc_id"]

DOC_TYPES = {
    "120": "有価証券報告書", "130": "訂正有価証券報告書", "140": "四半期報告書", "160": "半期報告書",
    "170": "自己株券買付状況報告書", "180": "臨時報告書", "240": "公開買付届出書",
    "350": "大量保有報告書", "360": "変更報告書（大量保有）",
}
DEFAULT_TYPES = tuple(DOC_TYPES.keys())


def has_key() -> bool:
    return bool(os.getenv("EDINET_API_KEY", "").strip())


def parse_results(payload: dict, day: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for r in payload.get("results", []) or []:
        if str(r.get("withdrawalStatus") or "0") != "0":
            continue  # 取下げ済み
        sec = r.get("secCode")
        rows.append({
            "date": day.normalize(),
            "code": normalize_code(sec) if sec else "",
            "filer": r.get("filerName") or "",
            "doc_type_code": str(r.get("docTypeCode") or ""),
            "description": r.get("docDescription") or DOC_TYPES.get(str(r.get("docTypeCode") or ""), ""),
            "url": VIEW_URL.format(doc_id=r.get("docID")) if r.get("docID") else "",
            "doc_id": r.get("docID") or "",
        })
    return pd.DataFrame(rows, columns=COLUMNS)


class EdinetClient:
    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or (Path(__file__).resolve().parents[2] / "db" / "cache" / "edinet")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._session = requests.Session()

    def _fetch_day(self, day: pd.Timestamp) -> dict:
        p = self.cache_dir / f"{day.strftime('%Y-%m-%d')}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        key = os.getenv("EDINET_API_KEY", "").strip()
        r = self._session.get(
            f"{EDINET_BASE}/documents.json",
            params={"date": day.strftime("%Y-%m-%d"), "type": 2, "Subscription-Key": key},
            timeout=_TIMEOUT,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"EDINET API {r.status_code} : {r.text[:200]}")
        body = r.json()
        # 当日分はまだ増えるのでキャッシュしない
        if day.normalize() < pd.Timestamp.today().normalize():
            p.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.3)
        return body

    def documents(self, code: str, days: list[pd.Timestamp], doc_types: tuple[str, ...] = DEFAULT_TYPES) -> pd.DataFrame:
        """指定日リストの提出書類のうち、銘柄コードが一致し、種別が doc_types のものを返す。
        大量保有報告書は提出者（filer）が別会社なので secCode（対象会社）で一致させる。"""
        if not has_key():
            return pd.DataFrame(columns=COLUMNS)
        code = normalize_code(code)
        frames = []
        for d in sorted(set(pd.Timestamp(x).normalize() for x in days)):
            try:
                df = parse_results(self._fetch_day(d), d)
            except Exception as e:  # noqa: BLE001
                print(f"[edinet] {d.date()} の取得に失敗（スキップ）: {str(e)[:120]}")
                continue
            df = df[(df["code"] == code) & (df["doc_type_code"].isin(doc_types))]
            frames.append(df)
        if not frames:
            return pd.DataFrame(columns=COLUMNS)
        return pd.concat(frames, ignore_index=True).sort_values("date").reset_index(drop=True)
