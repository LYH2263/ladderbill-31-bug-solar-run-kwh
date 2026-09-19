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


# ---------- 保存后：记录列表与户详情电量口径一致（净电量） ----------

def _history_kwh(c, run_id):
    items = c.get("/api/history").json()["items"]
    return next(i for i in items if i["id"] == run_id)


def _account_run(c, account_id, run_id):
    runs = c.get(f"/api/accounts/{account_id}").json()["runs"]
    return next(r for r in runs if r["id"] == run_id)


def test_saved_run_shows_net_kwh_in_history_and_account(fresh_db):
    with TestClient(app) as c:
        c.post(
            "/api/solar-offsets",
            json={"account_id": 1, "billing_period": "2026-08", "offset_kwh": 200},
        )
        preview = c.post(
            "/api/solar-offsets/preview",
            json={"account_id": 1, "billing_period": "2026-08", "gross_kwh": 400, "peak": False},
        ).json()
        saved = c.post(
            "/api/solar-offsets/runs",
            json={"account_id": 1, "billing_period": "2026-08", "gross_kwh": 400, "peak": False},
        ).json()
        run_id = saved["run_id"]

        h = _history_kwh(c, run_id)
        a = _account_run(c, 1, run_id)
        # 两处电量相同，且等于保存前测算台的净电量
        assert h["meter_kwh"] == preview["net_kwh"] == 200
        assert a["billed_kwh"] == preview["net_kwh"] == 200
        # 两处合计一致，且与测算台一致
        assert h["total"] == a["total"] == preview["total"] == 106.0


def test_new_offset_affects_only_runs_saved_afterwards(fresh_db):
    with TestClient(app) as c:
        c.post(
            "/api/solar-offsets",
            json={"account_id": 1, "billing_period": "2026-08", "offset_kwh": 200},
        )
        run1 = c.post(
            "/api/solar-offsets/runs",
            json={"account_id": 1, "billing_period": "2026-08", "gross_kwh": 400, "peak": False},
        ).json()["run_id"]

        # 同一账期再记入一笔抵扣（更正为 350）
        c.post(
            "/api/solar-offsets",
            json={
                "account_id": 1,
                "billing_period": "2026-08",
                "offset_kwh": 350,
                "expected_version": 1,
            },
        )
        run2 = c.post(
            "/api/solar-offsets/runs",
            json={"account_id": 1, "billing_period": "2026-08", "gross_kwh": 400, "peak": False},
        ).json()["run_id"]

        # 新运行用新的净电量 50
        assert _history_kwh(c, run2)["meter_kwh"] == 50
        assert _account_run(c, 1, run2)["billed_kwh"] == 50
        # 旧运行两处仍保持保存当时的净电量 200
        assert _history_kwh(c, run1)["meter_kwh"] == 200
        assert _account_run(c, 1, run1)["billed_kwh"] == 200


def test_offset_exceeding_gross_shows_zero_everywhere(fresh_db):
    with TestClient(app) as c:
        c.post(
            "/api/solar-offsets",
            json={"account_id": 1, "billing_period": "2026-08", "offset_kwh": 500},
        )
        saved = c.post(
            "/api/solar-offsets/runs",
            json={"account_id": 1, "billing_period": "2026-08", "gross_kwh": 400, "peak": False},
        ).json()
        assert saved["offset_clipped"] is True
        run_id = saved["run_id"]
        assert _history_kwh(c, run_id)["meter_kwh"] == 0.0
        assert _account_run(c, 1, run_id)["billed_kwh"] == 0.0
        assert _history_kwh(c, run_id)["total"] == 0.0


def test_run_without_offset_shows_gross_kwh_everywhere(fresh_db):
    with TestClient(app) as c:
        preview = c.post(
            "/api/solar-offsets/preview",
            json={"account_id": 1, "billing_period": "2030-01", "gross_kwh": 120, "peak": False},
        ).json()
        assert preview["offset_kwh"] == 0
        run_id = c.post(
            "/api/solar-offsets/runs",
            json={"account_id": 1, "billing_period": "2030-01", "gross_kwh": 120, "peak": False},
        ).json()["run_id"]
        # 无抵扣：两处电量与测算台电量相同
        assert _history_kwh(c, run_id)["meter_kwh"] == preview["net_kwh"] == 120
        assert _account_run(c, 1, run_id)["billed_kwh"] == preview["net_kwh"] == 120
        assert _history_kwh(c, run_id)["total"] == preview["total"]
