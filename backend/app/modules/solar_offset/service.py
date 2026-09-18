import sqlite3

from app.db import connect
from app.modules.solar_offset import repository as solar_repo
from app.modules.solar_offset.engine import bill_with_offset
from app.modules.solar_offset.exceptions import AccountNotFound, OffsetConflict
from app.repositories import accounts as accounts_repo
from app.repositories import runs as runs_repo
from app.repositories import settings as settings_repo
from app.repositories import tiers as tiers_repo


class SolarOffsetService:
    def __init__(self):
        self._conn = connect()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _require_account(self, account_id: int) -> dict:
        account = accounts_repo.get(self._conn, account_id)
        if not account:
            raise AccountNotFound(f"account {account_id} not found")
        return account

    def list_for_account(self, account_id: int) -> list[dict]:
        self._require_account(account_id)
        return solar_repo.list_for_account(self._conn, account_id)

    def enter_offset(
        self,
        account_id: int,
        billing_period: str,
        offset_kwh: float,
        source_note: str | None,
        entered_by: str | None,
        expected_version: int | None,
    ) -> dict:
        self._require_account(account_id)
        if offset_kwh < 0:
            raise ValueError("offset_kwh must be non-negative")

        active = solar_repo.get_active(self._conn, account_id, billing_period)
        if active:
            # 同一户同一账期只允许一条有效记录；更正必须带显式且匹配的版本号。
            if expected_version is None:
                raise OffsetConflict(
                    f"该账期已存在 v{active['version']} 有效记录，更正须显式传 expected_version"
                )
            if expected_version != active["version"]:
                raise OffsetConflict(
                    f"版本号不匹配：当前有效版本为 v{active['version']}，收到 v{expected_version}"
                )
            new_version = active["version"] + 1
            supersedes_id = active["id"]
            solar_repo.deactivate(self._conn, active["id"])  # 旧版只读保留
        else:
            if expected_version is not None:
                raise OffsetConflict("该账期暂无有效记录，首录不应传 expected_version")
            new_version = 1
            supersedes_id = None

        try:
            new_id = solar_repo.insert(
                self._conn,
                account_id,
                billing_period,
                offset_kwh,
                source_note,
                entered_by,
                new_version,
                supersedes_id,
            )
        except sqlite3.IntegrityError:
            # 唯一索引兜底：并发下该账期已被另一条有效记录占用。
            self._conn.rollback()  # 撤销 deactivate，保持旧有效记录不变
            raise OffsetConflict("该账期已存在有效记录（并发冲突），请刷新后带最新版本号重试")
        except Exception:
            self._conn.rollback()  # 撤销 deactivate，保持旧有效记录不变
            raise
        return solar_repo.get(self._conn, new_id)

    def preview(self, account_id: int, billing_period: str, gross_kwh: float, peak: bool) -> dict:
        account = self._require_account(account_id)
        if gross_kwh < 0:
            raise ValueError("gross_kwh must be non-negative")

        active = solar_repo.get_active(self._conn, account_id, billing_period)
        offset_kwh = active["offset_kwh"] if active else 0.0
        tiers = tiers_repo.as_calc_rows(self._conn)
        factor = settings_repo.peak_factor(self._conn) if peak else 1.0

        result = bill_with_offset(gross_kwh, offset_kwh, tiers, factor)
        return {
            "account": account,
            "billing_period": billing_period,
            "peak": peak,
            "offset_record": _record_brief(active),
            **result,
        }

    def save_run(self, account_id: int, billing_period: str, gross_kwh: float, peak: bool) -> dict:
        body = self.preview(account_id, billing_period, gross_kwh, peak)
        snapshot = {
            "gross_kwh": body["gross_kwh"],
            "offset_kwh": body["offset_kwh"],
            "net_kwh": body["net_kwh"],
            "total": body["total"],
            "gross_total": body["gross_total"],
            "saving": body["saving"],
            "peak_factor": body["peak_factor"],
            "offset_clipped": body["offset_clipped"],
            "segments": body["segments"],
            "billing_period": billing_period,
        }
        payload = {
            "account_id": account_id,
            "billing_period": billing_period,
            "gross_kwh": body["gross_kwh"],
            "peak": peak,
        }
        run_id = runs_repo.insert(self._conn, "solar", payload, snapshot, account_id)
        return {"run_id": run_id, **body}


def _record_brief(active: dict | None) -> dict | None:
    if not active:
        return None
    return {
        "id": active["id"],
        "version": active["version"],
        "offset_kwh": active["offset_kwh"],
        "source_note": active["source_note"],
        "entered_by": active["entered_by"],
        "created_at": active["created_at"],
    }
