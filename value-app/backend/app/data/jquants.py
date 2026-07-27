"""JQuantsProvider：J-Quants API V2（APIキー方式）から財務・株価を取得（仕様書 4.9）。

認証（既存 jp-sector-flow と同方式）:
  - V2 は APIキー方式。全リクエストに `x-api-key: <JQUANTS_API_KEY>` を付与。
  - ベース URL は https://api.jquants.com/v2（JQUANTS_BASE で上書き可）。

注意:
  - /fins/statements のサマリには BS 明細（棚卸資産・売上債権・有利子負債 等）が
    含まれないことがある。取得できない項目は None のまま保存し、下流の指標・Fスコアは
    欠損を安全側に扱う（算出不能）。実運用ではフィールド名を実レスポンスで要検証。
  - 財務三表の網羅取得が必要なら EDINET(XBRL) の追加が将来課題。
"""

from __future__ import annotations

import os
from typing import Optional

import requests

from .provider import DataProvider

_TIMEOUT = 30


class JQuantsProvider(DataProvider):
    name = "jquants"

    def __init__(self) -> None:
        self.base = (os.getenv("JQUANTS_BASE") or "https://api.jquants.com/v2").rstrip("/")
        self._session = requests.Session()

    # ------------------------------------------------------------ 認証
    def _headers(self) -> dict:
        key = os.getenv("JQUANTS_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "J-Quants の APIキーがありません。JQUANTS_API_KEY を設定してください（V2 は APIキー方式）。"
            )
        return {"x-api-key": key}

    def _get(self, path: str, params: dict, key: str) -> list[dict]:
        out: list[dict] = []
        params = dict(params)
        headers = self._headers()
        while True:
            r = self._session.get(f"{self.base}{path}", params=params,
                                   headers=headers, timeout=_TIMEOUT)
            if r.status_code >= 400:
                raise RuntimeError(f"J-Quants API {r.status_code} {path}: {r.text[:300]}")
            body = r.json()
            out.extend(body.get(key, []))
            nxt = body.get("pagination_key")
            if not nxt:
                break
            params["pagination_key"] = nxt
        return out

    @staticmethod
    def _first(row: dict, *names: str):
        for n in names:
            v = row.get(n)
            if v not in (None, ""):
                return v
        return None

    @staticmethod
    def _num(v) -> Optional[float]:
        if v in (None, ""):
            return None
        try:
            return float(str(v).replace(",", ""))
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------ 企業情報
    def fetch_company(self, code: str) -> Optional[dict]:
        rows = self._get("/equities/master", {"code": code}, key="data")
        if not rows:
            return None
        row = rows[0]
        name = self._first(row, "CompanyName", "CompanyNameEnglish", "Name")
        sector = self._first(row, "S33Nm", "Sector33CodeName", "Sector33Name")
        return {"name": name or code, "sector": sector, "market_cap": None}

    # ------------------------------------------------------------ 財務諸表
    def fetch_statements(self, code: str) -> list[dict]:
        rows = self._get("/fins/statements", {"code": code}, key="data")
        out: list[dict] = []
        for row in rows:
            # 通期（FY）のみを対象にする（仕様書：実績の確定値）
            period_type = self._first(row, "TypeOfCurrentPeriod", "typeOfCurrentPeriod")
            if period_type and str(period_type).upper() != "FY":
                continue
            fye = self._first(row, "CurrentFiscalYearEndDate", "CurrentPeriodEndDate",
                              "DisclosedDate")
            if not fye:
                continue
            fiscal_period = str(fye)[:7]  # "YYYY-MM"
            out.append(self._map_statement(row, fiscal_period))
        # 決算期の昇順
        out.sort(key=lambda r: r["fiscal_period"])
        return out

    def _map_statement(self, row: dict, fiscal_period: str) -> dict:
        f = self._first
        n = self._num
        return {
            "fiscal_period": fiscal_period,
            "source": "jquants",
            "revenue": n(f(row, "NetSales", "Sales", "OperatingRevenue", "Revenue")),
            "operating_income": n(f(row, "OperatingProfit", "OperatingIncome")),
            "ordinary_income": n(f(row, "OrdinaryProfit", "OrdinaryIncome")),
            "net_income": n(f(row, "Profit", "NetIncome", "ProfitAttributableToOwnersOfParent")),
            "operating_cf": n(f(row, "CashFlowsFromOperatingActivities")),
            "investing_cf": n(f(row, "CashFlowsFromInvestingActivities")),
            "financing_cf": n(f(row, "CashFlowsFromFinancingActivities")),
            "total_assets": n(f(row, "TotalAssets")),
            "equity": n(f(row, "Equity", "NetAssets")),
            "cash": n(f(row, "CashAndEquivalents")),
            "capital_stock": n(f(row, "CapitalStock")),
            "shares_outstanding": n(f(
                row,
                "NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock",
                "NumberOfSharesOutstanding",
            )),
            "dps": n(f(row, "ResultDividendPerShareAnnual", "DividendPerShare")),
        }

    # ------------------------------------------------------------ 市場データ
    def fetch_market(self, code: str) -> Optional[dict]:
        rows = self._get("/equities/bars/daily", {"code": code}, key="data")
        if not rows:
            return None
        rows.sort(key=lambda r: str(self._first(r, "Date", "date") or ""))
        latest = rows[-1]
        price = self._num(self._first(latest, "AdjC", "C", "Close", "AdjustmentClose"))
        as_of = self._first(latest, "Date", "date")
        # 3年前に最も近いバーの終値
        price_3y_ago = None
        if as_of and len(str(as_of)) >= 4:
            target_year = int(str(as_of)[:4]) - 3
            for r in rows:
                d = str(self._first(r, "Date", "date") or "")
                if d[:4] == str(target_year):
                    price_3y_ago = self._num(self._first(r, "AdjC", "C", "Close"))
                    break
        return {"price": price, "price_3y_ago": price_3y_ago, "as_of": as_of}
