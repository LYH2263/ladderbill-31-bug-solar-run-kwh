import json

from fastapi import APIRouter, HTTPException

from app.services.billing_service import BillingService

router = APIRouter(tags=["accounts"])


def _loads(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _billed_kwh(result: dict, payload: dict):
    if "net_kwh" in result:
        return float(result["net_kwh"])
    if "kwh" in result:
        return result["kwh"]
    return payload.get("kwh")


def _account_run(row: dict) -> dict:
    payload = _loads(row.get("input_json"))
    result = _loads(row.get("result_json"))
    return {
        "id": row["id"],
        "kind": row["kind"],
        "billed_kwh": _billed_kwh(result, payload),
        "total": result.get("total"),
        "created_at": row["created_at"],
    }


@router.get("/accounts")
def list_accounts():
    with BillingService() as svc:
        return {"items": svc.list_accounts()}


@router.get("/accounts/{account_id}")
def get_account(account_id: int):
    with BillingService() as svc:
        row = svc.get_account(account_id)
        if not row:
            raise HTTPException(404, "account not found")
        readings = svc.readings_for_account(account_id)
        runs = [_account_run(r) for r in svc.runs_for_account(account_id)]
        return {"account": row, "readings": readings, "runs": runs}
