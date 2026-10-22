"""Kit Pilot tests against a fake Lab Builder (an http.server in a thread). Nothing real is contacted."""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pilot as pilot_module  # noqa: E402
from engine import Api, Engine, NeedsYou, Paused  # noqa: E402
from pilot import Pilot  # noqa: E402

P, S, W = "fixture", "srv", "sw"


class FakeLab:
    """Records every write; answers like Lab Builder for a kit where only ESXi and the test remain."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.scope = "read_only"
        self.esxi, self.esxi_checks = "not_started", 0
        self.test, self.test_ticks = "not_started", 0
        self.volumes = False
        self.image = "win2022.ova"
        self.revision = 1
        self.lock = threading.Lock()

    def handle(self, method: str, path: str, body: dict) -> tuple[int, object]:
        if method != "GET":
            self.sent.append(f"{method} {path}")
        path = path.split("?", 1)[0]
        kit = f"/api/v1/rack-plans/{P}/"
        if path == "/api/v1/lab/profiles":
            return 200, {"active_profile": {"id": P, "name": "Test kit"}}
        if path == f"/api/v1/rack-plans/{P}":
            return 200, {"revision": self.revision, "equipment": [{"kind": "server", "name": "HPE DL360 3", "device_id": S, "model": "DL360"}, {"kind": "switch", "name": "Cisco switch 1", "device_id": W, "model": "C9300"}]}
        if path == kit + "preflight":
            return 200, {"state": "ok", "items": [{"group": "Media", "name": "Windows image", "state": "ok", "detail": self.image, "fix": None}]}
        if path.startswith("/api/v1/providers/ilo-redfish/probe"):
            return 200, {"status": "ok", "message": "iLO answered."}
        if path == kit + "switch-setup/status":
            return 200, {"state": "verified", "active": False, "message": "ok"}
        if path == f"/api/v1/devices/{W}/switch-access/check":
            return 200, {"status": "ok", "message": "Switch answered."}
        if path == kit + "parts-update/status":
            return 200, {"state": "not_started", "active": False, "message": ""}
        if path == kit + "parts-update/review":
            return 200, {"review_id": "r1", "parts": [], "blockers": []}
        if path == kit + "firmware-update/status":
            return 200, {"status": "not_started", "active": False, "message": ""}
        if path == kit + "firmware-update/plan":
            return 200, {"updates": [], "can_apply": False, "review_token": None, "confirmation_phrase": None, "blockers": []}
        if path == kit + "raid-rebuild/status":
            return 200, ({"operation": None, "status": "not_started"} if self.volumes else {"operation": "create", "status": "verified"})
        if path == kit + "disk-preparation":
            return 200, {"blockers": [], "volumes": [{"name": "old"}]}
        if path == kit + "esxi/install" and method == "GET":
            return 200, self._esxi()
        if path == kit + "esxi/installer":
            return 200, {"status": "ready", "blockers": []}
        if path == kit + "esxi/install" and method == "POST":
            self.esxi = "installing"
            return 200, self._esxi()
        if path == kit + "esxi/install/check":
            self.esxi_checks += 1
            if self.esxi_checks >= 2:
                self.esxi = "verified"
            return 200, self._esxi()
        if path == kit + "windows/status":
            return 200, {"state": "verified", "active": False, "message": ""}
        if path == kit + "windows/acceptance":
            return 200, self._test()
        if path == kit + "windows/acceptance/start":
            self.test = "running"
            return 200, self._test()
        if path == kit + "windows/acceptance/advance":
            self.test_ticks += 1
            if self.test_ticks >= 2:
                self.test = "verified"
            return 200, self._test()
        if path == kit + "handover":
            return 200, {"kit": "Test kit", "network": {"subnet": "192.0.2.0/24", "gateway": "192.0.2.1", "dns": ["192.0.2.53"], "domain": "lab.test"},
                         "servers": [{"name": "HPE DL360 3", "model": "DL360", "ilo": {"address": "192.0.2.10"}, "esxi": {"state": "verified", "host_name": "esx01", "address": "192.0.2.20", "verified_at": "2026-10-16T11:00:00+00:00"},
                                      "windows": {"state": "verified", "vm": "windows01", "address": "192.0.2.77", "os": "Windows Server 2022"}, "acceptance": {"state": "verified", "finished_at": "2026-10-16T11:30:00+00:00"}}],
                         "switches": [], "cables": None, "verified": [{"area": "ESXi", "at": "2026-10-16T11:00:00+00:00", "message": "ESXi verified."}]}
        if path == "/api/v1/runtime/write-scope":
            return 200, {"scope": self.scope}
        if path == "/api/v1/runtime/write-scope/preview":
            return 200, {"review_token": "t", "confirmation_phrase": "", "blockers": [], "target_scope": body["target_scope"]}
        if path == "/api/v1/runtime/write-scope/apply":
            self.scope = "read_only" if self.scope != "read_only" else "changed"
            return 200, {"scope": self.scope}
        return 404, {"detail": "unexpected " + method + " " + path}

    def _esxi(self) -> dict:
        return {"state": self.esxi, "active": self.esxi == "installing", "message": "ESXi verified." if self.esxi == "verified" else "Installing…"}

    def _test(self) -> dict:
        return {"state": self.test, "active": self.test == "running", "message": "Passed." if self.test == "verified" else "Testing…",
                "lookup": "esx01.lab.test", "default_lookup": "esx01.lab.test", "signin": {"username": "Administrator", "password_saved": True},
                "phases": [{"phase": "outside", "label": "Windows answers from outside", "state": "running" if self.test == "running" else "ok"}]}


@pytest.fixture
def lab():
    fake = FakeLab()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _serve(self, method):
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            with fake.lock:
                status, payload = fake.handle(method, self.path, body)
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = lambda self: self._serve("GET")
        do_POST = lambda self: self._serve("POST")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fake.url = f"http://127.0.0.1:{server.server_port}"
    yield fake
    server.shutdown()


def make_pilot(lab, tmp_path, monkeypatch):
    monkeypatch.setattr(pilot_module, "HERE", tmp_path)
    return Pilot(Api(lab.url, timeout=5), clock=lambda s: time.sleep(min(s, 0.01)))


def wait(pilot, phase, seconds=10):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        with pilot.lock:
            if pilot.state["phase"] == phase:
                return pilot.state
        time.sleep(0.02)
    raise AssertionError(f"never reached {phase}; now {pilot.state['phase']}: {pilot.state['message']}")


def test_check_then_one_approval_builds_the_kit_and_writes_the_report(lab, tmp_path, monkeypatch):
    pilot = make_pilot(lab, tmp_path, monkeypatch)
    pilot.check()
    assert pilot.state["phase"] == "checked" and lab.sent == []  # a check changes nothing
    pilot.ask_approval()
    assert pilot.state["phase"] == "approve" and lab.sent == []
    pilot.approve()
    state = wait(pilot, "done")
    assert [leg["state"] for leg in state["legs"]] == ["done", "skipped", "skipped", "skipped", "done", "skipped", "done"]
    assert lab.sent.count(f"POST /api/v1/rack-plans/{P}/esxi/install?device_id={S}") == 1
    assert sum(1 for s in lab.sent if "acceptance/start" in s) == 1
    assert not any("raid-rebuild/apply" in s or "windows/start" in s or "switch-setup/start" in s for s in lab.sent)
    assert lab.scope == "read_only"
    report = Path(state["report"]).read_text(encoding="utf-8")
    assert "Test kit" in report and "windows01" in report and "Passed" in report


def test_existing_volumes_stop_before_anything_is_sent_then_try_again_carries_on(lab, tmp_path, monkeypatch):
    lab.volumes = True
    pilot = make_pilot(lab, tmp_path, monkeypatch)
    pilot.check(); pilot.ask_approval(); pilot.approve()
    state = wait(pilot, "needs_you")
    assert "already has RAID volumes" in state["message"] and state["where"] == "/setup/disks"
    assert not any("raid-rebuild" in s for s in lab.sent)
    assert lab.scope == "read_only"
    lab.volumes = False
    pilot.resume()
    wait(pilot, "done")


def test_a_plan_changed_after_approval_needs_a_new_approval(lab, tmp_path, monkeypatch):
    lab.volumes = True
    pilot = make_pilot(lab, tmp_path, monkeypatch)
    pilot.check(); pilot.ask_approval(); pilot.approve()
    wait(pilot, "needs_you")
    lab.volumes = False
    lab.image = "other.ova"
    before = len(lab.sent)
    pilot.resume()
    assert pilot.state["phase"] == "idle" and "changed since you approved" in pilot.state["message"]
    assert len(lab.sent) == before


def test_pause_stops_before_the_next_change(lab, tmp_path, monkeypatch):
    stop = threading.Event()
    engine = Engine(Api(lab.url, timeout=5), P, [{"id": S, "name": "HPE DL360 3"}], [], stop=stop, clock=lambda s: None)
    stop.set()
    with pytest.raises(Paused):
        engine.leg_esxi()
    assert not any("esxi/install" in s for s in lab.sent)


def test_a_refused_request_stops_at_once_not_after_an_hour(lab, tmp_path, monkeypatch):
    engine = Engine(Api(lab.url, timeout=5), P, [{"id": S, "name": "HPE DL360 3"}], [], clock=lambda s: None)
    calls = []

    def read():
        calls.append(1)
        raise pilot_module.ApiError(409, "refused")
    with pytest.raises(pilot_module.ApiError):
        engine.poll(0, read, lambda v: True, lambda v: None)
    assert len(calls) == 1


def test_needs_you_names_the_lab_builder_page(lab, tmp_path, monkeypatch):
    lab.volumes = True
    engine = Engine(Api(lab.url, timeout=5), P, [{"id": S, "name": "HPE DL360 3"}], [], clock=lambda s: None)
    with pytest.raises(NeedsYou) as stop:
        engine.leg_raid()
    assert stop.value.where == "/setup/disks" and stop.value.label == "Open Disks & RAID"


def test_every_request_can_fail_every_way_and_the_laws_hold():
    """Chaos: lost reply, 503, pause and kill at every request of a full flight (see chaos.py)."""
    import chaos

    baseline = chaos.fly(chaos.FakeKit(), {})
    assert baseline["outcome"] == "done" and not chaos.laws(baseline, {})
    broken = {}
    for position in range(1, baseline["requests"] + 1):
        for fault in ("lost", "503", "pause", "kill"):
            result = chaos.fly(chaos.FakeKit(), {position: fault})
            problems = chaos.laws(result, {position: fault})
            if problems:
                broken[(position, fault)] = problems
    assert broken == {}


def test_stop_help_and_switch_config_evidence():
    import evidence
    import help as stop_help

    assert stop_help.advice("Switch: The settings were sent and saved, but Vlan1 has no address from DHCP after 3 minutes.")["title"] == "The switch got no DHCP address."
    assert stop_help.advice("Server already has RAID volumes. Keep them or wipe them")["steps"][0].startswith("Kit Pilot never deletes")
    assert stop_help.advice("something unknown") is None
    data = {"switches": [{"name": "Cisco switch 1", "config": {"after": "hostname lab-sw01\nenable secret 9 ********", "at": "2026-10-17T10:00:00",
                                                                "diff": ["--- before setup", "+++ after setup", "@@ -1 +1,2 @@", "-hostname Switch", "+hostname lab-sw01", "+enable secret 9 ********"]}}]}
    html = evidence.switch_config_section(data, [], {})
    assert "configuration after the first setup" in html and "+hostname lab-sw01" in html and "3 lines changed" in html and "<script" not in html
