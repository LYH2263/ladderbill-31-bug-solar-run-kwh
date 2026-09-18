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
