"""適正株価・安全域・シナリオ計算のルーター（仕様書 Phase 2 / 4.3）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models, schemas
from ..engines.valuation import (
    ScenarioInputs, project_scenario,
    fair_value_per, fair_value_pbr, fair_value_dividend,
    risk_reward,
)

router = APIRouter(prefix="/api", tags=["valuation"])


def _to_inputs(payload: schemas.ScenarioIn) -> ScenarioInputs:
    return ScenarioInputs(**payload.model_dump())


def _fair_values(result, multiples: schemas.FairMultiples, current_price):
    """1シナリオの予想値から3方式の適正株価を返す。"""
    return {
        "per": fair_value_per(result.eps, multiples.fair_per, current_price).to_dict(),
        "pbr": fair_value_pbr(result.bps, multiples.fair_pbr, current_price).to_dict(),
        "dividend": fair_value_dividend(result.dps, multiples.fair_yield, current_price).to_dict(),
    }


@router.post("/valuation")
def compute_valuation(payload: schemas.ValuationIn):
    """base/negative シナリオから予想値・適正株価・安全域・リスクリワードを一括算出。"""
    base_res = project_scenario(_to_inputs(payload.base))
    base_fv = _fair_values(base_res, payload.multiples, payload.current_price)

    neg_res = None
    neg_fv = None
    rr = None
    if payload.negative is not None:
        neg_res = project_scenario(_to_inputs(payload.negative))
        neg_fv = _fair_values(neg_res, payload.multiples, payload.current_price)
        # リスクリワードは PER 基準の適正株価で評価（主指標は景気局面で切替＝Phase 6）
        base_fair = base_fv["per"]["fair_price"]
        neg_fair = neg_fv["per"]["fair_price"]
        rr = risk_reward(base_fair, neg_fair, payload.current_price).to_dict()

    return {
        "current_price": payload.current_price,
        "base": {"projection": base_res.to_dict(), "fair_value": base_fv},
        "negative": (
            {"projection": neg_res.to_dict(), "fair_value": neg_fv}
            if neg_res is not None else None
        ),
        "risk_reward": rr,
    }


@router.post("/companies/{code}/valuation")
def company_valuation(code: str, payload: schemas.ValuationIn, db: Session = Depends(get_db)):
    """銘柄に紐づけてシナリオ計算し、必要なら Forecast に保存する（仕様書 4.3）。"""
    company = db.get(models.Company, code)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")

    result = compute_valuation(payload)

    if payload.save and payload.fiscal_period:
        for label, scen_in, block in (
            ("base", payload.base, result["base"]),
            ("negative", payload.negative, result["negative"]),
        ):
            if block is None or scen_in is None:
                continue
            proj = block["projection"]
            fc = models.Forecast(
                company_code=code, fiscal_period=payload.fiscal_period,
                source=payload.source, scenario=label,
                revenue=scen_in.revenue, operating_income=proj["operating_income"],
                operating_margin=scen_in.operating_margin, net_income=proj["net_income"],
                eps=proj["eps"], bps=proj["bps"], dps=proj["dps"],
                one_time_items=scen_in.one_time_items,
            )
            db.add(fc)
        db.commit()
        result["saved"] = True

    return result
