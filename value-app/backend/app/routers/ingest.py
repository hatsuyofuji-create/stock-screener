"""データ自動取得のルーター（仕様書 Phase 5 / 4.9）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from .. import schemas
from ..data.provider import get_provider
from ..ingest import ingest_company

router = APIRouter(prefix="/api", tags=["ingest"])


@router.post("/companies/{code}/ingest")
def ingest_one(code: str, provider: str | None = None, db: Session = Depends(get_db)):
    """1銘柄を自動取得して保存（手入力を置き換える）。provider=mock/jquants。"""
    try:
        p = get_provider(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        return ingest_company(db, code, p)
    except RuntimeError as exc:
        # APIキー未設定・外部APIエラー等
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/ingest")
def ingest_many(payload: schemas.IngestIn, db: Session = Depends(get_db)):
    """複数銘柄を一括取得。"""
    try:
        p = get_provider(payload.provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    results = []
    for code in payload.codes:
        try:
            results.append(ingest_company(db, code, p))
        except RuntimeError as exc:
            results.append({"code": code, "error": str(exc)})
    return {"count": len(results), "results": results}
