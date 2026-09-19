from fastapi.testclient import TestClient

from app.main import app


def _client(fresh_db):
    return TestClient(app)


def test_enter_offset_and_list(fresh_db):
    with TestClient(app) as c:
        r = c.post(
            "/api/solar-offsets",
            json={
                "account_id": 1,
                "billing_period": "2026-08",
                "offset_kwh": 100,
                "source_note": "屋顶光伏",
                "entered_by": "alice",
            },
        )
        assert r.status_code == 200, r.text
        item = r.json()["item"]
        assert item["version"] == 1 and item["active"] is True

        r = c.get("/api/solar-offsets/accounts/1")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1


def test_negative_offset_rejected_by_schema(fresh_db):
    with TestClient(app) as c:
        r = c.post(
            "/api/solar-offsets",
            json={"account_id": 1, "billing_period": "2026-08", "offset_kwh": -5},
        )
        assert r.status_code == 422


def test_unknown_account_404(fresh_db):
    with TestClient(app) as c:
        r = c.post(
            "/api/solar-offsets",
            json={"account_id": 999, "billing_period": "2026-08", "offset_kwh": 10},
        )
        assert r.status_code == 404


def test_duplicate_active_409_then_correction_200(fresh_db):
    with TestClient(app) as c:
        body = {"account_id": 1, "billing_period": "2026-08", "offset_kwh": 100}
        assert c.post("/api/solar-offsets", json=body).status_code == 200
        dup = c.post("/api/solar-offsets", json={**body, "offset_kwh": 120})
        assert dup.status_code == 409

        fix = c.post(
            "/api/solar-offsets",
            json={**body, "offset_kwh": 120, "expected_version": 1, "entered_by": "bob"},
        )
        assert fix.status_code == 200, fix.text
        assert fix.json()["item"]["version"] == 2


def test_preview_does_not_persist(fresh_db):
    with TestClient(app) as c:
        c.post(
            "/api/solar-offsets",
            json={"account_id": 1, "billing_period": "2026-08", "offset_kwh": 200},
        )
        r = c.post(
            "/api/solar-offsets/preview",
            json={"account_id": 1, "billing_period": "2026-08", "gross_kwh": 400, "peak": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["gross_kwh"] == 400
        assert data["offset_kwh"] == 200
        assert data["net_kwh"] == 200
        assert data["peak_factor"] == 1.2
        assert len(data["segments"]) == 2  # 净 200：180 + 20 两段
        assert data["total"] == 127.2
        # 预览只读取抵扣，不应生成新记录
        assert len(c.get("/api/solar-offsets/accounts/1").json()["items"]) == 1


def _history_row(c, run_id):
    items = c.get("/api/history").json()["items"]
    rows = [h for h in items if h["id"] == run_id]
    assert len(rows) == 1
    return rows[0]


def _account_run(c, account_id, run_id):
    runs = c.get(f"/api/accounts/{account_id}").json()["runs"]
    rows = [r for r in runs if r["id"] == run_id]
    assert len(rows) == 1
    return rows[0]


def test_saved_run_shows_net_kwh_in_history_and_account(fresh_db):
    with TestClient(app) as c:
        c.post(
            "/api/solar-offsets",
            json={"account_id": 1, "billing_period": "2026-08", "offset_kwh": 100},
        )
        bench = c.post(
            "/api/solar-offsets/preview",
            json={"account_id": 1, "billing_period": "2026-08", "gross_kwh": 400, "peak": True},
        ).json()
        saved = c.post(
            "/api/solar-offsets/runs",
            json={"account_id": 1, "billing_period": "2026-08", "gross_kwh": 400, "peak": True},
        ).json()
        run_id = saved["run_id"]

        hist = _history_row(c, run_id)
        detail = _account_run(c, 1, run_id)

        # 两处电量相同，且等于测算台上的净电量（不是毛电量 400）
        assert hist["meter_kwh"] == bench["net_kwh"] == 300
        assert detail["billed_kwh"] == bench["net_kwh"] == 300
        # 合计两处一致，且与测算台一致
        assert hist["total"] == detail["total"] == bench["total"]


def test_new_offset_changes_new_run_but_old_run_keeps_snapshot(fresh_db):
    with TestClient(app) as c:
        c.post(
            "/api/solar-offsets",
            json={"account_id": 1, "billing_period": "2026-08", "offset_kwh": 100},
        )
        old = c.post(
            "/api/solar-offsets/runs",
            json={"account_id": 1, "billing_period": "2026-08", "gross_kwh": 400, "peak": False},
        ).json()
        old_id = old["run_id"]
        assert old["net_kwh"] == 300

        # 同一账期更正抵扣量：必须带版本号
        fix = c.post(
            "/api/solar-offsets",
            json={
                "account_id": 1,
                "billing_period": "2026-08",
                "offset_kwh": 250,
                "expected_version": 1,
            },
        )
        assert fix.status_code == 200, fix.text

        new = c.post(
            "/api/solar-offsets/runs",
            json={"account_id": 1, "billing_period": "2026-08", "gross_kwh": 400, "peak": False},
        ).json()
        new_id = new["run_id"]
        assert new["net_kwh"] == 150  # 新运行使用新的净电量

        # 旧运行两处仍保持保存当时的净电量 300
        assert _history_row(c, old_id)["meter_kwh"] == 300
        assert _account_run(c, 1, old_id)["billed_kwh"] == 300
        # 新运行两处为新净电量 150
        assert _history_row(c, new_id)["meter_kwh"] == 150
        assert _account_run(c, 1, new_id)["billed_kwh"] == 150


def test_offset_exceeding_gross_saves_zero_kwh_in_both_views(fresh_db):
    with TestClient(app) as c:
        c.post(
            "/api/solar-offsets",
            json={"account_id": 1, "billing_period": "2026-08", "offset_kwh": 120},
        )
        saved = c.post(
            "/api/solar-offsets/runs",
            json={"account_id": 1, "billing_period": "2026-08", "gross_kwh": 80, "peak": True},
        ).json()
        run_id = saved["run_id"]
        assert saved["net_kwh"] == 0
        assert saved["total"] == 0.0

        assert _history_row(c, run_id)["meter_kwh"] == 0.0
        detail = _account_run(c, 1, run_id)
        assert detail["billed_kwh"] == 0.0
        assert detail["total"] == 0.0


def test_run_without_offset_shows_workbench_kwh_in_both_views(fresh_db):
    with TestClient(app) as c:
        bench = c.post(
            "/api/solar-offsets/preview",
            json={"account_id": 1, "billing_period": "2030-01", "gross_kwh": 120, "peak": False},
        ).json()
        saved = c.post(
            "/api/solar-offsets/runs",
            json={"account_id": 1, "billing_period": "2030-01", "gross_kwh": 120, "peak": False},
        ).json()
        run_id = saved["run_id"]
        assert bench["net_kwh"] == 120

        assert _history_row(c, run_id)["meter_kwh"] == 120
        assert _account_run(c, 1, run_id)["billed_kwh"] == 120
