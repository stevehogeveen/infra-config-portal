from copy import deepcopy

import pytest
from sqlalchemy import select
from app.models import DeviceInventory, RackLayoutPlan


def plan():
    return {"revision": 0, "rack_units": 12, "equipment": [
        {"id": "server", "name": "Server", "kind": "server", "model": "HPE Gen11",
         "position": 3, "height": 2, "bay_count": 10, "occupied_bays": [1, 2, 10]},
        {"id": "switch", "name": "Switch", "kind": "switch", "position": 6, "height": 1, "ports": 48},
    ]}


def test_persistence_revision_and_profile_isolation(client):
    assert client.get("/api/v1/rack-plans/kit-a").json()["equipment"] == []
    response = client.put("/api/v1/rack-plans/kit-a", json=plan())
    assert response.status_code == 200
    saved = response.json()
    assert saved["revision"] == 1
    assert saved["equipment"][0]["occupied_bays"] == [1, 2, 10]
    assert client.get("/api/v1/rack-plans/kit-a").json() == saved
    assert client.get("/api/v1/rack-plans/kit-b").json()["equipment"] == []
    assert client.put("/api/v1/rack-plans/kit-a", json=plan()).status_code == 409
    saved["equipment"][1]["ports"] = 24
    assert client.put("/api/v1/rack-plans/kit-a", json=saved).json()["revision"] == 2
    assert client.put("/api/v1/rack-plans/kit-a", json=saved).status_code == 409


@pytest.mark.parametrize("field,value", [("position", 12), ("position", 0), ("bay_count", 8),
    ("occupied_bays", [1, 1]), ("occupied_bays", [0]), ("mount", "left")])
def test_invalid_equipment_rejected(client, field, value):
    body = deepcopy(plan())
    body["equipment"][0][field] = value
    assert client.put("/api/v1/rack-plans/kit", json=body).status_code == 422


def test_overlap_and_side_pdu(client):
    body = plan()
    body["equipment"][1]["position"] = 3
    assert client.put("/api/v1/rack-plans/kit", json=body).status_code == 422
    body["equipment"][1] = {"id": "pdu", "name": "PDU", "kind": "pdu", "position": 1, "height": 12, "mount": "right"}
    assert client.put("/api/v1/rack-plans/kit", json=body).status_code == 200


def test_hardware_created_once_and_retained_when_removed(client, db_session):
    saved = client.put("/api/v1/rack-plans/new-kit", json=plan()).json()
    server_id = saved["equipment"][0]["device_id"]
    switch_id = saved["equipment"][1]["device_id"]
    assert db_session.get(DeviceInventory, server_id).device_type == "ilo"
    assert db_session.get(DeviceInventory, switch_id).device_type == "cisco_switch"
    count = len(list(db_session.scalars(select(DeviceInventory))))
    updated = client.put("/api/v1/rack-plans/new-kit", json=saved).json()
    assert updated["equipment"][0]["device_id"] == server_id
    assert len(list(db_session.scalars(select(DeviceInventory)))) == count
    updated["equipment"] = []
    assert client.put("/api/v1/rack-plans/new-kit", json=updated).status_code == 200
    assert db_session.get(DeviceInventory, server_id) is not None


def test_missing_link_rejected_without_creating_hardware(client):
    body = plan()
    body["equipment"][0]["device_id"] = "missing"
    assert client.put("/api/v1/rack-plans/kit", json=body).status_code == 409
    assert client.get("/api/v1/rack-plans/kit").json()["revision"] == 0


@pytest.mark.parametrize("model,height,bays", [
    ("HPE DL360 Gen11", 1, 10), ("HPE DL360 Gen10 Plus", 1, 8),
    ("HPE DL380 Gen11", 2, 24), ("HPE DL380 Gen10 Plus", 2, 16),
])
def test_server_presets_persist(client, model, height, bays):
    body = plan()
    body["equipment"][0].update(model=model, height=height, bay_count=bays, occupied_bays=[1, bays])
    response = client.put("/api/v1/rack-plans/models", json=body)
    assert response.status_code == 200
    loaded = client.get("/api/v1/rack-plans/models").json()["equipment"][0]
    assert (loaded["model"], loaded["height"], loaded["bay_count"]) == (model, height, bays)
    assert loaded["occupied_bays"] == [1, bays]


@pytest.mark.parametrize("model,height,bays", [
    ("HPE DL360 Gen11", 2, 10), ("HPE DL360 Gen10 Plus", 1, 11),
    ("HPE DL380 Gen11", 1, 24), ("HPE DL380 Gen10 Plus", 2, 25),
])
def test_server_model_limits_rejected_without_saving(client, model, height, bays):
    body = plan()
    body["equipment"][0].update(model=model, height=height, bay_count=bays)
    assert client.put("/api/v1/rack-plans/models", json=body).status_code == 422
    assert client.get("/api/v1/rack-plans/models").json()["revision"] == 0


def test_storage_drive_occupancy_and_sfp_module_persist(client, db_session):
    body = plan()
    body["equipment"][0].update(kind="storage", model="NetApp 24 SFF", bay_count=24,
                                  occupied_bays=list(range(1, 25)))
    body["equipment"][1].update(ports=24, uplink_ports=4)
    response = client.put("/api/v1/rack-plans/storage", json=body)
    assert response.status_code == 200
    saved = response.json()
    assert db_session.get(DeviceInventory, saved["equipment"][0]["device_id"]).device_type == "netapp"
    assert client.get("/api/v1/rack-plans/storage").json() == saved
    saved["equipment"][0]["occupied_bays"].remove(24)
    saved["equipment"][1].update(ports=48, uplink_ports=0)
    assert client.put("/api/v1/rack-plans/storage", json=saved).status_code == 200
    loaded = client.get("/api/v1/rack-plans/storage").json()
    assert loaded["equipment"][0]["occupied_bays"] == list(range(1, 24))
    assert loaded["equipment"][1]["uplink_ports"] == 0
    assert loaded["equipment"][1]["ports"] == 48


@pytest.mark.parametrize("kind", ["server", "ups", "pdu", "storage"])
def test_sfp_module_only_belongs_to_switches(client, kind):
    body = {"equipment": [{"id": "item", "name": "Item", "kind": kind,
                           "position": 1, "height": 1, "uplink_ports": 4}]}
    assert client.put("/api/v1/rack-plans/sfp", json=body).status_code == 422


def test_legacy_model_layout_remains_readable(client, db_session):
    body = plan()
    body.pop("revision")
    body["equipment"][0]["model"] = "HPE DL360 Gen11"
    db_session.add(RackLayoutPlan(profile_id="legacy", revision=1, layout_json=body))
    db_session.commit()
    response = client.get("/api/v1/rack-plans/legacy")
    assert response.status_code == 200
    assert response.json()["equipment"][0]["height"] == 2
    assert response.json()["equipment"][1]["uplink_ports"] == 0
