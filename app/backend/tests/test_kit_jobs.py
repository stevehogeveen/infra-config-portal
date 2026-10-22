from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx

from app.models import DeviceInventory, GuardedOperation


def op(**change):
    values = dict(profile_id="kit", device_id="srv", resource="windows-deploy", idempotency_key="k", intent_hash="h",
                  status="wd-sent-import", active_device="srv", created_at=datetime.now(UTC) - timedelta(minutes=12),
                  updated_at=datetime.now(UTC))
    values.update(change)
    return GuardedOperation(**values)


def test_jobs_split_running_attention_and_recent(client, db_session):
    db_session.add(DeviceInventory(id="srv", device_type="ilo", display_name="HPE DL360 1"))
    db_session.add(DeviceInventory(id="sw", device_type="cisco_switch", display_name="Cisco switch 1"))
    db_session.add(op())
    db_session.add(op(device_id="sw", resource="switch-setup", idempotency_key="k2", status="sw-uncertain-configure", active_device="sw"))
    db_session.add(op(resource="esxi-install", idempotency_key="k3", status="verified", active_device=None))
    db_session.add(op(resource="parts-update", idempotency_key="k4", status="verified", active_device=None,
                      updated_at=datetime.now(UTC) - timedelta(days=5)))
    db_session.commit()
    body = client.get("/api/v1/jobs").json()
    assert [(job["label"], job["device_name"]) for job in body["running"]] == [("Windows deploy", "HPE DL360 1")]
    assert body["running"][0]["path"] == "/setup/install-windows?device=srv"
    assert [job["label"] for job in body["attention"]] == ["Switch setup"]
    assert [(job["label"], job["state"]) for job in body["recent"]] == [("ESXi install", "done")]


class FakeIlo:
    def __init__(self):
        self.patches = []
        self.led = "Off"

    def handler(self, request: httpx.Request):
        if request.method == "PATCH":
            self.patches.append(request.content)
            self.led = "Blinking" if b"Blinking" in request.content else "Off"
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"IndicatorLED": self.led, "SerialNumber": "FIXTURE01", "Model": "ProLiant DL360 Gen10"}, headers={"ETag": "W/\"1\""})


def test_identify_blinks_the_light_and_records_it(client, db_session, monkeypatch):
    from app.api import kit_jobs
    from app.services import ilo_access_settings

    db_session.add(DeviceInventory(id="srv", device_type="ilo", display_name="HPE DL360 1"))
    db_session.commit()
    ilo_access_settings.update_ilo_access_settings(db_session, "srv", {"host": "192.0.2.10", "username": "admin", "password": "Fixture-Pass-1"})
    fake = FakeIlo()
    real_client = httpx.Client
    monkeypatch.setattr(kit_jobs.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(fake.handler)))
    import app.core.config as config
    monkeypatch.setattr(config, "settings", replace(config.settings, provider_mode="local-lab-readwrite"))
    monkeypatch.setattr("app.providers.action_policy.current_lab_action_policy", lambda mode=None: type("P", (), {"readonly_allowed": True, "local_lab_acknowledged": True})())
    body = client.post("/api/v1/devices/srv/identify", json={"on": True}).json()
    assert body == {"indicator": "Blinking", "serial": "FIXTURE01", "model": "ProLiant DL360 Gen10"}
    assert len(fake.patches) == 1
    history = client.get("/api/v1/build-history").json()
    assert history and "ID light turned on" in history[0]["message"]


def test_health_summary_reads_temps_fans_and_psus():
    from app.api.kit_jobs import health_summary

    probe = {"status": "ok", "checked_at": "2026-10-15T12:00:00+00:00",
             "systems": [{"Status": {"HealthRollup": "OK"}}],
             "thermal": [{"Temperatures": [{"Name": "01-Inlet Ambient", "PhysicalContext": "Intake", "ReadingCelsius": 21, "UpperThresholdCritical": 42},
                                           {"Name": "02-CPU 1", "ReadingCelsius": 40, "UpperThresholdCritical": 70},
                                           {"Name": "03-P1 DIMM", "ReadingCelsius": 0}],
                          "Fans": [{"Name": "Fan 1", "Status": {"State": "Enabled", "Health": "OK"}},
                                   {"Name": "Fan 2", "Status": {"State": "Enabled", "Health": "Critical"}},
                                   {"Name": "Fan 7", "Status": {"State": "Absent"}}]}],
             "power": [{"PowerSupplies": [{"MemberId": "0", "Location": "1", "Status": {"State": "Enabled", "Health": "OK"}},
                                          {"MemberId": "1", "Location": "2", "Status": {"State": "Absent"}}]}]}
    summary = health_summary(probe)
    assert summary["inlet_c"] == 21 and summary["hottest"] == {"name": "02-CPU 1", "c": 40}
    assert (summary["fans_ok"], summary["fans"], summary["psu_ok"], summary["psus"]) == (1, 2, 1, 1)
    assert summary["problems"] == ["Fan 2 is not OK"]
    assert health_summary({"status": "blocked"}) is None


def test_the_id_light_is_refused_in_read_only_mode(client, db_session, monkeypatch):
    from app.services import ilo_access_settings

    db_session.add(DeviceInventory(id="srv", device_type="ilo", display_name="HPE DL360 1"))
    db_session.commit()
    ilo_access_settings.update_ilo_access_settings(db_session, "srv", {"host": "192.0.2.10", "username": "admin", "password": "Fixture-Pass-1"})
    import app.core.config as config
    monkeypatch.setattr(config, "settings", replace(config.settings, provider_mode="local-readonly"))
    response = client.post("/api/v1/devices/srv/identify", json={"on": True})
    assert response.status_code == 409 and "read-write" in response.json()["detail"]


def test_unverified_is_never_done(client, db_session):
    db_session.add(op(resource="esxi-install", status="unverified", active_device=None))
    db_session.commit()
    assert client.get("/api/v1/jobs").json()["recent"][0]["state"] == "stopped"
