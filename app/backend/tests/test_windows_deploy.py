from contextlib import nullcontext
from datetime import timedelta

import pytest

from app.providers import esxi_govc as govc
from app.services import windows_deploy as service

HOST = {"address": "192.0.2.20", "password": "Fixture-Pass-1", "datastore": "VMdata"}


class FakeEsxi:
    def __init__(self):
        self.vms = {}
        self.sent = []
        self.fail_import = None
        self.tools_after = 2  # vm_info reads after power-on before Tools reports

    def datastores(self, ip, password):
        return [{"name": "VMdata", "capacity": 4 * 1024**4, "free": 3 * 1024**4}, {"name": "datastore1", "capacity": 150 * 1024**3, "free": 5 * 1024**3}]

    def networks(self, ip, password):
        return ["VM Network"]

    def ovf_networks(self, ip, password, path):
        return ["bridged"]

    def import_vm(self, ip, password, *, path, datastore, name, network, mappings, heartbeat=None):
        if heartbeat:
            heartbeat()
        self.sent.append(("import", name, datastore, network, tuple(mappings)))
        if self.fail_import:
            raise govc.GovcError(self.fail_import)
        self.vms[name] = {"power": "poweredOff", "tools": "guestToolsNotRunning", "ip": None, "addresses": [], "hostname": None, "guest_os": "Microsoft Windows Server 2022"}

    def vm_info(self, ip, password, name):
        vm = self.vms.get(name)
        if vm and vm["power"] == "poweredOn":
            self.tools_after -= 1
            if self.tools_after <= 0:
                vm.update(tools="guestToolsRunning", ip="192.0.2.77", hostname="WIN01")
        return dict(vm) if vm else None

    def power_on(self, ip, password, name):
        self.sent.append(("power", name))
        self.vms[name]["power"] = "poweredOn"


@pytest.fixture
def esxi(monkeypatch, tmp_path, db_session):
    from sqlalchemy.orm import sessionmaker

    fake = FakeEsxi()
    monkeypatch.setattr(service, "_session_factory", lambda: sessionmaker(bind=db_session.get_bind()))
    media = tmp_path / "media"
    media.mkdir()
    (media / "win2022.ova").write_bytes(b"ova-fixture" * 100)
    (media / "split.ovf").write_text('<Envelope><References><File ovf:href="split-disk1.vmdk" xmlns:ovf="x"/></References></Envelope>')
    monkeypatch.setattr(service, "_media_root", lambda: media)
    monkeypatch.setattr("app.services.firmware_packages.media_root", lambda: media)
    monkeypatch.setattr(service, "_host", lambda session, profile_id, device_id: dict(HOST))
    monkeypatch.setattr(service, "_policy_blockers", lambda: [])
    for name in ("datastores", "networks", "ovf_networks", "import_vm", "vm_info", "power_on"):
        monkeypatch.setattr(govc, name, getattr(fake, name))
    monkeypatch.setattr("app.services.runtime_write_scope.dispatch_lease", lambda action: nullcontext())
    return fake


def save(db_session, **change):
    payload = {"image": "win2022.ova", "vm_name": "windows01", "datastore": "VMdata", "network": "VM Network", **change}
    return service.save_settings(db_session, "kit", "srv", payload, "op")


def run_import(db_session):
    started = service.start(db_session, "kit", "srv", "op")
    service._workers[started["run_id"]].join(5)
    return started


def test_setup_lists_images_and_flags_an_ovf_missing_its_disk(db_session, esxi):
    setup = service.get_setup(db_session, "kit", "srv")
    images = {i["name"]: i for i in setup["images"]}
    assert images["win2022.ova"]["kind"] == "ova" and images["win2022.ova"]["windows"] is True
    assert images["split.ovf"]["missing"] == ["split-disk1.vmdk"]
    assert setup["host"]["networks"] == ["VM Network"] and setup["host"]["default_datastore"] == "VMdata"
    with pytest.raises(service.WindowsDeployError, match="split-disk1.vmdk"):
        save(db_session, image="split.ovf")
    with pytest.raises(service.WindowsDeployError, match="letters, digits and dashes"):
        save(db_session, vm_name="bad name!")
    with pytest.raises(service.WindowsDeployError, match="datastore"):
        save(db_session, datastore="nope")


def test_review_blocks_an_existing_vm_name_and_a_full_datastore(db_session, esxi):
    save(db_session)
    assert service.review(db_session, "kit", "srv")["ready"] is True
    esxi.vms["windows01"] = {"power": "poweredOn"}
    assert any("already exists" in b for b in service.review(db_session, "kit", "srv")["blockers"])
    esxi.vms.clear()
    save(db_session, datastore="datastore1")
    assert any("too little free space" in b for b in service.review(db_session, "kit", "srv")["blockers"])


def test_imports_once_powers_on_once_and_verifies_by_vmware_tools(db_session, esxi):
    save(db_session)
    run_import(db_session)
    assert esxi.sent == [("import", "windows01", "VMdata", "VM Network", ("bridged",))]
    for _ in range(6):
        current = service.advance(db_session, "kit", "srv", "op")
        if not current["active"]:
            break
    assert current["state"] == "verified" and current["address"] == "192.0.2.77" and current["hostname"] == "WIN01"
    assert esxi.sent.count(("power", "windows01")) == 1
    assert "Fixture-Pass-1" not in str(current)


def test_a_failed_import_stops_and_nothing_is_powered_on(db_session, esxi):
    esxi.fail_import = "Disk upload failed"
    save(db_session)
    run_import(db_session)
    current = service.advance(db_session, "kit", "srv", "op")
    assert current["state"] == "needs_attention" and "Disk upload failed" in current["message"]
    assert not any(s[0] == "power" for s in esxi.sent)
    closed = service.close(db_session, "kit", "srv", "op")
    assert closed["active"] is False


def test_an_import_whose_outcome_was_lost_is_not_started_again(db_session, esxi, monkeypatch):
    save(db_session)
    monkeypatch.setattr(service.threading.Thread, "start", lambda self: None)  # app "restarted" before the worker ran
    started = service.start(db_session, "kit", "srv", "op")
    service._workers.pop(started["run_id"], None)
    monkeypatch.setattr(service, "_now", lambda: service.datetime.now(service.UTC) + timedelta(minutes=5))
    current = service.advance(db_session, "kit", "srv", "op")
    assert current["state"] == "needs_attention" and "not started again" in current["message"]
    assert esxi.sent == []


def test_a_second_start_is_refused_while_one_runs(db_session, esxi):
    save(db_session)
    run_import(db_session)
    with pytest.raises(service.WindowsDeployError, match="already running"):
        service.start(db_session, "kit", "srv", "op")


def test_a_guest_that_is_not_windows_is_never_verified(db_session, esxi):
    save(db_session)
    run_import(db_session)
    esxi.vms["windows01"]["guest_os"] = "Ubuntu Linux (64-bit)"
    for _ in range(6):
        current = service.advance(db_session, "kit", "srv", "op")
    assert current["state"] == "running" and current["active"]


def test_a_lost_power_on_reply_is_read_back_never_resent(db_session, esxi, monkeypatch):
    save(db_session)
    run_import(db_session)

    def lost(ip, password, name):
        esxi.sent.append(("power", name))
        raise KeyboardInterrupt  # crash after sending, before the reply is recorded

    monkeypatch.setattr(govc, "power_on", lost)
    with pytest.raises(KeyboardInterrupt):
        service.advance(db_session, "kit", "srv", "op")
    assert service.advance(db_session, "kit", "srv", "op")["state"] == "running"
    monkeypatch.setattr(service, "_now", lambda: service.datetime.now(service.UTC) + timedelta(minutes=5))
    current = service.advance(db_session, "kit", "srv", "op")
    assert current["state"] == "needs_attention" and "not sent again" in current["message"]
    assert esxi.sent.count(("power", "windows01")) == 1


def test_the_verify_deadline_holds_while_esxi_cannot_be_read(db_session, esxi, monkeypatch):
    save(db_session)
    run_import(db_session)
    esxi.tools_after = 99
    service.advance(db_session, "kit", "srv", "op")  # powers on

    def unreadable(*args):
        raise govc.GovcError("connection refused")

    monkeypatch.setattr(govc, "vm_info", unreadable)
    monkeypatch.setattr(service, "_now", lambda: service.datetime.now(service.UTC) + timedelta(minutes=50))
    current = service.advance(db_session, "kit", "srv", "op")
    assert current["state"] == "needs_attention" and "45 minutes" in current["message"]


def test_a_stale_result_changes_nothing(db_session, esxi):
    save(db_session)
    started = run_import(db_session)
    assert service._result(db_session, "op", started["run_id"], "import", "failed", "late worker") is False


def test_errors_never_carry_the_password_even_url_encoded():
    assert govc._scrub("bad login for p%40ss%2Fw0rd and p@ss/w0rd", "p@ss/w0rd") == "bad login for *** and ***"
