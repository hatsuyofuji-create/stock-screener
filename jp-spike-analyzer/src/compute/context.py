# -*- coding: utf-8 -*-
"""
急騰日ごとに「その時何が起きていたか」を集める（要因タグ付け）。

各急騰日について:
  - market:      同日の TOPIX 騰落（%）と、個別の超過分
  - statements:  前日〜当日に開示された決算（J-Quants）
  - disclosures: 前日〜翌日の適時開示（TDnet 蓄積 + バックフィル）
  - edinet:      前日〜5営業日後の EDINET 提出書類
  - news:        前2営業日〜翌日のニュース見出し
  - tags:        上の情報から機械的に付けた要因タグ（決算 / 業績修正 / 自己株 / TOB / 地合い / 出来高急増 / 材料不明 …）
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.data.tdnet import tag_title  # noqa: E402
from config import (  # noqa: E402
    EDINET_WINDOW, MARKET_MOVE_PCT, NEWS_WINDOW, STATEMENT_WINDOW, TDNET_WINDOW,
)

_EDINET_TAG = {
    "180": "臨時報告書", "240": "TOB", "350": "大量保有", "360": "大量保有",
    "170": "自己株", "120": "有報", "140": "四半期報告書", "160": "半期報告書", "130": "有報訂正",
}


def business_offset(trading_days: pd.DatetimeIndex, day: pd.Timestamp, offset: int) -> pd.Timestamp:
    """営業日カレンダー（日足の日付）上で day から offset 営業日ずらした日付。
    範囲外は暦日で近似する。"""
    idx = trading_days.get_indexer([day])[0]
    if idx < 0:
        return day + pd.tseries.offsets.BDay(offset)
    j = idx + offset
    if 0 <= j < len(trading_days):
        return trading_days[j]
    return day + pd.tseries.offsets.BDay(offset)


def window(trading_days: pd.DatetimeIndex, day: pd.Timestamp, w: tuple[int, int]) -> tuple[pd.Timestamp, pd.Timestamp]:
    return business_offset(trading_days, day, w[0]), business_offset(trading_days, day, w[1])


def _rel_label(trading_days: pd.DatetimeIndex, day: pd.Timestamp, other: pd.Timestamp) -> str:
    """急騰日を基準にした相対日ラベル（前日 / 当日 / +3日 など）。"""
    a = trading_days.get_indexer([day])[0]
    b = trading_days.get_indexer([pd.Timestamp(other).normalize()])[0]
    if a < 0 or b < 0:
        n = (pd.Timestamp(other).normalize() - day).days
    else:
        n = b - a
    if n == 0:
        return "当日"
    if n == -1:
        return "前日"
    if n == 1:
        return "翌日"
    return f"{n:+d}日"


def _market_tag(pct: float, topix_pct: float | None) -> tuple[str | None, float | None]:
    if topix_pct is None or pd.isna(topix_pct):
        return None, None
    rel = pct - topix_pct
    if topix_pct >= MARKET_MOVE_PCT:
        return f"地合い(TOPIX{topix_pct:+.1f}%)", rel
    return None, rel


def enrich(
    spikes: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    topix: pd.Series | None = None,
    statements: pd.DataFrame | None = None,
    disclosures: pd.DataFrame | None = None,
    edinet: pd.DataFrame | None = None,
    news_fetcher=None,
) -> list[dict]:
    """急騰日ごとの文脈をまとめた dict のリストを返す（JSON にそのまま書ける形）。

    news_fetcher(start, end) -> DataFrame(date, title, url, publisher) を渡すと、
    急騰日ごとにニュースを取りに行く（None ならスキップ）。
    """
    days = pd.DatetimeIndex(bars.index).normalize()
    topix_pct = (topix.sort_index().pct_change() * 100.0) if topix is not None and len(topix) else None
    out: list[dict] = []
    for _, s in spikes.iterrows():
        d = pd.Timestamp(s["date"]).normalize()
        rec: dict = {
            "date": d.strftime("%Y-%m-%d"),
            "close": float(s["close"]),
            "pct": round(float(s["pct"]), 2),
            "gap_pct": None if pd.isna(s.get("gap_pct")) else round(float(s["gap_pct"]), 2),
            "high_pct": None if pd.isna(s.get("high_pct")) else round(float(s["high_pct"]), 2),
            "vol_ratio": None if pd.isna(s.get("vol_ratio")) else round(float(s["vol_ratio"]), 2),
            "fwd_5": None if pd.isna(s.get("fwd_5")) else round(float(s["fwd_5"]), 2),
            "fwd_20": None if pd.isna(s.get("fwd_20")) else round(float(s["fwd_20"]), 2),
            "rule": s.get("reason", ""),
        }
        tags: list[str] = []

        # 地合い
        tp = float(topix_pct.get(d)) if topix_pct is not None and d in topix_pct.index else None
        mtag, rel = _market_tag(rec["pct"], tp)
        rec["topix_pct"] = None if tp is None else round(tp, 2)
        rec["relative_pct"] = None if rel is None else round(rel, 2)
        if mtag:
            tags.append(mtag)

        # 決算（J-Quants）
        rec["statements"] = []
        if statements is not None and not statements.empty:
            a, b = window(days, d, STATEMENT_WINDOW)
            sub = statements[(statements["disclosed_date"] >= a) & (statements["disclosed_date"] <= b)]
            for _, r in sub.iterrows():
                rec["statements"].append({
                    "date": pd.Timestamp(r["disclosed_date"]).strftime("%Y-%m-%d"),
                    "rel": _rel_label(days, d, r["disclosed_date"]),
                    "time": str(r.get("disclosed_time") or ""),
                    "doc_type": str(r.get("doc_type") or ""),
                    "period": str(r.get("period") or ""),
                    "operating_profit": None if pd.isna(r.get("operating_profit")) else float(r["operating_profit"]),
                    "forecast_operating_profit": None if pd.isna(r.get("forecast_operating_profit")) else float(r["forecast_operating_profit"]),
                })
            if rec["statements"]:
                tags.append("決算")

        # 適時開示
        rec["disclosures"] = []
        if disclosures is not None and not disclosures.empty:
            a, b = window(days, d, TDNET_WINDOW)
            sub = disclosures[(disclosures["date"] >= a) & (disclosures["date"] <= b)]
            for _, r in sub.iterrows():
                rec["disclosures"].append({
                    "date": pd.Timestamp(r["date"]).strftime("%Y-%m-%d"),
                    "rel": _rel_label(days, d, r["date"]),
                    "time": str(r.get("time") or ""),
                    "tag": str(r.get("tag") or tag_title(r["title"])),
                    "title": str(r["title"]),
                    "url": str(r.get("url") or ""),
                    "source": str(r.get("source") or ""),
                })
            for t in dict.fromkeys(x["tag"] for x in rec["disclosures"]):
                if t and t not in ("その他", "ガバナンス", "株主総会", "役員") and t not in tags:
                    if not (t == "決算短信" and "決算" in tags):
                        tags.append(t)

        # EDINET
        rec["edinet"] = []
        if edinet is not None and not edinet.empty:
            a, b = window(days, d, EDINET_WINDOW)
            sub = edinet[(edinet["date"] >= a) & (edinet["date"] <= b)]
            for _, r in sub.iterrows():
                rec["edinet"].append({
                    "date": pd.Timestamp(r["date"]).strftime("%Y-%m-%d"),
                    "rel": _rel_label(days, d, r["date"]),
                    "doc_type_code": str(r.get("doc_type_code") or ""),
                    "description": str(r.get("description") or ""),
                    "filer": str(r.get("filer") or ""),
                    "url": str(r.get("url") or ""),
                })
            for t in dict.fromkeys(_EDINET_TAG.get(x["doc_type_code"]) for x in rec["edinet"]):
                if t and t not in tags and t not in ("有報", "四半期報告書", "半期報告書", "有報訂正"):
                    tags.append(t)

        # ニュース
        rec["news"] = []
        if news_fetcher is not None:
            a, b = window(days, d, NEWS_WINDOW)
            try:
                nd = news_fetcher(a, b)
            except Exception as e:  # noqa: BLE001
                print(f"[news] {d.date()} 取得失敗: {str(e)[:100]}")
                nd = None
            if nd is not None and not nd.empty:
                for _, r in nd.iterrows():
                    rec["news"].append({
                        "date": "" if pd.isna(r.get("date")) else pd.Timestamp(r["date"]).strftime("%Y-%m-%d"),
                        "title": str(r["title"]),
                        "url": str(r.get("url") or ""),
                        "publisher": str(r.get("publisher") or ""),
                    })

        # 出来高・材料不明
        if rec["vol_ratio"] is not None and rec["vol_ratio"] >= 3.0:
            tags.append("出来高急増")
        if not any(t for t in tags if not t.startswith("地合い") and t != "出来高急増"):
            if not rec["news"]:
                tags.append("材料不明")
            else:
                tags.append("ニュースのみ")
        rec["tags"] = tags
        out.append(rec)
    return out
