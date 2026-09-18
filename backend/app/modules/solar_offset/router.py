from fastapi import APIRouter, HTTPException

from app.modules.solar_offset.exceptions import AccountNotFound, OffsetConflict
from app.modules.solar_offset.schemas import SolarOffsetIn, SolarPreviewIn
from app.modules.solar_offset.service import SolarOffsetService

router = APIRouter(prefix="/solar-offsets", tags=["solar-offset"])


@router.get("/accounts/{account_id}")
def list_offsets(account_id: int):
    with SolarOffsetService() as svc:
        try:
            items = svc.list_for_account(account_id)
        except AccountNotFound:
            raise HTTPException(404, "account not found")
        return {"items": items}


@router.post("")
def enter_offset(body: SolarOffsetIn):
    with SolarOffsetService() as svc:
        try:
            row = svc.enter_offset(
                body.account_id,
                body.billing_period,
                body.offset_kwh,
                body.source_note,
                body.entered_by,
                body.expected_version,
            )
        except AccountNotFound:
            raise HTTPException(404, "account not found")
        except OffsetConflict as e:
            raise HTTPException(409, str(e))
        return {"item": row}


@router.post("/preview")
def preview(body: SolarPreviewIn):
    """纯测算：返回扣减后的分段与合计，不落库、不写 calc_runs。"""
    with SolarOffsetService() as svc:
        try:
            return svc.preview(body.account_id, body.billing_period, body.gross_kwh, body.peak)
        except AccountNotFound:
            raise HTTPException(404, "account not found")


@router.post("/runs")
def save_run(body: SolarPreviewIn):
    with SolarOffsetService() as svc:
        try:
            return svc.save_run(body.account_id, body.billing_period, body.gross_kwh, body.peak)
        except AccountNotFound:
            raise HTTPException(404, "account not found")
