# -*- coding: utf-8 -*-
"""
ニュース見出しの取得（Google News RSS）。キー不要。本文は取らず、見出しとリンクだけ。

  https://news.google.com/rss/search?q=<会社名> after:YYYY-MM-DD before:YYYY-MM-DD
      &hl=ja&gl=JP&ceid=JP:ja

after/before はその日を含まない境界なので、呼び出し側で1日ずつ広げて渡す。
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import pandas as pd
import requests

RSS_URL = "https://news.google.com/rss/search"
_TIMEOUT = 30
COLUMNS = ["date", "title", "url", "publisher"]


def parse_rss(xml_text: str | bytes) -> pd.DataFrame:
    root = ET.fromstring(xml_text)
    rows = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        src = item.find("source")
        publisher = (src.text or "").strip() if src is not None else ""
        try:
            ts = pd.Timestamp(parsedate_to_datetime(pub)).tz_convert("Asia/Tokyo").tz_localize(None)
        except Exception:  # noqa: BLE001
            ts = pd.NaT
        rows.append({"date": ts, "title": title, "url": link, "publisher": publisher})
    return pd.DataFrame(rows, columns=COLUMNS)


def fetch_news(query: str, start: pd.Timestamp, end: pd.Timestamp,
               session: requests.Session | None = None, sleep: float = 0.5) -> pd.DataFrame:
    """query を start〜end（両端を含む）で検索して見出しを返す。失敗時は空。"""
    s = session or requests.Session()
    q = f"{query} after:{(start - pd.Timedelta(days=1)).strftime('%Y-%m-%d')} before:{(end + pd.Timedelta(days=1)).strftime('%Y-%m-%d')}"
    try:
        r = s.get(RSS_URL, params={"q": q, "hl": "ja", "gl": "JP", "ceid": "JP:ja"}, timeout=_TIMEOUT)
        if r.status_code >= 400:
            print(f"[news] Google News RSS {r.status_code}（スキップ）")
            return pd.DataFrame(columns=COLUMNS)
        df = parse_rss(r.content)
    except Exception as e:  # noqa: BLE001
        print(f"[news] 取得に失敗（スキップ）: {str(e)[:120]}")
        return pd.DataFrame(columns=COLUMNS)
    finally:
        time.sleep(sleep)
    if df.empty:
        return df
    df = df[df["date"].isna() | ((df["date"] >= start.normalize()) & (df["date"] < end.normalize() + pd.Timedelta(days=1)))]
    return df.sort_values("date").reset_index(drop=True)
