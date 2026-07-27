"""予想Excel アップロード＆マッピングのルーター（仕様書 Phase 3 / 4.6）。"""

from __future__ import annotations

import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models, schemas
from ..engines.excel_adapter import (
    load_sheets, load_preview, auto_detect_mappings, extract_values,
)

router = APIRouter(prefix="/api", tags=["excel"])

# アップロード一時ファイル置き場（プロセス内で file_id → パスを保持）。
_UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "value_app_uploads")
os.makedirs(_UPLOAD_DIR, exist_ok=True)


def _path_for(file_id: str) -> str:
    return os.path.join(_UPLOAD_DIR, f"{file_id}.xlsx")


@router.post("/excel/preview")
async def excel_preview(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Excel をアップロードし、シートのプレビューと自動検出マッピング候補を返す。"""
    data = await file.read()
    try:
        sheets = load_sheets(data)
        preview = load_preview(data)
    except Exception as exc:  # openpyxl のパースエラー等
        raise HTTPException(status_code=400, detail=f"Excel を読み込めません: {exc}")

    file_id = uuid.uuid4().hex
    with open(_path_for(file_id), "wb") as f:
        f.write(data)

    suggestions = auto_detect_mappings(sheets)
    profiles = [
        {"format_name": p.format_name, "company_code": p.company_code, "mapping": p.mapping}
        for p in db.query(models.MappingProfile).all()
    ]
    return {
        "file_id": file_id,
        "sheets": [sd.name for sd in sheets],
        "preview": preview,
        "suggestions": suggestions,
        "saved_profiles": profiles,
    }


def _mapping_to_plain(mapping: dict[str, schemas.CellRef]) -> dict[str, dict]:
    return {k: v.model_dump() for k, v in mapping.items()}


@router.post("/companies/{code}/excel/extract")
def excel_extract(code: str, payload: schemas.ExtractIn, db: Session = Depends(get_db)):
    """確定マッピングで値を抽出し、必要なら Forecast と定性メモを保存する（仕様書 4.6）。"""
    company = db.get(models.Company, code)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")

    path = _path_for(payload.file_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="アップロードファイルが見つかりません（再アップロードしてください）")

    with open(path, "rb") as f:
        sheets = load_sheets(f.read())

    mapping = _mapping_to_plain(payload.mapping)
    values = extract_values(sheets, mapping)

    saved = False
    if payload.save and payload.fiscal_period:
        # Forecast 保存（同一キーがあれば更新）
        fc = (
            db.query(models.Forecast)
            .filter_by(company_code=code, fiscal_period=payload.fiscal_period,
                       source=payload.source, scenario=payload.scenario)
            .first()
        )
        if fc is None:
            fc = models.Forecast(
                company_code=code, fiscal_period=payload.fiscal_period,
                source=payload.source, scenario=payload.scenario,
            )
            db.add(fc)
        fc.revenue = values.get("revenue")
        fc.operating_income = values.get("operating_income")
        fc.operating_margin = values.get("operating_margin")
        fc.net_income = values.get("net_income")
        fc.eps = values.get("eps")
        fc.bps = values.get("bps")
        fc.dps = values.get("dps")

        # 定性情報はユーザーの Excel を正とする（qualitative_note を上書き）
        note = values.get("qualitative_note")
        if note:
            company.qualitative_note = note
        db.commit()
        saved = True

    # マッピングを名前付きで保存（次回以降 再利用）
    if payload.save_profile_as:
        _upsert_profile(db, payload.save_profile_as, code, mapping)

    return {"values": values, "saved": saved}


def _upsert_profile(db: Session, format_name: str, company_code: str, mapping: dict) -> None:
    prof = (
        db.query(models.MappingProfile)
        .filter_by(company_code=company_code, format_name=format_name)
        .first()
    )
    if prof is None:
        prof = models.MappingProfile(
            company_code=company_code, format_name=format_name, mapping=mapping
        )
        db.add(prof)
    else:
        prof.mapping = mapping
    db.commit()


@router.get("/mapping_profiles")
def list_profiles(db: Session = Depends(get_db)):
    return [
        {"id": p.id, "format_name": p.format_name, "company_code": p.company_code,
         "mapping": p.mapping}
        for p in db.query(models.MappingProfile).all()
    ]


@router.post("/mapping_profiles")
def save_profile(payload: schemas.MappingProfileIn, db: Session = Depends(get_db)):
    mapping = _mapping_to_plain(payload.mapping)
    _upsert_profile(db, payload.format_name, payload.company_code, mapping)
    return {"saved": True, "format_name": payload.format_name}
