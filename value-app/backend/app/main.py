"""FastAPI アプリのエントリポイント（仕様書 Phase 0/1）。

計算ロジックはすべて engines/ に置き、API は「集める→採点→返す」に徹する。
"""

from __future__ import annotations

import csv
import io
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .db import get_db, init_db
from . import models, schemas
from .services import to_raw, sorted_statements, latest_and_prior
from .engines.financials import compute_metrics, compute_changes
from .engines.fscore import compute_fscore

DISCLAIMER = (
    "本アプリは投資助言ツールではありません。投資判断は利用者自身の責任で行ってください。"
    "外部データの取得は各サービスの利用規約を遵守してください。"
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="バリュー投資アプリ (上原メソッド)", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict:
    return {"app": "value-app", "phase": "0-1", "disclaimer": DISCLAIMER}


@app.get("/api/disclaimer")
def disclaimer() -> dict:
    return {"disclaimer": DISCLAIMER}


# ---------- 企業 ----------

@app.post("/api/companies", response_model=schemas.CompanyOut)
def create_company(payload: schemas.CompanyIn, db: Session = Depends(get_db)):
    if db.get(models.Company, payload.code):
        raise HTTPException(status_code=409, detail="already exists")
    moat = ",".join(payload.moat_tags) if payload.moat_tags else None
    company = models.Company(
        code=payload.code, name=payload.name, sector=payload.sector,
        market_cap=payload.market_cap, growth_type=payload.growth_type,
        moat_tags=moat, qualitative_note=payload.qualitative_note,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@app.get("/api/companies", response_model=list[schemas.CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    return db.query(models.Company).all()


@app.get("/api/companies/{code}", response_model=schemas.CompanyOut)
def get_company(code: str, db: Session = Depends(get_db)):
    company = db.get(models.Company, code)
    if not company:
        raise HTTPException(status_code=404, detail="not found")
    return company


# ---------- 財務データ ----------

@app.post("/api/companies/{code}/statements", response_model=schemas.FinancialStatementOut)
def add_statement(code: str, payload: schemas.FinancialStatementIn, db: Session = Depends(get_db)):
    if not db.get(models.Company, code):
        raise HTTPException(status_code=404, detail="company not found")
    fs = models.FinancialStatement(company_code=code, **payload.model_dump())
    db.add(fs)
    db.commit()
    db.refresh(fs)
    return fs


@app.get("/api/companies/{code}/statements", response_model=list[schemas.FinancialStatementOut])
def list_statements(code: str, db: Session = Depends(get_db)):
    company = db.get(models.Company, code)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    return sorted_statements(company.statements)


@app.post("/api/companies/{code}/statements/import_csv")
async def import_statements_csv(code: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """財務データを CSV で一括取り込み（手入力検証用・仕様書 Phase 1）。

    ヘッダ行に fiscal_period, revenue, ... など FinancialStatement の列名を持つ CSV。
    """
    if not db.get(models.Company, code):
        raise HTTPException(status_code=404, detail="company not found")

    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    valid_cols = set(schemas.FinancialStatementIn.model_fields.keys())
    added = 0
    for row in reader:
        data: dict = {}
        for key, raw in row.items():
            if key not in valid_cols:
                continue
            raw = (raw or "").strip()
            if raw == "":
                continue
            data[key] = raw if key in ("fiscal_period", "source") else float(raw)
        if "fiscal_period" not in data:
            continue
        fs = models.FinancialStatement(company_code=code, **data)
        db.add(fs)
        added += 1
    db.commit()
    return {"imported": added}


# ---------- 分析（4.1 / 4.2） ----------

@app.get("/api/companies/{code}/metrics")
def get_metrics(code: str, effective_tax_rate: float = 0.30, db: Session = Depends(get_db)):
    """全決算期の財務指標＋前年比（仕様書 4.1）。"""
    company = db.get(models.Company, code)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    ordered = sorted_statements(company.statements)
    metrics = [compute_metrics(to_raw(fs), effective_tax_rate=effective_tax_rate) for fs in ordered]

    result = {"code": code, "metrics": [m.to_dict() for m in metrics], "changes": None}
    if len(metrics) >= 2:
        changes = compute_changes(metrics[-1], metrics[-2])
        result["changes"] = {k: v.to_dict() for k, v in changes.items()}
    return result


@app.get("/api/companies/{code}/fscore")
def get_fscore(code: str, effective_tax_rate: float = 0.30, db: Session = Depends(get_db)):
    """Fスコア（実績版）を算出する（仕様書 4.2）。"""
    company = db.get(models.Company, code)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    latest, prior = latest_and_prior(company.statements)
    if latest is None or prior is None:
        raise HTTPException(status_code=400, detail="Fスコアには最低2期分の財務データが必要です")
    result = compute_fscore(
        to_raw(latest), to_raw(prior), mode="actual",
        effective_tax_rate=effective_tax_rate,
    )
    return result.to_dict()
