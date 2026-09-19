from fastapi import APIRouter, HTTPException

from app.routers.run_fields import billed_kwh, loads_blob
from app.services.billing_service import BillingService

router = APIRouter(tags=["history"])


def _history_item(row: dict) -> dict:
    payload = loads_blob(row.get("input_json"))
    result = loads_blob(row.get("result_json"))
    item = dict(row)
    item["meter_kwh"] = billed_kwh(result, payload)
    item["total"] = result.get("total")
    return item


@router.get("/history")
def list_history(limit: int = 50):
    with BillingService() as svc:
        rows = svc.list_history(limit)
        return {"items": [_history_item(row) for row in rows]}


@router.get("/history/{run_id}")
def get_history(run_id: int):
    with BillingService() as svc:
        row = svc.get_run(run_id)
        if not row:
            raise HTTPException(404, "run not found")
        return _history_item(row)
