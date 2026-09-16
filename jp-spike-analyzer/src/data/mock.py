# -*- coding: utf-8 -*-
"""
MockProvider と各モックソース: 鍵なしで画面と計算を確認するための擬似データ。

固定シードの乱数ウォーク株価に、意図的に「急騰日」を数回埋め込み、その日に
決算発表・適時開示・EDINET 提出・ニュース見出しのダミーを紐づける。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .provider import PriceProvider, normalize_code
from .tdnet import tag_title

# 急騰日（営業日インデックス、末尾から数える）と、その理由のダミー
_SPIKE_PLAN = [
    {"back": 400, "pct": 0.12, "kind": "決算"},
    {"back": 260, "pct": 0.09, "kind": "業績修正"},
    {"back": 150, "pct": 0.09, "kind": "自己株"},
    {"back": 60, "pct": 0.15, "kind": "TOB"},
    {"back": 12, "pct": 0.085, "kind": "地合い"},
]


def _dates(days: int) -> pd.DatetimeIndex:
    return pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)


class MockProvider(PriceProvider):
    name = "mock"

    def __init__(self, days: int = 5 * 250, seed: int = 7) -> None:
        self.days = days
        self.seed = seed
        self.dates = _dates(days)
        self._bars: dict[str, pd.DataFrame] = {}
        self._topix: pd.Series | None = None
        self._build_topix()

    def _build_topix(self) -> None:
        rng = np.random.default_rng(self.seed + 1)
        rets = rng.normal(0.0002, 0.009, size=self.days)
        # 「地合い」の急騰日は TOPIX も大きく上げる
        for plan in _SPIKE_PLAN:
            if plan["kind"] == "地合い":
                rets[self.days - plan["back"]] = 0.028
        self._topix = pd.Series(2000.0 * np.exp(np.cumsum(rets)), index=self.dates).round(2)

    def _build_bars(self, code: str) -> pd.DataFrame:
        rng = np.random.default_rng(self.seed + sum(ord(ch) for ch in code))  # 実行ごとに同じ
        rets = rng.normal(0.0003, 0.018, size=self.days)
        vol = rng.lognormal(mean=13.0, sigma=0.35, size=self.days)
        for plan in _SPIKE_PLAN:
            i = self.days - plan["back"]
            rets[i] = plan["pct"]
            vol[i] *= 4.5 if plan["kind"] != "地合い" else 1.4
        close = 1500.0 * np.exp(np.cumsum(rets))
        prev = np.concatenate([[close[0]], close[:-1]])
        gap = rng.normal(0.0, 0.004, size=self.days)
        open_ = prev * (1 + gap)
        for plan in _SPIKE_PLAN:
            i = self.days - plan["back"]
            open_[i] = prev[i] * (1 + plan["pct"] * 0.6)  # 寄り付きギャップ
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.005, self.days)))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.005, self.days)))
        df = pd.DataFrame({
            "open": open_, "high": high, "low": low, "close": close,
            "volume": vol.round(0), "turnover": (vol * close).round(0),
        }, index=self.dates).round(2)
        df.index.name = "date"
        return df

    def get_daily_bars(self, code: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        code = normalize_code(code)
        if code not in self._bars:
            self._bars[code] = self._build_bars(code)
        df = self._bars[code]
        return df[(df.index >= start) & (df.index <= end)].copy()

    def get_statements(self, code: str) -> pd.DataFrame:
        """四半期ごとの決算発表 + 急騰日「決算」の前日引け後に短信を置く。"""
        recs = []
        for plan in _SPIKE_PLAN:
            if plan["kind"] == "決算":
                d = self.dates[self.days - plan["back"] - 1]
                recs.append({"disclosed_date": d, "disclosed_time": "15:00:00",
                             "doc_type": "2QFinancialStatements_Consolidated_JP", "period": "2Q",
                             "net_sales": 1.2e11, "operating_profit": 1.8e10, "profit": 1.2e10,
                             "eps": 85.2, "forecast_operating_profit": 3.9e10, "forecast_profit": 2.6e10})
        # それ以外は 63営業日ごとに機械的に置く
        for i in range(self.days - 30, 0, -63):
            d = self.dates[i]
            recs.append({"disclosed_date": d, "disclosed_time": "15:30:00",
                         "doc_type": "FinancialStatements", "period": "",
                         "net_sales": 1.0e11, "operating_profit": 1.2e10, "profit": 0.8e10,
                         "eps": 60.0, "forecast_operating_profit": 3.5e10, "forecast_profit": 2.4e10})
        return pd.DataFrame(recs).sort_values("disclosed_date").reset_index(drop=True)

    def get_market_index(self, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
        assert self._topix is not None
        s = self._topix
        return s[(s.index >= start) & (s.index <= end)].copy()

    def get_company_name(self, code: str) -> str:
        return f"ダミー商事({normalize_code(code)})"


# ---------------------------------------------------------------- モック開示・ニュース

def mock_disclosures(code: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """適時開示のダミー。急騰日の前日引け後に、理由に応じた開示を置く。"""
    p = MockProvider()
    code = normalize_code(code)
    titles = {
        "決算": "2026年3月期 第2四半期決算短信〔日本基準〕（連結）",
        "業績修正": "業績予想の修正（上方修正）に関するお知らせ",
        "自己株": "自己株式の取得及び自己株式立会外買付取引（ToSTNeT-3）による自己株式の買付けに関するお知らせ",
        "TOB": "株式会社◯◯による当社株式に対する公開買付けの開始及び賛同の意見表明に関するお知らせ",
    }
    rows = []
    for plan in _SPIKE_PLAN:
        t = titles.get(plan["kind"])
        if not t:
            continue
        d = p.dates[p.days - plan["back"] - 1]
        rows.append({"date": d, "time": "15:30", "code": code, "name": p.get_company_name(code),
                     "title": t, "url": "https://www.release.tdnet.info/inbs/", "source": "mock",
                     "tag": tag_title(t)})
    df = pd.DataFrame(rows, columns=["date", "time", "code", "name", "title", "url", "source", "tag"])
    return df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)


def mock_edinet(code: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    p = MockProvider()
    code = normalize_code(code)
    rows = []
    for plan in _SPIKE_PLAN:
        if plan["kind"] == "TOB":
            d = p.dates[p.days - plan["back"] + 3]
            rows.append({"date": d, "code": code, "filer": "◯◯ホールディングス株式会社",
                         "doc_type_code": "350", "description": "大量保有報告書",
                         "url": "https://disclosure2.edinet-fsa.go.jp/", "doc_id": "S100MOCK"})
    df = pd.DataFrame(rows, columns=["date", "code", "filer", "doc_type_code", "description", "url", "doc_id"])
    return df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)


def mock_news(name: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    p = MockProvider()
    rows = []
    heads = {
        "決算": f"{name}、上期営業益が過去最高　通期予想を据え置き",
        "業績修正": f"{name}が通期予想を上方修正　株価は一時ストップ高",
        "自己株": f"{name}、自己株買いを発表　発行済みの3%",
        "TOB": f"{name}にTOB　プレミアム40%で全株取得へ",
        "地合い": "日経平均が急反発、半導体株が主導",
    }
    for plan in _SPIKE_PLAN:
        d = p.dates[p.days - plan["back"]]
        rows.append({"date": d, "title": heads[plan["kind"]], "url": "https://news.google.com/",
                     "publisher": "ダミー新聞"})
    df = pd.DataFrame(rows, columns=["date", "title", "url", "publisher"])
    return df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)
