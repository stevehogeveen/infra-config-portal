from app.services.audit import record_audit_event


def test_recipe_round_trip_copies_design_not_secrets_or_identities(client, db_session):
    kit = client.post("/api/v1/lab/profiles", json={"name": "Source kit", "profile_topology": "custom", "subnet_cidr": "192.0.2.0/24", "gateway": "192.0.2.1"}).json()
    response = client.put(f"/api/v1/rack-plans/{kit['id']}", json={"equipment": [
        {"id": "s", "name": "HPE DL360 1", "kind": "server", "model": "HPE DL360 Gen10", "position": 1, "height": 1, "bay_count": 10},
        {"id": "w", "name": "Cisco switch 1", "kind": "switch", "model": "Catalyst 9300", "position": 3, "height": 1, "ports": 24}]})
    assert response.status_code == 200, response.text
    plan = response.json()
    server = next(item for item in plan["equipment"] if item["kind"] == "server")
    record_audit_event(db_session, actor="op", event_type="kit.esxi_settings_saved", message="saved",
                       data={"profile_id": kit["id"], "device_id": server["device_id"], "hostname": "esxi01.lab.example", "addressing": "static",
                             "management_ip": "192.0.2.20", "vlan_id": 0, "datastore_name": "VMdata", "password_changed": True})
    record_audit_event(db_session, actor="op", event_type="kit.windows.settings", message="saved",
                       data={"profile_id": kit["id"], "device_id": server["device_id"], "image": "win.ova", "vm_name": "windows01", "datastore": "VMdata", "network": "VM Network"})
    db_session.commit()
    recipe = client.get(f"/api/v1/rack-plans/{kit['id']}/recipe").json()
    assert recipe["format"] == "lab-builder-recipe/1" and recipe["servers"][0]["windows"]["vm_name"] == "windows01"
    assert "device_id" not in str(recipe["rack"]) and "password" not in str(recipe).lower()
    applied = client.post("/api/v1/recipes/apply", json={"name": "Copy kit", "recipe": recipe}).json()
    new_id = applied["kit"]["id"]
    assert new_id != kit["id"] and any("password" in item for item in applied["todo"])
    new_plan = client.get(f"/api/v1/rack-plans/{new_id}").json()
    new_server = next(item for item in new_plan["equipment"] if item["kind"] == "server")
    assert new_server["device_id"] and new_server["device_id"] != server["device_id"]
    from app.services import esxi_install
    saved = esxi_install._latest(db_session, "kit.esxi_settings_saved", profile_id=new_id, device_id=new_server["device_id"]).data_json
    assert saved["hostname"] is None and saved["management_ip"] is None and saved["datastore_name"] == "VMdata"
    assert "esxi01" not in str(recipe) and "192.0.2.20" not in str(recipe)


def test_a_non_recipe_file_is_refused(client):
    assert client.post("/api/v1/recipes/apply", json={"name": "x", "recipe": {"hello": 1}}).status_code == 422


def test_a_crafted_recipe_cannot_redirect_settings(client, db_session):
    from app.models import AuditEvent
    from sqlalchemy import select

    recipe = {"format": "lab-builder-recipe/1", "network": {"subnet_cidr": "192.0.2.0/24"},
              "rack": {"rack_units": 4, "equipment": [{"kind": "server", "name": "HPE DL360 1", "model": "HPE DL360 Gen10", "position": 1, "height": 1, "bay_count": 10}]},
              "servers": [{"windows": {"image": "win.ova", "vm_name": "w", "datastore": "d", "network": "n", "profile_id": "victim", "device_id": "victim-device"}}]}
    applied = client.post("/api/v1/recipes/apply", json={"name": "Crafted", "recipe": recipe}).json()
    rows = db_session.scalars(select(AuditEvent).where(AuditEvent.event_type == "kit.windows.settings")).all()
    assert rows and all(row.data_json["profile_id"] == applied["kit"]["id"] and row.data_json["device_id"] != "victim-device" for row in rows)
