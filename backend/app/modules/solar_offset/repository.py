import sqlite3
from datetime import datetime, timezone

_COLS = "id, account_id, billing_period, offset_kwh, source_note, entered_by, active, version, supersedes_id, created_at"


def init(conn: sqlite3.Connection) -> None:
    from app.modules.solar_offset.ddl import DDL

    conn.executescript(DDL)
    conn.commit()


def _row(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "account_id": r["account_id"],
        "billing_period": r["billing_period"],
        "offset_kwh": r["offset_kwh"],
        "source_note": r["source_note"],
        "entered_by": r["entered_by"],
        "active": bool(r["active"]),
        "version": r["version"],
        "supersedes_id": r["supersedes_id"],
        "created_at": r["created_at"],
    }


def get_active(conn: sqlite3.Connection, account_id: int, billing_period: str) -> dict | None:
    q = f"SELECT {_COLS} FROM solar_offsets WHERE account_id=? AND billing_period=? AND active=1"
    row = conn.execute(q, (account_id, billing_period)).fetchone()
    return _row(row) if row else None


def list_for_account(conn: sqlite3.Connection, account_id: int) -> list[dict]:
    """全部版本（含已失效只读旧版），账期倒序、版本倒序。"""
    q = f"SELECT {_COLS} FROM solar_offsets WHERE account_id=? ORDER BY billing_period DESC, version DESC"
    return [_row(r) for r in conn.execute(q, (account_id,)).fetchall()]


def deactivate(conn: sqlite3.Connection, record_id: int) -> None:
    conn.execute("UPDATE solar_offsets SET active=0 WHERE id=?", (record_id,))


def insert(
    conn: sqlite3.Connection,
    account_id: int,
    billing_period: str,
    offset_kwh: float,
    source_note: str | None,
    entered_by: str | None,
    version: int,
    supersedes_id: int | None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO solar_offsets(
            account_id, billing_period, offset_kwh, source_note, entered_by,
            active, version, supersedes_id, created_at
        ) VALUES (?,?,?,?,?,1,?,?,?)
        """,
        (account_id, billing_period, offset_kwh, source_note, entered_by, version, supersedes_id, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def get(conn: sqlite3.Connection, record_id: int) -> dict | None:
    row = conn.execute(f"SELECT {_COLS} FROM solar_offsets WHERE id=?", (record_id,)).fetchone()
    return _row(row) if row else None
