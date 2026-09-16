# -*- coding: utf-8 -*-
"""
適時開示の過去分バックフィル（非公式 TDnet WebAPI・yanoshin.jp）。

公式 TDnet は直近1か月しか遡れないので、蓄積開始前の期間だけこの API で埋める。
  https://webapi.yanoshin.jp/webapi/tdnet/list/{銘柄コード}.json?limit=N
  https://webapi.yanoshin.jp/webapi/tdnet/list/{YYYYMMDD}-{YYYYMMDD}.json?limit=N

個人運営のサービスなので、止まっても日次運用（公式クロール）には影響しない構造にする。
レスポンス例:
  {"items": [{"Tdnet": {"pubdate": "2026-08-25 16:30:00", "company_code": "72030",
               "company_name": "...", "title": "...", "document_url": "https://...pdf"}}]}
"""

from __future__ import annotations

import os
import time

import pandas as pd
import requests

from .provider import normalize_code
from .tdnet import COLUMNS, tag_title

_TIMEOUT = 30


def _base() -> str:
    return (os.getenv("TDNET_BACKFILL_BASE") or "https://webapi.yanoshin.jp/webapi/tdnet/list").rstrip("/")


def parse_items(payload: dict) -> pd.DataFrame:
    """API の JSON を蓄積形式の DataFrame に変換する（純関数）。"""
    rows = []
    for it in payload.get("items", []):
        t = it.get("Tdnet", it)
        pub = str(t.get("pubdate") or "")
        if not pub:
            continue
        ts = pd.Timestamp(pub)
        rows.append({
            "date": ts.normalize(),
            "time": ts.strftime("%H:%M") if len(pub) > 10 else "",
            "code": normalize_code(t.get("company_code") or ""),
            "name": t.get("company_name") or "",
            "title": t.get("title") or "",
            "url": t.get("document_url") or t.get("url_xbrl") or "",
            "source": "backfill",
            "tag": tag_title(t.get("title") or ""),
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def fetch_by_code(code: str, start: pd.Timestamp, end: pd.Timestamp, limit: int = 2000,
                  session: requests.Session | None = None) -> pd.DataFrame:
    """銘柄コード指定で開示一覧を取り、期間で絞る。"""
    s = session or requests.Session()
    code = normalize_code(code)
    url = f"{_base()}/{code}.json"
    r = s.get(url, params={"limit": limit}, timeout=_TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"TDnet backfill API {r.status_code} {url} : {r.text[:200]}")
    df = parse_items(r.json())
    df = df[(df["date"] >= start.normalize()) & (df["date"] <= end.normalize())]
    return df.reset_index(drop=True)


def fetch_by_range(start: pd.Timestamp, end: pd.Timestamp, limit: int = 5000,
                   session: requests.Session | None = None, sleep: float = 1.0) -> pd.DataFrame:
    """日付範囲指定（全銘柄）。月ごとに分けて叩く。"""
    s = session or requests.Session()
    frames = []
    for m in pd.period_range(start.to_period("M"), end.to_period("M"), freq="M"):
        a = max(m.start_time.normalize(), start.normalize())
        b = min(m.end_time.normalize(), end.normalize())
        url = f"{_base()}/{a.strftime('%Y%m%d')}-{b.strftime('%Y%m%d')}.json"
        r = s.get(url, params={"limit": limit}, timeout=_TIMEOUT)
        if r.status_code >= 400:
            raise RuntimeError(f"TDnet backfill API {r.status_code} {url} : {r.text[:200]}")
        frames.append(parse_items(r.json()))
        time.sleep(sleep)
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    return pd.concat(frames, ignore_index=True)
