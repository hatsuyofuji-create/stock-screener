"""スクリーニング＋銘柄マトリクスのルーター（仕様書 Phase 4 / 4.5 / 4.7）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models, schemas
from ..services import build_all_snapshots
from ..engines.screening import (
    ThresholdCriteria, apply_threshold, magic_formula, build_matrix,
)

router = APIRouter(prefix="/api", tags=["screening"])


@router.put("/companies/{code}/market")
def set_market_data(code: str, payload: schemas.MarketDataIn, db: Session = Depends(get_db)):
    """市場データ（株価等）を登録・更新する（Phase 5 で自動取得に置換予定）。"""
    if not db.get(models.Company, code):
        raise HTTPException(status_code=404, detail="company not found")
    md = db.get(models.MarketData, code)
    if md is None:
        md = models.MarketData(company_code=code)
        db.add(md)
    for k, v in payload.model_dump().items():
        setattr(md, k, v)
    db.commit()
    return {"saved": True}


@router.post("/screen/threshold")
def screen_threshold(criteria: schemas.ThresholdIn, db: Session = Depends(get_db)):
    """閾値フィルター（モードA）。ヒット件数と銘柄を返す（仕様書 4.5）。"""
    snaps = build_all_snapshots(db)
    result = apply_threshold(snaps, ThresholdCriteria(**criteria.model_dump()))
    return result


@router.post("/screen/magic")
def screen_magic(top_n: int = 30, db: Session = Depends(get_db)):
    """魔法の公式（モードB）。合成ランク上位 N 社（仕様書 4.5）。"""
    snaps = build_all_snapshots(db)
    return magic_formula(snaps, top_n=top_n)


@router.get("/matrix")
def matrix(pbr_threshold: float = 1.0, fscore_healthy: int = 7,
           high_roe: float = 0.15, db: Session = Depends(get_db)):
    """銘柄マトリクス（横軸PBR×縦軸Fスコア）の散布図データ（仕様書 4.7）。"""
    snaps = build_all_snapshots(db)
    return build_matrix(snaps, pbr_threshold=pbr_threshold,
                        fscore_healthy=fscore_healthy, high_roe=high_roe)


# ---- スクリーニング設定の保存・再利用（仕様書 4.5） ----

@router.get("/screen/settings")
def list_settings(db: Session = Depends(get_db)):
    return [
        {"id": s.id, "name": s.name, "mode": s.mode, "params": s.params}
        for s in db.query(models.ScreenSetting).all()
    ]


@router.post("/screen/settings")
def save_setting(payload: schemas.ScreenSettingIn, db: Session = Depends(get_db)):
    s = db.query(models.ScreenSetting).filter_by(name=payload.name).first()
    if s is None:
        s = models.ScreenSetting(name=payload.name, mode=payload.mode, params=payload.params)
        db.add(s)
    else:
        s.mode = payload.mode
        s.params = payload.params
    db.commit()
    return {"saved": True, "name": payload.name}
