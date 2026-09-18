import json

from fastapi import APIRouter, HTTPException

from app.services.billing_service import BillingService

router = APIRouter(tags=["history"])


def _loads(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _meter_kwh(result: dict, payload: dict):
    if "gross_kwh" in result and "net_kwh" in result:
        net = float(result["net_kwh"])
        if net <= 1e-9:
            return 0.0
        return float(result["gross_kwh"])
    if "kwh" in result:
        return result["kwh"]
    return payload.get("kwh")


def _history_item(row: dict) -> dict:
    payload = _loads(row.get("input_json"))
    result = _loads(row.get("result_json"))
    item = dict(row)
    item["meter_kwh"] = _meter_kwh(result, payload)
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
