"""取り込みサービス（仕様書 4.9 / Phase 5）。

DataProvider から取得した数値を DB へ upsert し、手入力を置き換える。
計算・判断は行わず「集める → 保存する」だけに徹する。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from . import models
from .data.provider import DataProvider

# FinancialStatement / MarketData に書き込んでよい列名（安全のためホワイトリスト）
_FS_COLS = {c.name for c in models.FinancialStatement.__table__.columns}
_MD_COLS = {c.name for c in models.MarketData.__table__.columns}


def ingest_company(db: Session, code: str, provider: DataProvider) -> dict:
    """1銘柄分を取得して upsert する。"""
    info = provider.fetch_company(code)

    company = db.get(models.Company, code)
    if company is None:
        company = models.Company(code=code, name=(info or {}).get("name") or code)
        db.add(company)
    if info:
        if info.get("sector"):
            company.sector = info["sector"]
        if info.get("market_cap") is not None:
            company.market_cap = info["market_cap"]

    added = updated = 0
    for row in provider.fetch_statements(code):
        data = {k: v for k, v in row.items() if k in _FS_COLS and k != "company_code"}
        fp = data.get("fiscal_period")
        if not fp:
            continue
        fs = (
            db.query(models.FinancialStatement)
            .filter_by(company_code=code, fiscal_period=fp)
            .first()
        )
        if fs is None:
            fs = models.FinancialStatement(company_code=code)
            db.add(fs)
            added += 1
        else:
            updated += 1
        for k, v in data.items():
            setattr(fs, k, v)

    market = provider.fetch_market(code)
    if market:
        md = db.get(models.MarketData, code)
        if md is None:
            md = models.MarketData(company_code=code)
            db.add(md)
        for k, v in market.items():
            if k in _MD_COLS and k != "company_code":
                setattr(md, k, v)

    db.commit()
    return {
        "code": code,
        "provider": provider.name,
        "statements_added": added,
        "statements_updated": updated,
        "market": bool(market),
    }
