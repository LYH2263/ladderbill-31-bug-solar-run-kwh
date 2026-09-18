"""Solar offset module DDL.

按户号 + 账期记录光伏抵扣电量。同一户同一账期至多一条 active=1 的有效记录
（部分唯一索引兜底）；更正时旧记录置 active=0 只读保留，新版本号递增。
"""

DDL = """
CREATE TABLE IF NOT EXISTS solar_offsets(
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,
    billing_period TEXT NOT NULL,
    offset_kwh REAL NOT NULL CHECK(offset_kwh >= 0),
    source_note TEXT,
    entered_by TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    version INTEGER NOT NULL DEFAULT 1,
    supersedes_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_solar_active_per_period
    ON solar_offsets(account_id, billing_period) WHERE active = 1;
CREATE INDEX IF NOT EXISTS ix_solar_account_period
    ON solar_offsets(account_id, billing_period, version);
"""
