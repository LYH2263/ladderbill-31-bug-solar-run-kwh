from fastapi import APIRouter, HTTPException

from app.routers.run_fields import billed_kwh, loads_blob
from app.services.billing_service import BillingService

router = APIRouter(tags=["accounts"])


def _account_run(row: dict) -> dict:
    payload = loads_blob(row.get("input_json"))
    result = loads_blob(row.get("result_json"))
    return {
        "id": row["id"],
        "kind": row["kind"],
        "billed_kwh": billed_kwh(result, payload),
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
