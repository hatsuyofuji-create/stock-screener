"""景気局面＋ポートフォリオ管理・アラートのルーター（仕様書 Phase 6 / 4.4 / 4.8）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models, schemas
from ..services import build_snapshot
from ..engines.business_cycle import select_business_cycle, PHASES
from ..engines.portfolio import (
    take_profit_alert, stop_loss_alert, position_size,
    diversification_check, reevaluate_as_new,
)

router = APIRouter(prefix="/api", tags=["portfolio"])


# ---- 景気局面（4.4） ----

@router.get("/business-cycle/phases")
def business_cycle_phases():
    return {"phases": list(PHASES)}


@router.post("/business-cycle")
def business_cycle(payload: schemas.BusinessCycleIn):
    try:
        sel = select_business_cycle(payload.phase, payload.is_cyclical)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return sel.to_dict()


# ---- 保有銘柄（4.8） ----

@router.get("/holdings", response_model=list[schemas.HoldingOut])
def list_holdings(db: Session = Depends(get_db)):
    return db.query(models.Holding).all()


@router.post("/holdings", response_model=schemas.HoldingOut)
def add_holding(payload: schemas.HoldingIn, db: Session = Depends(get_db)):
    if not db.get(models.Company, payload.company_code):
        raise HTTPException(status_code=404, detail="company not found")
    h = models.Holding(**payload.model_dump())
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


@router.delete("/holdings/{holding_id}")
def delete_holding(holding_id: int, db: Session = Depends(get_db)):
    h = db.get(models.Holding, holding_id)
    if not h:
        raise HTTPException(status_code=404, detail="not found")
    db.delete(h)
    db.commit()
    return {"deleted": True}


def _holding_context(db: Session, holding_id: int):
    h = db.get(models.Holding, holding_id)
    if not h:
        raise HTTPException(status_code=404, detail="holding not found")
    company = db.get(models.Company, h.company_code)
    market = db.get(models.MarketData, h.company_code)
    snap = build_snapshot(company, market) if company else None
    price = market.price if market else None
    return h, company, snap, price


@router.post("/holdings/{holding_id}/take-profit")
def holding_take_profit(holding_id: int, payload: schemas.TakeProfitIn,
                        db: Session = Depends(get_db)):
    """利確アラート（仕様書 4.8）。成長タイプ別ルールを適用。"""
    h, company, _snap, price = _holding_context(db, holding_id)
    current = payload.current_price if payload.current_price is not None else price
    alert = take_profit_alert(
        growth_type=company.growth_type if company else None,
        current_price=current,
        fair_price=payload.fair_price,
        overvalued_factor=payload.overvalued_factor,
        at_cycle_peak=payload.at_cycle_peak,
        reached_hist_avg_valuation=payload.reached_hist_avg_valuation,
        recovery_target_price=payload.recovery_target_price,
    )
    return alert.to_dict()


@router.post("/holdings/{holding_id}/stop-loss")
def holding_stop_loss(holding_id: int, payload: schemas.StopLossIn,
                      db: Session = Depends(get_db)):
    """損切りアラート（仕様書 4.8）。①シナリオ崩壊 ②バリュートラップ継続 ③2年含み損。"""
    h, _company, snap, price = _holding_context(db, holding_id)
    current = payload.current_price if payload.current_price is not None else price
    pbr = payload.pbr if payload.pbr is not None else (snap.pbr if snap else None)
    fscore = payload.fscore if payload.fscore is not None else (snap.fscore if snap else None)
    alert = stop_loss_alert(
        scenario_broken=payload.scenario_broken,
        pbr=pbr, fscore=fscore, value_trap_persist=payload.value_trap_persist,
        buy_date=h.buy_date, buy_price=h.buy_price, current_price=current,
    )
    return alert.to_dict()


@router.get("/portfolio/diversification")
def portfolio_diversification(db: Session = Depends(get_db)):
    """分散チェック（保有5〜10・業種偏り）。仕様書 4.8。"""
    holdings = db.query(models.Holding).all()
    rows = []
    for h in holdings:
        company = db.get(models.Company, h.company_code)
        rows.append({"code": h.company_code, "sector": company.sector if company else None})
    return diversification_check(rows).to_dict()


@router.post("/portfolio/position-size")
def portfolio_position_size(payload: schemas.PositionSizeIn):
    """ポジションサイズ提案（自信度 × アップサイド％）。仕様書 4.8。"""
    return position_size(payload.confidence, payload.upside, payload.max_weight).to_dict()


@router.post("/portfolio/reevaluate")
def portfolio_reevaluate(payload: schemas.ReevaluateIn):
    """「今この株を非保有と仮定」再評価（行動バイアス除去）。仕様書 4.8。"""
    return reevaluate_as_new(
        margin_of_safety=payload.margin_of_safety, fscore=payload.fscore
    ).to_dict()
