from app.services import ask_lab, trace
from app.services.audit import record_audit_event


def add(session, event_type, message, **data):
    record_audit_event(session, actor="op", event_type=event_type, message=message, data=data)
    session.commit()


def test_terms_pick_out_vlans_addresses_and_words():
    found = ask_lab.terms("Why is VLAN 100 on 192.0.2.50 here?")
    assert [t["label"] for t in found] == ["VLAN 100", "192.0.2.50"]
    assert not ask_lab.terms("why is it here?")


def test_ask_answers_from_plan_change_and_check_records(db_session, monkeypatch):
    monkeypatch.setattr(ask_lab, "_settings_sources", lambda session: [])
    add(db_session, "kit.switch.run", "Switch first setup approved.", vlan=100, hostname="lab-sw01", password="Fixture-Pass-1")
    add(db_session, "kit.switch.attempt", "Switch setup over the console starting; outcome unverified.", vlan=100)
    add(db_session, "kit.switch.result", "lab-sw01 is set up at 192.0.2.50.", phase="configure", outcome="ok", vlan=100)
    add(db_session, "kit.switch.result", "Unrelated VLAN 1000 note.", outcome="ok")
    answer = ask_lab.ask(db_session, "why is VLAN 100 here?")
    assert answer["terms"] == ["VLAN 100"]
    assert len(answer["plan"]) == 1 and len(answer["changes"]) == 1 and len(answer["checks"]) == 1
    assert answer["summary"].startswith("VLAN 100: planned in switch")
    assert "Fixture-Pass-1" not in str(answer)


def test_a_password_is_never_searchable(db_session, monkeypatch):
    monkeypatch.setattr(ask_lab, "_settings_sources", lambda session: [])
    add(db_session, "kit.switch.run", "Switch first setup approved.", password="Hunter22secret")
    assert ask_lab.ask(db_session, "Hunter22secret")["summary"].startswith("Nothing in the app's records")


def test_nothing_found_says_so(db_session, monkeypatch):
    monkeypatch.setattr(ask_lab, "_settings_sources", lambda session: [])
    assert ask_lab.ask(db_session, "VLAN 4000")["summary"] == "Nothing in the app's records mentions VLAN 4000."


def _stub(monkeypatch, *, windows="verified", cable=True, gateway_ok=True, switch_ok=True):
    from app.services import acceptance, esxi_install, switch_access, windows_deploy

    monkeypatch.setattr(windows_deploy, "status", lambda s, p, d: {"state": windows, "vm_name": "windows01", "address": "192.0.2.77", "network": "VM Network",
                                                                     "started_at": "2026-10-15T09:00:00+00:00"})
    monkeypatch.setattr(esxi_install, "install_status", lambda s, p, d: {"state": "verified", "management_ip": "192.0.2.20", "verified_at": "2026-10-15T10:00:00+00:00"})
    monkeypatch.setattr(esxi_install, "get_settings", lambda s, p, d: {"hostname": "esx01", "management_nic": "vmnic0", "kit": {"gateway": "192.0.2.1"}})
    checks = [{"name": "Windows reaches the gateway 192.0.2.1", "ok": gateway_ok}]
    monkeypatch.setattr(acceptance, "status", lambda s, p, d: {"phases": [{"checks": checks}], "vm": "windows01", "started_at": "2026-10-15T11:50:00+00:00",
                                                                "finished_at": "2026-10-15T12:00:00+00:00"})
    monkeypatch.setattr(switch_access, "read_access", lambda s, d: {"last_check": {"status": "ok" if switch_ok else "unreachable", "checked_at": "2026-10-15T11:00:00+00:00"}})
    cables = {"checked_at": "2026-10-15T11:30:00+00:00", "cables": [{"server_id": "srv", "server": "DL360", "server_port": "vmnic0 (Embedded LOM 1 port 1)", "mac": "aa:bb:cc:dd:ee:01",
                                                                     "switch_id": "sw", "switch": "lab-sw01", "switch_port": "Gi1/0/1", "vlan": "100"}] if cable else []}
    return cables


def test_a_fully_proven_path_has_no_stop(db_session, monkeypatch):
    cables = _stub(monkeypatch)
    path = trace.server_path(db_session, "kit", "srv", "DL360", cables, {"sw": "lab-sw01"})
    assert [h["name"] for h in path["hops"]] == ["Windows VM", "VM network", "ESXi host", "Server port", "Cable", "Switch port", "Gateway"]
    assert path["stops_at"] is None and all(h["state"] == "proven" for h in path["hops"])


def test_evidence_stops_at_the_unread_cable(db_session, monkeypatch):
    cables = _stub(monkeypatch, cable=False, gateway_ok=False)
    path = trace.server_path(db_session, "kit", "srv", "DL360", cables, {})
    stop = path["hops"][path["stops_at"]]
    assert stop["name"] == "VM network" and stop["prove"]
    assert next(h for h in path["hops"] if h["name"] == "Cable")["state"] == "unknown"


def test_an_old_acceptance_test_does_not_prove_a_new_deployment(db_session, monkeypatch):
    from app.services import windows_deploy

    cables = _stub(monkeypatch)
    monkeypatch.setattr(windows_deploy, "status", lambda s, p, d: {"state": "verified", "vm_name": "windows01", "address": "192.0.2.77",
                                                                     "network": "VM Network", "started_at": "2026-10-15T13:00:00+00:00"})
    path = trace.server_path(db_session, "kit", "srv", "DL360", cables, {})
    assert path["hops"][path["stops_at"]]["name"] == "VM network"


def test_free_text_secrets_are_hidden_and_addresses_match_whole(db_session, monkeypatch):
    monkeypatch.setattr(ask_lab, "_settings_sources", lambda session: [])
    add(db_session, "kit.switch.result", "Set up at 192.0.2.5 password=Hunter22secret", outcome="ok", detail="token: abc123")
    add(db_session, "kit.switch.result", "Other device at 10.192.0.2.5x", outcome="ok")
    answer = ask_lab.ask(db_session, "192.0.2.5")
    assert len(answer["checks"]) == 1
    assert "Hunter22secret" not in str(answer) and "[hidden]" in answer["checks"][0]["message"]
    assert not ask_lab.ask(db_session, "abc123")["checks"]


def test_a_firmware_review_with_a_silent_ilo_says_so(client, monkeypatch):
    import httpx

    from app.services import parts_update

    def silent(*args):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(parts_update, "review", silent)
    monkeypatch.setattr("app.api.parts_update.server_in_kit", lambda *a: None)
    response = client.post("/api/v1/rack-plans/kit/parts-update/review?device_id=srv")
    assert response.status_code == 409 and "iLO did not answer" in response.json()["detail"]
