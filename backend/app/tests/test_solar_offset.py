import pytest

from app.modules.solar_offset.engine import bill_with_offset, deduct
from app.modules.solar_offset.exceptions import AccountNotFound, OffsetConflict
from app.modules.solar_offset.service import SolarOffsetService

TIERS = [
    {"up_to": 180, "price": 0.52},
    {"up_to": 260, "price": 0.62},
    {"up_to": None, "price": 0.82},
]


# ---------- 引擎：扣减 / 净电量下限 ----------

def test_deduct_partial():
    gross, applied, net, clipped = deduct(400, 100)
    assert (gross, applied, net) == (400, 100, 300)
    assert clipped is False


def test_deduct_offset_exceeds_gross_clips_net_to_zero():
    gross, applied, net, clipped = deduct(80, 100)
    assert (gross, applied, net) == (80, 80, 0)
    assert clipped is True


def test_deduct_negative_rejected():
    with pytest.raises(ValueError):
        deduct(-1, 10)
    with pytest.raises(ValueError):
        deduct(10, -1)


def test_bill_order_offset_then_tiers_then_peak():
    # 毛 400，抵扣 200 → 净 200：180@0.52 + 20@0.62，尖峰 1.2 只作用于净额。
    r = bill_with_offset(400, 200, TIERS, 1.2)
    assert r["gross_kwh"] == 400
    assert r["offset_kwh"] == 200
    assert r["net_kwh"] == 200
    assert r["total_plain"] == round(180 * 0.52 + 20 * 0.62, 2)  # 106.0
    assert r["total"] == round((180 * 0.52 + 20 * 0.62) * 1.2, 2)  # 127.2
    # 毛口径同系数全额 309.6，抵扣节省 182.4
    assert r["gross_total"] == 309.6
    assert r["saving"] == round(309.6 - 127.2, 2)
    seg = r["segments"][0]
    assert seg["base_price"] == 0.52
    assert seg["peak_factor"] == 1.2
    assert seg["price"] == round(0.52 * 1.2, 4)
    assert seg["base_amount"] == round(180 * 0.52, 2)
    assert seg["amount"] == round(180 * 0.52 * 1.2, 2)


def test_bill_zero_net_has_no_segments():
    r = bill_with_offset(50, 50, TIERS, 1.2)
    assert r["net_kwh"] == 0
    assert r["segments"] == []
    assert r["total"] == 0.0
    assert r["total_plain"] == 0.0


def test_peak_factor_not_applied_to_offset_amount():
    # 抵扣段本身不参与计费；净 0 时即便尖峰也无金额。
    r = bill_with_offset(120, 120, TIERS, 1.2)
    assert r["total"] == 0.0


# ---------- 服务：落库 / 版本更正 / 校验 ----------

def test_enter_first_version(fresh_db):
    with SolarOffsetService() as svc:
        row = svc.enter_offset(1, "2026-08", 100, "屋顶光伏", "alice", None)
    assert row["version"] == 1
    assert row["active"] is True
    assert row["supersedes_id"] is None
    assert row["offset_kwh"] == 100
    assert row["entered_by"] == "alice"


def test_enter_unknown_account_raises(fresh_db):
    with SolarOffsetService() as svc:
        with pytest.raises(AccountNotFound):
            svc.enter_offset(999, "2026-08", 10, None, None, None)


def test_duplicate_active_without_version_conflicts(fresh_db):
    with SolarOffsetService() as svc:
        svc.enter_offset(1, "2026-08", 100, None, None, None)
        with pytest.raises(OffsetConflict):
            svc.enter_offset(1, "2026-08", 120, None, None, None)
        items = svc.list_for_account(1)
    # 冲突后仍只有一条有效记录
    assert len(items) == 1
    assert items[0]["offset_kwh"] == 100


def test_correction_with_explicit_version_keeps_old_readonly(fresh_db):
    with SolarOffsetService() as svc:
        v1 = svc.enter_offset(1, "2026-08", 100, "old", "alice", None)
        v2 = svc.enter_offset(1, "2026-08", 130, "corrected", "bob", 1)
        assert v2["version"] == 2
        assert v2["supersedes_id"] == v1["id"]
        items = svc.list_for_account(1)
    by_ver = {r["version"]: r for r in items}
    assert by_ver[1]["active"] is False  # 旧版只读保留
    assert by_ver[2]["active"] is True
    assert by_ver[2]["offset_kwh"] == 130


def test_correction_wrong_version_conflicts_and_preserves_active(fresh_db):
    with SolarOffsetService() as svc:
        svc.enter_offset(1, "2026-08", 100, None, None, None)
        with pytest.raises(OffsetConflict):
            svc.enter_offset(1, "2026-08", 130, None, None, 5)  # 版本号不匹配
        items = svc.list_for_account(1)
    assert len(items) == 1
    assert items[0]["version"] == 1
    assert items[0]["active"] is True


def test_first_entry_with_version_conflicts(fresh_db):
    with SolarOffsetService() as svc:
        with pytest.raises(OffsetConflict):
            svc.enter_offset(1, "2026-08", 100, None, None, 1)


def test_distinct_periods_each_one_active(fresh_db):
    with SolarOffsetService() as svc:
        svc.enter_offset(1, "2026-07", 50, None, None, None)
        svc.enter_offset(1, "2026-08", 60, None, None, None)
        items = svc.list_for_account(1)
    assert len(items) == 2
    assert all(r["active"] for r in items)


# ---------- 预览：不落库、不写运行 ----------

def test_preview_applies_active_offset_without_persisting(fresh_db):
    from app.db import connect

    with SolarOffsetService() as svc:
        svc.enter_offset(1, "2026-08", 200, "pv", "alice", None)
        before = svc.list_for_account(1)
        r = svc.preview(1, "2026-08", 400, peak=True)
        after = svc.list_for_account(1)
    assert r["gross_kwh"] == 400
    assert r["offset_kwh"] == 200
    assert r["net_kwh"] == 200
    assert r["offset_record"]["version"] == 1
    assert before == after  # 预览不改动抵扣记录

    conn = connect()
    runs = conn.execute("SELECT COUNT(*) c FROM calc_runs").fetchone()["c"]
    conn.close()
    # 种子仅 2 条 calc_runs，预览未新增
    assert runs == 2


def test_preview_unknown_account_raises(fresh_db):
    with SolarOffsetService() as svc:
        with pytest.raises(AccountNotFound):
            svc.preview(42, "2026-08", 100, False)


def test_preview_period_without_offset_uses_zero(fresh_db):
    with SolarOffsetService() as svc:
        r = svc.preview(1, "2030-01", 120, peak=False)
    assert r["offset_kwh"] == 0
    assert r["net_kwh"] == 120
    assert r["offset_record"] is None
