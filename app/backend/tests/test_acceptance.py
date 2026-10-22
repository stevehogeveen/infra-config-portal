import json
from contextlib import nullcontext
from datetime import timedelta

import pytest

from app.providers import esxi_govc as govc
from app.services import acceptance as service

TARGET = {"esxi": "192.0.2.20", "password": "Fixture-Pass-1", "vm": "win01", "gateway": "192.0.2.1", "default_name": "esx01.lab.test"}
PROFILE, DEVICE = "kit-a", "dev-1"
GUEST_PASSWORD = "Guest-Fixture-9"
NSLOOKUP = "Server:  dns.lab.test\nAddress:  192.0.2.53\n\nName:    esx01.lab.test\nAddress:  192.0.2.20\n"


class FakeVm:
    def __init__(self):
        self.vm = {"power": "poweredOn", "tools": "guestToolsRunning", "ip": "192.0.2.77"}
        self.sent, self.runs = [], []
        self.gateway_reply = "Reply from 192.0.2.1: bytes=32 time<1ms TTL=255"
        self.refuse_signin = False
        self.boot = "2026-10-15T08:00:00.0000000Z"

    def vm_info(self, ip, password, name):
        return dict(self.vm)

    def guest_run(self, ip, password, name, login, program, *args, timeout=120):
        self.runs.append((program, *args))
        if self.refuse_signin:
            raise govc.GovcError("Windows refused the saved administrator sign-in.")
        assert login == f"Administrator:{GUEST_PASSWORD}"
        return {"ping": (0, self.gateway_reply), "nslookup": (0, NSLOOKUP), "hostname": (0, "WIN01\n"),
                "powershell": (0, f"{self.boot}\n")}[program]

    def guest_reboot(self, ip, password, name):
        self.sent.append(("reboot", name))
        self.vm.update(tools="guestToolsNotRunning", ip=None)
        self.boot = "2026-10-15T12:30:00.0000000Z"


@pytest.fixture
def lab(monkeypatch, tmp_path):
    fake = FakeVm()
    for name in ("vm_info", "guest_run", "guest_reboot"):
        monkeypatch.setattr(govc, name, getattr(fake, name))
    monkeypatch.setattr(service, "_root", lambda: tmp_path / "windows")
    monkeypatch.setattr(service, "_target", lambda session, profile_id, device_id: dict(TARGET))
    monkeypatch.setattr(service, "_policy_blockers", lambda: [])
    monkeypatch.setattr("app.services.runtime_write_scope.dispatch_lease", lambda action: nullcontext())
    service.save_signin(DEVICE, "Administrator", GUEST_PASSWORD)
    return fake


def step(db_session, times=1, ping=lambda address: True):
    for _ in range(times):
        result = service.advance(db_session, PROFILE, DEVICE, "tester", ping=ping)
    return result


def later(monkeypatch, minutes):
    monkeypatch.setattr(service, "_now", lambda: service.datetime.now(service.UTC) + timedelta(minutes=minutes))


def test_the_signin_is_kept_private_and_never_returned(lab, tmp_path):
    status = service.signin_status(DEVICE)
    assert status == {"username": "Administrator", "password_saved": True}
    assert GUEST_PASSWORD not in json.dumps(status)
    with pytest.raises(service.AcceptanceError):
        service.save_signin(DEVICE, "bad name;", "x")


def test_passes_outside_inside_restart_and_back(db_session, lab, monkeypatch):
    service.start(db_session, PROFILE, DEVICE, "tester")
    status = step(db_session, 2)
    assert [p["state"] for p in status["phases"]] == ["ok", "ok", "running", "todo"]
    assert ("ping", "-n", "2", "192.0.2.1") in lab.runs and ("nslookup", "esx01.lab.test") in lab.runs
    step(db_session)  # restart sent
    assert lab.sent == [("reboot", "win01")]
    lab.vm.update(tools="guestToolsRunning", ip="192.0.2.77")
    later(monkeypatch, 2)
    status = step(db_session, 3)
    assert lab.sent == [("reboot", "win01")]
    assert status["state"] == "verified" and not status["active"]
    assert all(p["state"] == "ok" for p in status["phases"])


def test_a_gateway_that_does_not_reply_fails_even_when_ping_exits_zero(db_session, lab):
    lab.gateway_reply = "Reply from 192.0.2.77: Destination host unreachable."
    service.start(db_session, PROFILE, DEVICE, "tester")
    status = step(db_session, 2)
    assert status["state"] == "needs_attention"
    assert lab.sent == []
    assert service.close(db_session, PROFILE, DEVICE, "tester")["state"] == "failed"


def test_a_refused_signin_fails_inside_and_nothing_is_restarted(db_session, lab):
    lab.refuse_signin = True
    service.start(db_session, PROFILE, DEVICE, "tester")
    status = step(db_session, 4)
    assert status["state"] == "needs_attention" and "refused" in status["message"]
    assert lab.sent == []


def test_the_restart_is_sent_once_and_a_vm_that_never_returns_is_uncertain(db_session, lab, monkeypatch):
    service.start(db_session, PROFILE, DEVICE, "tester")
    step(db_session, 3)
    later(monkeypatch, 5)
    step(db_session, 3)
    assert lab.sent == [("reboot", "win01")]
    later(monkeypatch, 20)
    status = step(db_session)
    assert status["state"] == "needs_attention" and "Nothing was sent again" in status["message"]
    assert lab.sent == [("reboot", "win01")]


def test_a_lost_restart_reply_is_read_back_not_resent(db_session, lab, monkeypatch):
    def lost(ip, password, name):
        lab.sent.append(("reboot", name))
        lab.boot = "2026-10-15T12:30:00.0000000Z"
        raise govc.GovcError("connection reset")

    monkeypatch.setattr(govc, "guest_reboot", lost)
    service.start(db_session, PROFILE, DEVICE, "tester")
    step(db_session, 3)
    later(monkeypatch, 2)
    status = step(db_session, 3)
    assert lab.sent == [("reboot", "win01")]
    assert status["state"] == "verified"


def test_the_restart_is_not_sent_when_write_permission_was_withdrawn(db_session, lab, monkeypatch):
    service.start(db_session, PROFILE, DEVICE, "tester")
    step(db_session, 2)
    monkeypatch.setattr(service, "_policy_blockers", lambda: ["The app is read-only."])
    status = step(db_session)
    assert lab.sent == [] and status["state"] == "needs_attention"


def test_start_needs_the_signin_and_permission(db_session, lab, monkeypatch, tmp_path):
    monkeypatch.setattr(service, "_policy_blockers", lambda: ["The app is read-only."])
    with pytest.raises(service.AcceptanceError, match="read-only"):
        service.start(db_session, PROFILE, DEVICE, "tester")
    monkeypatch.setattr(service, "_policy_blockers", lambda: [])
    service._signin_path(DEVICE).unlink()
    with pytest.raises(service.AcceptanceError, match="sign-in"):
        service.start(db_session, PROFILE, DEVICE, "tester")


def test_an_unreachable_vm_fails_the_outside_check(db_session, lab):
    service.start(db_session, PROFILE, DEVICE, "tester")
    status = step(db_session, ping=lambda address: False)
    assert status["state"] == "needs_attention"
    assert status["phases"][0]["state"] == "failed"


def test_a_restart_that_never_happened_is_not_a_pass(db_session, lab, monkeypatch):
    def ignored(ip, password, name):
        lab.sent.append(("reboot", name))  # accepted, but Windows never restarts

    monkeypatch.setattr(govc, "guest_reboot", ignored)
    service.start(db_session, PROFILE, DEVICE, "tester")
    step(db_session, 3)
    later(monkeypatch, 5)
    assert step(db_session, 2)["phases"][2]["state"] == "running"
    later(monkeypatch, 20)
    status = step(db_session)
    assert status["state"] == "needs_attention" and "never restarted" in status["message"]
    assert lab.sent == [("reboot", "win01")]


def test_a_changed_vm_stops_the_run_before_any_restart(db_session, lab, monkeypatch):
    service.start(db_session, PROFILE, DEVICE, "tester")
    step(db_session, 2)
    monkeypatch.setattr(service, "_target", lambda session, profile_id, device_id: {**TARGET, "vm": "win02"})
    status = step(db_session)
    assert status["state"] == "needs_attention" and "changed" in status["message"]
    assert lab.sent == []


def test_a_password_rejected_by_validation_is_not_echoed(client):
    response = client.put("/api/v1/rack-plans/kit-a/windows/guest-signin?device_id=x", json={"username": "Administrator", "password": "S3cret-" + "x" * 200})
    assert response.status_code == 422
    assert "S3cret-" not in response.text
