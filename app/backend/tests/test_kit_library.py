from app.models import DeviceInventory, IloDeviceCredential
from app.services.audit import record_audit_event


def make_kit(client):
    response = client.post("/api/v1/lab/profiles", json={"name": "Kit Alpha", "profile_topology": "custom", "subnet_cidr": "192.0.2.0/24"})
    assert response.status_code == 201, response.text
    kit = response.json()
    response = client.put(f"/api/v1/rack-plans/{kit['id']}", json={"rack_units": 12, "equipment": [
        {"id": "server", "name": "Server Alpha", "kind": "server", "model": "HPE DL360 Gen11", "height": 1, "position": 2, "bay_count": 10, "occupied_bays": [1, 2]},
    ]})
    assert response.status_code == 200, response.text
    return kit, response.json()


def test_save_as_isolated_and_original_unchanged(client, db_session):
    original, rack = make_kit(client)
    source_id = rack["equipment"][0]["device_id"]
    db_session.get(DeviceInventory, source_id).host = "192.0.2.10"
    db_session.add(IloDeviceCredential(device_id=source_id, credentials_json={"password": "fixture-only-secret"}))
    db_session.commit()
    response = client.post(f"/api/v1/rack-plans/{original['id']}/save-as", json={"name": "Kit Beta"})
    assert response.status_code == 201, response.text
    copied = response.json()
    assert copied["id"] != original["id"]
    assert copied["history"] == []
    assert copied["address_plan"]["ilo"] is None
    copied_rack = client.get(f"/api/v1/rack-plans/{copied['id']}").json()
    target = copied_rack["equipment"][0]
    assert target["device_id"] != source_id
    assert target["occupied_bays"] == [1, 2]
    assert db_session.get(IloDeviceCredential, target["device_id"]) is None
    assert db_session.get(DeviceInventory, target["device_id"]).host is None
    assert client.get("/api/v1/lab/profiles").json()["active_profile"]["id"] == original["id"]
    assert client.get(f"/api/v1/rack-plans/{original['id']}").json() == rack
    assert client.get(f"/api/v1/rack-plans/{copied['id']}/reports").json() == []


def test_reports_persist_scope_and_omit_payloads(client, db_session):
    kit, rack = make_kit(client)
    record_audit_event(db_session, actor="fixture", event_type="fixture.checked", message="fixture-secret-message",
                       data={"device_id": rack["equipment"][0]["device_id"], "password": "fixture-only-secret"}, to_status="blocked")
    record_audit_event(db_session, actor="fixture", event_type="other-kit.event", message="other",
                       data={"profile_id": "other-kit"})
    db_session.commit()
    url = f"/api/v1/rack-plans/{kit['id']}/reports"
    response = client.post(url)
    assert response.status_code == 201, response.text
    report = response.json()
    assert "fixture-only-secret" not in response.text
    assert "fixture-secret-message" not in response.text
    assert "other-kit.event" not in response.text
    assert any(e["to_status"] == "blocked" for e in report["activity"])
    assert client.patch(f"/api/v1/rack-plans/{kit['id']}/name", json={"name": "Renamed kit"}).status_code == 200
    assert client.get(url).json()[0] == report
    assert client.get(url).json()[0]["name"] == "Kit Alpha"


def test_invalid_names_and_missing_kits(client):
    assert client.post("/api/v1/rack-plans/missing/save-as", json={"name": "Valid name"}).status_code == 404
    assert client.post("/api/v1/rack-plans/runtime/save-as", json={"name": "   "}).status_code == 422
    assert client.get("/api/v1/rack-plans/missing/reports").status_code == 404


def test_failed_copy_does_not_leave_profile(client, monkeypatch):
    import pytest
    from app.api import rack_plans
    kit, _ = make_kit(client)
    before = client.get("/api/v1/lab/profiles").json()["profiles"]
    def fail(*args):
        raise RuntimeError("fixture database unavailable")
    monkeypatch.setattr(rack_plans, "save_plan", fail)
    with pytest.raises(RuntimeError, match="fixture database unavailable"):
        client.post(f"/api/v1/rack-plans/{kit['id']}/save-as", json={"name": "Failed copy"})
    assert client.get("/api/v1/lab/profiles").json()["profiles"] == before
