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
    {"back": 200, "pct": -0.11, "kind": "下方修正"},
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
        """四半期ごとの決算（数字入り）＋ 急騰日「決算」「業績修正」に対応する行。"""
        from .jquants import STATEMENT_COLUMNS

        recs = []
        # 3月決算の会社として、各四半期の累計営業利益を機械的に作る（毎年 +12% 成長）
        base_fy_op = 3.0e10
        for i in range(self.days - 40, 0, -63):
            d = self.dates[i]
            # 単純化: 5/8/11/2 月に FY/1Q/2Q/3Q が出るものとして月から決める
            m = d.month
            period = {5: "FY", 8: "1Q", 11: "2Q", 2: "3Q"}.get(m, ["1Q", "2Q", "3Q", "FY"][i % 4])
            fy_end_year = d.year if m <= 3 else d.year + (0 if period == "FY" else 1)
            if period == "FY":
                fy_end_year = d.year if m >= 4 else d.year - 1
            fy_end = pd.Timestamp(year=fy_end_year, month=3, day=31)
            growth = 1.12 ** (fy_end_year - 2024)
            fy_op = base_fy_op * growth
            frac = {"1Q": 0.25, "2Q": 0.5, "3Q": 0.75, "FY": 1.0}[period]
            recs.append({
                "disclosed_date": d, "disclosed_time": "15:30:00",
                "doc_type": f"{period}FinancialStatements_Consolidated_JP", "period": period, "fy_end": fy_end,
                "net_sales": 4.0e11 * growth * frac, "operating_profit": fy_op * frac, "ordinary_profit": fy_op * frac * 1.05,
                "profit": fy_op * frac * 0.7, "eps": 60.0 * growth * frac,
                "forecast_sales": 4.0e11 * growth, "forecast_operating_profit": fy_op, "forecast_profit": fy_op * 0.7,
                "next_fy_forecast_sales": 4.0e11 * growth * 1.1 if period == "FY" else None,
                "next_fy_forecast_operating_profit": fy_op * 1.15 if period == "FY" else None,
                "next_fy_forecast_profit": fy_op * 0.7 * 1.15 if period == "FY" else None,
            })
        # 急騰日「決算」: 前日引け後に 2Q 好決算（進捗 62%・予想を上方修正）
        for plan in _SPIKE_PLAN:
            d = self.dates[self.days - plan["back"] - 1]
            if plan["kind"] == "決算":
                fy_end = pd.Timestamp(year=d.year + (1 if d.month >= 4 else 0), month=3, day=31)
                recs.append({
                    "disclosed_date": d, "disclosed_time": "15:00:00",
                    "doc_type": "2QFinancialStatements_Consolidated_JP", "period": "2Q", "fy_end": fy_end,
                    "net_sales": 2.6e11, "operating_profit": 2.3e10, "ordinary_profit": 2.4e10, "profit": 1.6e10, "eps": 85.2,
                    "forecast_sales": 4.6e11, "forecast_operating_profit": 3.7e10, "forecast_profit": 2.6e10,
                    "next_fy_forecast_sales": None, "next_fy_forecast_operating_profit": None, "next_fy_forecast_profit": None,
                })
            if plan["kind"] == "下方修正":
                fy_end = pd.Timestamp(year=d.year + (1 if d.month >= 4 else 0), month=3, day=31)
                recs.append({
                    "disclosed_date": d, "disclosed_time": "15:30:00",
                    "doc_type": "EarnForecastRevision", "period": "", "fy_end": fy_end,
                    "net_sales": None, "operating_profit": None, "ordinary_profit": None, "profit": None, "eps": None,
                    "forecast_sales": 3.6e11, "forecast_operating_profit": 2.4e10, "forecast_profit": 0.9e10,
                    "next_fy_forecast_sales": None, "next_fy_forecast_operating_profit": None, "next_fy_forecast_profit": None,
                })
            if plan["kind"] == "業績修正":
                fy_end = pd.Timestamp(year=d.year + (1 if d.month >= 4 else 0), month=3, day=31)
                recs.append({
                    "disclosed_date": d, "disclosed_time": "15:30:00",
                    "doc_type": "EarnForecastRevision", "period": "", "fy_end": fy_end,
                    "net_sales": None, "operating_profit": None, "ordinary_profit": None, "profit": None, "eps": None,
                    "forecast_sales": 4.9e11, "forecast_operating_profit": 4.4e10, "forecast_profit": 3.1e10,
                    "next_fy_forecast_sales": None, "next_fy_forecast_operating_profit": None, "next_fy_forecast_profit": None,
                })
        df = pd.DataFrame(recs, columns=STATEMENT_COLUMNS)
        return df.sort_values(["disclosed_date", "disclosed_time"]).reset_index(drop=True)

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
        "下方修正": "業績予想の修正（下方修正）及び特別損失の計上に関するお知らせ",
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
        "下方修正": f"{name}が通期予想を下方修正　減損で特損計上、株価は急落",
    }
    for plan in _SPIKE_PLAN:
        d = p.dates[p.days - plan["back"]]
        rows.append({"date": d, "title": heads[plan["kind"]], "url": "https://news.google.com/",
                     "publisher": "ダミー新聞"})
    df = pd.DataFrame(rows, columns=["date", "title", "url", "publisher"])
    return df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)
