from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.providers import hpe_ilo_components as ilo
from app.services import parts_update as service

BOARD = service.SHARED_BOARD_TARGET
IE, SPS, SR = "a6b1-ie", "a6b1-sps", "a6b1-sr"
MANIFESTS = [
    {"file": "U32_3.66.fwpkg", "device": "System BIOS - U32", "version": "v3.66 (04/01/2026)", "target": BOARD, "method": "ilo", "reset": True, "minutes": 5},
    {"file": "U30_3.66.fwpkg", "device": "System BIOS - U30", "version": "v3.66 (04/01/2026)", "target": "other-rom", "method": "ilo", "reset": True, "minutes": 5},
    {"file": "SR_8.00.fwpkg", "device": "Smart Array", "version": "8.00", "target": SR, "method": "ilo", "reset": True, "minutes": 5},
    {"file": "IE_0.2.3.0.fwpkg", "device": "Innovation Engine (IE) Universal Image", "version": "0.2.3.0", "target": IE, "method": "bios", "reset": False, "minutes": 5},
    {"file": "SPS_04.01.05.201.fwpkg", "device": "Server Platform Services (SPS) Firmware", "version": "04.01.05.201", "target": SPS, "method": "bios", "reset": True, "minutes": 5},
    {"file": "ilo5_319.fwpkg", "device": "iLO 5", "version": "3.19", "target": "ilo", "method": "ilo", "reset": False, "minutes": 5},
]


def inventory_items():
    return [
        {"name": "iLO 5", "version": "3.19 Apr 07 2026", "targets": ["ilo"], "where": "System Board", "updateable": True},
        {"name": "System ROM", "version": "U32 v1.46 (10/02/2018)", "targets": [BOARD, "x"], "where": "System Board", "updateable": True},
        {"name": "Intelligent Platform Abstraction Data", "version": "7.1.0", "targets": [BOARD, "x"], "where": "System Board", "updateable": True},
        {"name": "Innovation Engine (IE) Firmware", "version": "0.1.6.1", "targets": [BOARD, IE], "where": "System Board", "updateable": True},
        {"name": "Server Platform Services (SPS) Firmware", "version": "4.0.4.393", "targets": [BOARD, SPS], "where": "System Board", "updateable": True},
        {"name": "HPE Smart Array P408i-a SR Gen10", "version": "5.61", "targets": [SR], "where": "Embedded RAID", "updateable": True},
    ]


def test_matching_picks_system_rom_on_the_shared_board_id_and_orders_the_rom_first():
    found = service.compare(MANIFESTS, inventory_items())
    names = [p["item"] for p in found["install"]]
    assert names[0] == "System ROM" and found["install"][0]["rom"] is True
    assert set(names) == {"System ROM", "HPE Smart Array P408i-a SR Gen10", "Innovation Engine (IE) Firmware", "Server Platform Services (SPS) Firmware"}
    assert all(p["file"] != "U30_3.66.fwpkg" for p in found["install"])  # other ROM families never match
    assert found["elsewhere"] == []  # the iLO is current
    kinds = [(ph["kind"], ph.get("part")) for ph in service.phases_for(found["install"])]
    rom, sr = found["install"][0]["id"], found["install"][1]["id"]
    # The System ROM alone first: flashed, restarted into and read back before anything else.
    assert kinds[:5] == [("flash", rom), ("wait-ilo", rom), ("restart", None), ("wait-start", None), ("check", None)]
    assert kinds[5:7] == [("flash", sr), ("wait-ilo", sr)]
    assert kinds[-3:] == [("restart", None), ("wait-start", None), ("check", None)]
    first_queue = next(i for i, k in enumerate(kinds) if k[0] == "queue")
    assert first_queue > kinds.index(("check", None))  # BIOS-applied parts only after the ROM readback


def test_versions_compare_numerically_ignoring_family_and_dates():
    assert service.newer("v3.66 (04/01/2026)", "U32 v1.46 (10/02/2018)") is True
    assert service.newer("04.01.05.201", "4.0.4.393") is True
    assert service.newer("0.2.3.0", "0.2.3") is False
    assert service.at_least("U32 v3.66 (04/01/2026)", "v3.66 (04/01/2026)") is True


class FakeILO:
    def __init__(self):
        self.items = inventory_items()
        self.sent = []
        self.post = "2026-10-06T14:00:00Z"
        self.power = "On"
        self.queue = []
        self.repo = {"IE_0.2.3.0.fwpkg"}
        self.refuse = None
        self.rom_flashes = True

    def upload(self, config, *, filename, data, flash_now):
        self.sent.append(("upload", filename, flash_now))
        if self.refuse == filename:
            raise ilo.ComponentError("The iLO refused the package (HTTP 400).", refused=True)
        if flash_now:
            self.pending = filename
        else:
            self.repo.add(filename)

    def queue_task(self, config, *, filename):
        self.sent.append(("queue", filename))
        self.queue.append({"name": "t", "filename": filename, "state": "Pending", "command": "ApplyUpdate", "result": None})
        return "t"

    def reset(self, kind, config):
        self.sent.append(("restart", kind))
        self.post = "2026-10-06T15:%02d:00Z" % len(self.sent)
        for item in self.items:
            if item["name"] == "System ROM" and self.rom_flashes:
                item["version"] = "U32 v3.66 (04/01/2026)"
            if item["name"].startswith("HPE Smart Array"):
                item["version"] = "8.00"
        if self.queue:
            for task in self.queue:
                task["state"] = "Complete"
            for item in self.items:
                if item["name"].startswith("Innovation"):
                    item["version"] = "0.2.3.0"
                if item["name"].startswith("Server Platform"):
                    item["version"] = "4.1.5.201"
        return {"status_code": 200}


@pytest.fixture
def fake(monkeypatch):
    f = FakeILO()
    import app.services.esxi_boot_workflow as boot

    monkeypatch.setattr(service, "_package", lambda session, profile_id: {"path": "spp.iso", "file_name": "spp.iso"})
    monkeypatch.setattr(service, "_config", lambda session, device_id: SimpleNamespace(host="192.0.2.10"))
    monkeypatch.setattr(service, "_identity", lambda config: {"hardware_identity": "hw", "endpoint_identity": "ep", "power": f.power, "post": "FinishedPost"})
    monkeypatch.setattr(service, "_post_stamp", lambda config: f.post)
    monkeypatch.setattr(service, "_policy_blockers", lambda: [])
    monkeypatch.setattr(service, "MIN_ILO_WAIT", timedelta(0))
    monkeypatch.setattr(service, "QUIET_ILO_WAIT", timedelta(0))
    monkeypatch.setattr(service, "manifests", lambda package: MANIFESTS)
    monkeypatch.setattr(service, "inventory", lambda config: [dict(i) for i in f.items])
    monkeypatch.setattr(service, "package_bytes", lambda package, filename: b"fwpkg")
    monkeypatch.setattr(ilo, "upload_package", f.upload)
    monkeypatch.setattr(ilo, "queue_bios_update", f.queue_task)
    monkeypatch.setattr(ilo, "update_service", lambda config: {"state": "COMPLETE", "busy": False, "result": None, "progress": 100, "push_uri": "/cgi-bin/uploadFile"})
    monkeypatch.setattr(ilo, "repository", lambda config: [{"filename": n, "version": getattr(f, "repo_versions", {}).get(n, n.split("_", 1)[1].rsplit(".", 1)[0]), "locked": False} for n in f.repo])
    monkeypatch.setattr(ilo, "task_queue", lambda config: list(f.queue))
    monkeypatch.setattr(boot, "_post_system_reset", f.reset)
    monkeypatch.setattr("app.services.runtime_write_scope.dispatch_lease", lambda action: nullcontext())
    return f


def run_to_end(db_session, limit=60):
    status = None
    for _ in range(limit):
        status = service.advance(db_session, "kit", "srv", "op")
        if not status["active"]:
            break
    return status


def test_full_run_installs_rom_first_then_queues_bios_parts_and_reads_everything_back(db_session, fake):
    plan = service.review(db_session, "kit", "srv", "op")
    assert plan["restarts"] == 3 and not plan["blockers"]
    first = service.start(db_session, "kit", "srv", "op", plan["review_id"])
    assert first["active"] is True
    final = run_to_end(db_session)
    assert final["state"] == "verified", final
    assert all(p["state"] == "done" for p in final["parts"])
    uploads = [s for s in fake.sent if s[0] == "upload"]
    assert uploads[0] == ("upload", "U32_3.66.fwpkg", True)
    assert ("upload", "SPS_04.01.05.201.fwpkg", False) in uploads
    assert ("upload", "IE_0.2.3.0.fwpkg", False) not in uploads  # already in the iLO Repository
    queued_at = fake.sent.index(("queue", "IE_0.2.3.0.fwpkg"))
    first_restart = fake.sent.index(("restart", "ForceRestart"))
    assert first_restart < queued_at  # never queued for the old BIOS
    assert sum(1 for s in fake.sent if s[0] == "restart") == 3
    assert fake.sent.index(("upload", "SR_8.00.fwpkg", True)) > first_restart  # nothing else before the new ROM runs
    assert all(uploads.count(u) == 1 for u in uploads)  # each package sent once


def test_a_rom_that_does_not_reach_its_version_stops_before_anything_is_queued(db_session, fake):
    fake.rom_flashes = False
    plan = service.review(db_session, "kit", "srv", "op")
    service.start(db_session, "kit", "srv", "op", plan["review_id"])
    final = run_to_end(db_session)
    assert final["state"] == "needs_attention" and "System ROM" in final["message"]
    assert not any(s[0] == "queue" for s in fake.sent)
    closed = service.close(db_session, "kit", "srv", "op")
    assert closed["active"] is False and closed["state"] == "failed"


def test_a_refused_upload_stops_the_run_and_nothing_else_is_sent(db_session, fake):
    fake.refuse = "U32_3.66.fwpkg"
    plan = service.review(db_session, "kit", "srv", "op")
    service.start(db_session, "kit", "srv", "op", plan["review_id"])
    final = run_to_end(db_session)
    assert final["state"] == "needs_attention" and "refused" in final["message"]
    assert fake.sent == [("upload", "U32_3.66.fwpkg", True)]


def test_a_send_without_a_recorded_reply_is_never_repeated(db_session, fake, monkeypatch):
    plan = service.review(db_session, "kit", "srv", "op")

    def lost(*args, **kwargs):
        raise KeyboardInterrupt  # stands in for a crash mid-send: nothing is recorded

    monkeypatch.setattr(ilo, "upload_package", lost)
    with pytest.raises(KeyboardInterrupt):
        service.start(db_session, "kit", "srv", "op", plan["review_id"])
    waiting = service.advance(db_session, "kit", "srv", "op")
    assert waiting["state"] == "running" and waiting["active"]
    monkeypatch.setattr(service, "SEND_REPLY_LIMIT", timedelta(seconds=-1))
    stuck = service.advance(db_session, "kit", "srv", "op")
    assert stuck["state"] == "needs_attention" and "not sent again" in stuck["message"]
    assert fake.sent == []


def test_an_expired_or_changed_review_does_not_start(db_session, fake, monkeypatch):
    plan = service.review(db_session, "kit", "srv", "op")
    fake.items[1]["version"] = "U32 v3.66 (04/01/2026)"
    with pytest.raises(service.PartsUpdateError, match="changed since the review"):
        service.start(db_session, "kit", "srv", "op", plan["review_id"])
    assert fake.sent == []


def test_the_ilo_wait_never_ends_on_a_stale_complete_right_after_an_upload(db_session, fake, monkeypatch):
    monkeypatch.setattr(service, "MIN_ILO_WAIT", timedelta(seconds=60))
    monkeypatch.setattr(service, "QUIET_ILO_WAIT", timedelta(minutes=5))
    plan = service.review(db_session, "kit", "srv", "op")
    service.start(db_session, "kit", "srv", "op", plan["review_id"])
    for _ in range(5):
        current = service.advance(db_session, "kit", "srv", "op")
    assert [p["state"] for p in current["phases"][:2]] == ["ok", "todo"]  # still waiting on the iLO
    assert not any(s[0] == "restart" for s in fake.sent)
    states = iter(["Writing", "Writing", "Complete"])
    monkeypatch.setattr(ilo, "update_service", lambda config: (lambda st: {"state": st.upper(), "busy": st == "Writing", "result": None, "progress": None, "push_uri": "/cgi-bin/uploadFile"})(next(states, "Complete")))
    monkeypatch.setattr(service, "MIN_ILO_WAIT", timedelta(0))
    for _ in range(3):
        current = service.advance(db_session, "kit", "srv", "op")
    assert current["phases"][1]["state"] == "ok"  # seen working, then complete


def test_bios_parts_are_not_offered_without_a_matching_system_rom_package(db_session, fake, monkeypatch):
    monkeypatch.setattr(service, "manifests", lambda package: [m for m in MANIFESTS if not m["file"].startswith("U3")])
    plan = service.review(db_session, "kit", "srv", "op")
    assert all(p["method"] != "bios" for p in plan["parts"])
    assert any("no System ROM package" in b for b in plan["blockers"])


def test_a_repository_copy_of_a_different_version_is_uploaded_again(db_session, fake):
    fake.repo_versions = {"IE_0.2.3.0.fwpkg": "0.1.0.0"}
    plan = service.review(db_session, "kit", "srv", "op")
    service.start(db_session, "kit", "srv", "op", plan["review_id"])
    run_to_end(db_session)
    assert ("upload", "IE_0.2.3.0.fwpkg", False) in fake.sent


def test_review_is_blocked_while_the_ilo_holds_queued_updates(db_session, fake):
    fake.queue.append({"name": "old", "filename": "old.fwpkg", "state": "Pending", "command": "ApplyUpdate", "result": None})
    plan = service.review(db_session, "kit", "srv", "op")
    assert any("queued updates" in b for b in plan["blockers"])
