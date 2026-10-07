import pytest
from app.services.rack_identity import save_detected_generation


@pytest.mark.parametrize("family,generation", [("DL360","Gen10"),("DL380","Gen11"),("DL360","Gen10 Plus")])
def test_resolves_generation_and_preserves_layout(client, db_session, monkeypatch, family, generation):
    monkeypatch.setattr("app.services.rack_identity.read_ilo_access_settings", lambda *a: {"last_probe_is_current":True,"last_probe_target_matches_access_host":True})
    url = "/api/v1/rack-plans/identity-kit"
    saved = client.put(url,json={"equipment":[{"id":"server","name":"My custom server","kind":"server","model":"HPE " + family,"position":2,"height":1 if family=="DL360" else 2}]}).json()
    device = saved["equipment"][0]["device_id"]
    save_detected_generation(db_session,device,{"status":"ok","systems":[{"Model":f"ProLiant {family} {generation}"}]})
    updated = client.get(url).json()
    assert updated["equipment"][0] == {**saved["equipment"][0],"model":f"HPE {family} {generation}"}
    assert updated["revision"] == saved["revision"] + 1
    assert client.put(url,json=saved).status_code == 409
    save_detected_generation(db_session,device,{"status":"ok","systems":[{"Model":f"ProLiant {family} {generation}"}]})
    assert client.get(url).json() == updated


@pytest.mark.parametrize("status,model,current", [("blocked","ProLiant DL360 Gen10",True),("ok","ProLiant DL380 Gen11",True),("ok","ProLiant DL360 Gen10",False),("ok","unknown",True)])
def test_unverified_or_different_family_does_not_change_plan(client,db_session,monkeypatch,status,model,current):
    monkeypatch.setattr("app.services.rack_identity.read_ilo_access_settings", lambda *a: {"last_probe_is_current":current,"last_probe_target_matches_access_host":current})
    url = "/api/v1/rack-plans/identity-kit"
    saved = client.put(url,json={"equipment":[{"id":"s","name":"Server","kind":"server","model":"HPE DL360","position":1,"height":1}]}).json()
    save_detected_generation(db_session,saved["equipment"][0]["device_id"],{"status":status,"systems":[{"Model":model}]})
    assert client.get(url).json() == saved
