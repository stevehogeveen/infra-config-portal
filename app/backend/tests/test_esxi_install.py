from contextlib import contextmanager
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace

import pycdlib
import pytest

from app.services import esxi_install as service


def _iso(path, esxi=True):
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3)
    boot = (
        b"bootstate=0\ntitle=Loading ESXi installer\nkernel=/b.b00\nkernelopt=runweasel\n"
        if esxi
        else b"x\n"
    )
    iso.add_fp(BytesIO(boot), len(boot), "/BOOT.CFG;1")
    if esxi:
        iso.add_fp(BytesIO(b"kernel"), 6, "/B.B00;1")
    iso.write(str(path))
    iso.close()


CONTEXT = {
    "active_profile": {
        "id": "kit",
        "version": 3,
        "source": "saved",
        "global_settings": {
            "gateway": "192.0.2.1",
            "dns_servers": ["192.0.2.53"],
            "ntp_servers": ["192.0.2.123"],
            "domain_name": "lab.example",
        },
    },
    "resolved_address_plan": {"subnet": "192.0.2.0/24", "esxi_management": "192.0.2.20"},
    "enabled_features": {
        "deployment_mode": "single_server_local_storage",
        "storage_location": "server_local",
        "enable_ntp": False,
    },
}


@pytest.fixture
def kit(client, monkeypatch, tmp_path):
    profile = client.post(
        "/api/v1/lab/profiles",
        json={"name": "ESXi kit", "profile_topology": "custom", "subnet_cidr": "192.0.2.0/24"},
    ).json()
    base = "/api/v1/rack-plans/" + profile["id"]
    saved = client.put(
        base,
        json={
            "equipment": [
                {
                    "id": "s",
                    "name": "Server",
                    "kind": "server",
                    "model": "HPE DL360",
                    "position": 1,
                    "height": 1,
                }
            ]
        },
    ).json()
    device = saved["equipment"][0]["device_id"]
    context = {**CONTEXT, "active_profile": {**CONTEXT["active_profile"], "id": profile["id"]}}
    media = tmp_path / "Media"
    media.mkdir()
    monkeypatch.setenv("FIRMWARE_MEDIA_ROOT", str(media))
    monkeypatch.setattr(
        "app.services.lab_profiles.active_lab_profile_context", lambda *a, **k: context
    )
    monkeypatch.setattr(
        service, "_secret_path", lambda device_id: tmp_path / ".local" / f"{device_id}.sha512crypt"
    )
    monkeypatch.setattr(
        service,
        "_boot_volume",
        lambda session, device_id: {
            "name": "ESXi boot",
            "bays": ["1I:1:1", "1I:1:2"],
            "capacity_bytes": 300e9,
            "disk_id": "naa.600508b1001c0000",
            "read_at": None,
        },
    )
    monkeypatch.setattr(
        service,
        "_data_volume",
        lambda session, device_id, **kwargs: {
            "name": "VM data",
            "raid": "RAID5",
            "bays": ["2I:1:5", "2I:1:6", "2I:1:7", "2I:1:8"],
            "capacity_bytes": 3.6e12,
            "disk_id": "naa.600508b1001cdata",
            "read_at": None,
        },
    )
    return SimpleNamespace(
        base=base + "/esxi",
        query="?device_id=" + device,
        profile=profile["id"],
        device=device,
        media=media,
        tmp=tmp_path,
        context=context,
    )


def test_media_lists_only_esxi_installers_and_records_the_choice(client, kit):
    _iso(kit.media / "VMware-ESXi-8.0.3-24859861-HPE-803.0.0.12.2.0.9-oct2025.iso")
    _iso(kit.media / "P-SPP.iso", esxi=False)
    _iso(kit.media / "esxi-installer-0123456789abcdef.iso")
    listing = client.get(kit.base + "/media" + kit.query).json()
    assert [item["name"] for item in listing["isos"]] == [
        "VMware-ESXi-8.0.3-24859861-HPE-803.0.0.12.2.0.9-oct2025.iso"
    ]
    assert listing["isos"][0]["version"] == "8.0.3 build 24859861"
    assert listing["selected"] is None
    assert (
        client.post(kit.base + "/media" + kit.query, json={"path": "P-SPP.iso"}).status_code == 409
    )
    assert (
        client.post(kit.base + "/media" + kit.query, json={"path": "../outside.iso"}).status_code
        == 409
    )
    chosen = client.post(
        kit.base + "/media" + kit.query, json={"path": listing["isos"][0]["path"]}
    ).json()
    assert (
        chosen["selected"]["name"].startswith("VMware-ESXi-8.0.3")
        and chosen["selected"]["present"] is True
    )


def test_settings_validate_and_keep_the_password_only_as_a_hash(client, kit):
    good = {
        "hostname": "esxi01.lab.example",
        "management_ip": "192.0.2.20",
        "vlan_id": 0,
        "management_nic": "vmnic0",
        "root_password": "Lab-Pass-2026",
    }
    for change, reason in [
        ({"hostname": "esxi01"}, "full host name"),
        ({"hostname": "esxi01.other.example"}, ".lab.example"),
        ({"management_ip": "198.51.100.5"}, "free host address"),
        ({"management_ip": "192.0.2.1"}, "not the gateway"),
        ({"management_nic": "eth0"}, "network port"),
        ({"root_password": "short"}, "8 characters"),
    ]:
        response = client.put(kit.base + "/settings" + kit.query, json={**good, **change})
        assert response.status_code == 409 and reason in response.json()["detail"], change
    saved = client.put(kit.base + "/settings" + kit.query, json=good).json()
    assert saved["password_set"] is True and saved["hostname"] == "esxi01.lab.example"
    assert "root_password" not in saved and "Lab-Pass-2026" not in str(saved)
    secret = (kit.tmp / ".local" / f"{kit.device}.sha512crypt").read_text()
    assert secret.startswith("$6$") and "Lab-Pass-2026" not in secret
    # Changing other fields keeps the saved password.
    again = client.put(
        kit.base + "/settings" + kit.query, json={**good, "root_password": None, "vlan_id": 120}
    ).json()
    assert again["vlan_id"] == 120 and again["password_set"] is True


def _ready(client, kit, monkeypatch):
    _iso(kit.media / "VMware-ESXi-8.0.3-24859861.iso")
    client.post(kit.base + "/media" + kit.query, json={"path": "VMware-ESXi-8.0.3-24859861.iso"})
    client.put(
        kit.base + "/settings" + kit.query,
        json={
            "hostname": "esxi01.lab.example",
            "management_ip": "192.0.2.20",
            "vlan_id": 0,
            "management_nic": "vmnic0",
            "root_password": "Lab-Pass-2026",
        },
    )
    built = kit.tmp / "derived.iso"
    built.write_bytes(b"derived-installer")
    seen = {}

    def fake_builder(request, **kwargs):
        seen.update(
            request=request, context=kwargs["profile_context"], roots=kwargs["allowed_media_roots"]
        )
        return {
            "status": "ready",
            "derived_artifact": {
                "iso": str(built),
                "iso_sha256": __import__("hashlib").sha256(b"derived-installer").hexdigest(),
                "iso_size_bytes": built.stat().st_size,
                "kickstart_sha256": "k" * 64,
            },
        }

    monkeypatch.setattr(
        "app.services.esxi_installer_artifact.prepare_esxi_installer_artifact", fake_builder
    )
    return seen


def test_build_needs_everything_then_binds_the_saved_values_and_goes_stale_on_change(
    client, kit, monkeypatch
):
    blocked = client.post(kit.base + "/installer" + kit.query).json()
    assert (
        blocked["status"] == "blocked" and "Choose the ESXi installer ISO." in blocked["blockers"]
    )
    seen = _ready(client, kit, monkeypatch)
    result = client.post(kit.base + "/installer" + kit.query).json()
    assert result["status"] == "ready", result
    request = seen["request"]
    assert request["install_disk_id"] == "naa.600508b1001c0000"
    assert request["ntp_servers"] == [] and request["management_vlan_id"] == 0
    assert request["root_password_sha512_crypt"].startswith("$6$")
    assert seen["context"]["esxi_management_vlan_id"] == 0
    assert (kit.media / result["built"]["iso_name"]).read_bytes() == b"derived-installer"
    assert result["built"]["iso_name"].startswith("esxi-installer-")
    # The built installer is hidden from the ISO picker.
    assert all(
        not item["name"].startswith("esxi-installer-")
        for item in client.get(kit.base + "/media" + kit.query).json()["isos"]
    )
    client.put(
        kit.base + "/settings" + kit.query,
        json={
            "hostname": "esxi02.lab.example",
            "management_ip": "192.0.2.20",
            "vlan_id": 0,
            "management_nic": "vmnic0",
        },
    )
    assert client.get(kit.base + "/installer" + kit.query).json()["status"] == "stale"


class FakeServer:
    def __init__(self, power="On"):
        self.power, self.inserted, self.image, self.boot = power, False, None, {}
        self.sent = []
        self.fail = None
        self.post_states = []

    def read(self, config):
        return {
            "hardware_identity": "fixture-hardware",
            "power": self.power,
            "boot": dict(self.boot),
            "post": self.post_states.pop(0) if self.post_states else "FinishedPost",
            "media": {"path": "/vm/2"},
            "inserted": self.inserted,
            "image": self.image,
            "eject_target": "/redfish/v1/Managers/1/VirtualMedia/2/Actions/VirtualMedia.EjectMedia",
        }

    def insert(self, media, url, config):
        self.sent.append("media")
        if self.fail == "media":
            raise RuntimeError("timeout")
        self.inserted, self.image = True, url
        return {"status_code": 200}

    def patch(self, payload, config):
        self.sent.append("boot")
        if self.fail == "boot-refused":
            self.fail = None
            return {"status_code": 400, "response": {"error": {"@Message.ExtendedInfo": [
                {"MessageId": "iLO.2.14.UnableToModifyDuringSystemPOST"}]}}}
        self.boot = {"BootSourceOverrideEnabled": "Once", "BootSourceOverrideTarget": "Cd"}
        return {"status_code": 200}

    def reset(self, kind, config):
        self.sent.append(f"power:{kind}")
        self.power = "On"
        return {"status_code": 200}

    def post(self, path, body, config):
        self.sent.append("eject")
        self.inserted, self.image = False, None
        return {"status_code": 204}


@pytest.fixture
def server(monkeypatch, kit):
    fake = FakeServer()
    import app.services.esxi_boot_workflow as boot

    monkeypatch.setattr(
        service, "_config", lambda session, device_id: SimpleNamespace(host="192.0.2.10")
    )
    monkeypatch.setattr(service, "_policy_blockers", lambda: [])
    monkeypatch.setattr(service, "_read_server", fake.read)
    monkeypatch.setattr(service, "_current_boot_disk", lambda *args: "naa.600508b1001c0000")
    monkeypatch.setattr(service, "_media_url", lambda config, name: f"http://192.0.2.5:8088/{name}")
    monkeypatch.setattr(boot, "_post_virtual_media_action", fake.insert)
    monkeypatch.setattr(boot, "_patch_system_boot", fake.patch)
    monkeypatch.setattr(boot, "_post_system_reset", fake.reset)
    monkeypatch.setattr(boot, "_post_redfish", fake.post)
    monkeypatch.setattr("app.providers.spp_media_server.ensure_media_server", lambda *a: None)

    @contextmanager
    def lease(action):
        fake.sent.append(f"lease:{action}")
        yield {}

    monkeypatch.setattr("app.services.runtime_write_scope.dispatch_lease", lease)

    class Stream:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def raise_for_status(self):
            pass

        def iter_bytes(self, size):
            yield b"derived-installer"

    monkeypatch.setattr("httpx.stream", Stream)
    return fake


def test_install_attaches_boots_once_and_restarts_in_order_then_verifies_ejects_and_creates_the_datastore(
    client, kit, monkeypatch, server, esxi
):
    _ready(client, kit, monkeypatch)
    client.post(kit.base + "/installer" + kit.query)
    started = client.post(kit.base + "/install" + kit.query).json()
    assert started["state"] == "installing", started
    assert [item for item in server.sent if not item.startswith("lease:")] == [
        "media",
        "boot",
        "power:ForceRestart",
    ]
    assert server.sent[0] == "lease:ilo-redfish.esxi-virtual-media"
    # A second start is refused while the run is active.
    assert client.post(kit.base + "/install" + kit.query).status_code == 409
    monkeypatch.setattr(
        service,
        "_esxi_answers",
        lambda ip: {"answering": False, "detail": "Nothing answers on port 443 yet."},
    )
    waiting = client.post(kit.base + "/install/check" + kit.query).json()
    assert waiting["state"] == "installing" and waiting["last_check"]["answering"] is False
    assert "eject" not in server.sent
    monkeypatch.setattr(
        service,
        "_esxi_answers",
        lambda ip: {"answering": True, "detail": "ESXi's API answers on its management address."},
    )
    done = client.post(kit.base + "/install/check" + kit.query).json()
    assert done["state"] == "verified" and done["ejected"] is True and done["verified_at"]
    assert all(check["ok"] for check in done["verification"]["checks"])
    assert done["datastore"] == {"name": "VMdata", "disk": "naa.600508b1001cdata"}
    assert server.sent.count("eject") == 1 and server.sent.count("media") == 1
    assert esxi.created == [("192.0.2.20", "VMdata", "naa.600508b1001cdata")]
    # The root password reached govc only as an argument, never a record or a response.
    assert "Lab-Pass-2026" not in str(client.get(kit.base + "/install" + kit.query).json())


def test_an_unconfirmed_step_stops_the_run_and_is_never_resent(client, kit, monkeypatch, server):
    _ready(client, kit, monkeypatch)
    client.post(kit.base + "/installer" + kit.query)
    server.fail = "media"
    assert client.post(kit.base + "/install" + kit.query).json()["state"] == "needs_attention"
    status = client.get(kit.base + "/install" + kit.query).json()
    assert status["state"] == "needs_attention" and status["phase"] == "media"
    assert server.sent.count("media") == 1 and "boot" not in server.sent
    # Resume only continues once the server shows the step done; it never resends it.
    assert client.post(kit.base + "/install/resume" + kit.query).status_code == 409
    assert server.sent.count("media") == 1
    server.inserted, server.image = True, f"http://192.0.2.5:8088/{status['iso_name']}"
    resumed = client.post(kit.base + "/install/resume" + kit.query).json()
    assert resumed["state"] == "installing"
    assert server.sent.count("media") == 1 and "boot" in server.sent


def test_other_media_already_attached_blocks_before_anything_is_sent(
    client, kit, monkeypatch, server
):
    _ready(client, kit, monkeypatch)
    client.post(kit.base + "/installer" + kit.query)
    server.inserted, server.image = True, "http://elsewhere/other.iso"
    response = client.post(kit.base + "/install" + kit.query)
    assert response.status_code == 409 and "Other virtual media" in response.json()["detail"]
    assert server.sent == []


def test_other_guarded_operation_excludes_esxi_start(client, kit, monkeypatch, server, db_session):
    from app.services.guarded_operation_ledger import reserve

    _ready(client, kit, monkeypatch)
    client.post(kit.base + "/installer" + kit.query)
    reserve(
        db_session,
        profile_id=kit.profile,
        device_id=kit.device,
        resource="firmware-execution",
        idempotency_key="fixture-other",
        reviewed_intent={"fixture": True},
        actor="fixture",
    )
    assert client.post(kit.base + "/install" + kit.query).status_code == 409
    assert not server.sent


def test_phase_cannot_be_claimed_twice(client, kit, monkeypatch, server, db_session):
    _ready(client, kit, monkeypatch)
    client.post(kit.base + "/installer" + kit.query)
    result = client.post(kit.base + "/install" + kit.query).json()
    with pytest.raises(service.EsxiInstallError, match="already claimed"):
        service._send(
            db_session,
            "fixture",
            result["run_id"],
            "power",
            service.ACTION_POWER,
            lambda: server.reset("ForceRestart", None),
        )
    assert server.sent.count("power:ForceRestart") == 1


def test_resume_rejects_replaced_hardware(client, kit, monkeypatch, server):
    _ready(client, kit, monkeypatch)
    client.post(kit.base + "/installer" + kit.query)
    server.fail = "media"
    current = client.post(kit.base + "/install" + kit.query).json()
    server.inserted, server.image = True, f"http://192.0.2.5:8088/{current['iso_name']}"
    monkeypatch.setattr(
        service,
        "_read_server",
        lambda config: {**server.read(config), "hardware_identity": "replacement"},
    )
    assert client.post(kit.base + "/install/resume" + kit.query).status_code == 409
    assert server.sent.count("media") == 1 and "boot" not in server.sent


def test_changed_boot_disk_prevents_any_send(client, kit, monkeypatch, server):
    _ready(client, kit, monkeypatch)
    client.post(kit.base + "/installer" + kit.query)
    monkeypatch.setattr(service, "_current_boot_disk", lambda *args: "naa.different")
    response = client.post(kit.base + "/install" + kit.query)
    assert response.status_code == 409 and "boot mirror changed" in response.json()["detail"]
    assert not server.sent


def test_lost_eject_is_not_resent_or_marked_complete(client, kit, monkeypatch, server, esxi):
    _ready(client, kit, monkeypatch)
    client.post(kit.base + "/installer" + kit.query)
    client.post(kit.base + "/install" + kit.query)
    monkeypatch.setattr(service, "_esxi_answers", lambda ip: {"answering": True})

    def lose_eject(*args, **kwargs):
        server.sent.append("eject")
        raise TimeoutError("fixture")

    monkeypatch.setattr("app.services.esxi_boot_workflow._post_redfish", lose_eject)
    response = client.post(kit.base + "/install/check" + kit.query).json()
    assert response["state"] == "needs_attention" and response["active"]
    client.post(kit.base + "/install/check" + kit.query)
    assert server.sent.count("eject") == 1
    server.inserted = False
    response = client.post(kit.base + "/install/resume" + kit.query).json()
    assert response["state"] == "reachable" and not response["active"]
    assert server.sent.count("eject") == 1


def test_late_result_cannot_reopen_a_claimed_later_phase(db_session):
    from app.models import GuardedOperation
    from app.services.guarded_operation_ledger import reserve

    operation = reserve(
        db_session,
        profile_id="fixture",
        device_id="fixture-device",
        resource="esxi-install",
        idempotency_key="late-result",
        reviewed_intent={"fixture": True},
        actor="fixture",
    )
    operation.status = "esxi-sent-boot"
    db_session.commit()
    service._record(
        db_session,
        "fixture",
        "kit.esxi_install.result",
        "Late media readback.",
        {"run_id": operation.id, "phase": "media", "outcome": "ok"},
    )
    assert (
        db_session.get(GuardedOperation, operation.id, populate_existing=True).status
        == "esxi-sent-boot"
    )


def test_interrupted_admission_is_visible_and_can_be_closed_without_sending(db_session):
    from app.services.guarded_operation_ledger import reserve

    operation = reserve(
        db_session,
        profile_id="fixture",
        device_id="fixture-device",
        resource="esxi-install",
        idempotency_key="interrupted",
        reviewed_intent={"fixture": True},
        actor="fixture",
    )
    current = service.install_status(db_session, "fixture", "fixture-device")
    assert current["phase"] == "admission" and current["run_id"] == operation.id
    with pytest.raises(service.EsxiInstallError, match="before dispatch"):
        service.resume_install(db_session, "fixture", "fixture-device", "fixture")
    assert not service.cancel_install(db_session, "fixture", "fixture-device", "fixture")["active"]


class FakeEsxi:
    """A freshly installed host as govc reads it, signed in with the saved root password."""

    def __init__(self):
        self.facts = {
            "product": "VMware ESXi",
            "version": "8.0.3",
            "build": "24859861",
            "fqdn": "esxi01.lab.example",
            "vmk0": {"ip": "192.0.2.20", "netmask": "255.255.255.0", "type": "STATIC"},
            "management_vlan": "0",
            "partitions": {"naa.600508b1001c0000": 8},
            "datastores": [],
        }
        self.created = []
        self.passwords = set()
        self.fail_create = False

    def host_facts(self, ip, password):
        self.passwords.add(password)
        return {
            **self.facts,
            "partitions": dict(self.facts["partitions"]),
            "datastores": list(self.facts["datastores"]),
        }

    def create(self, ip, password, name, disk):
        self.created.append((ip, name, disk))
        if self.fail_create:
            raise RuntimeError("lost")
        self.facts["datastores"].append({"name": name, "disk": disk})


@pytest.fixture
def esxi(monkeypatch):
    fake = FakeEsxi()
    monkeypatch.setattr("app.providers.esxi_govc.host_facts", fake.host_facts)
    monkeypatch.setattr("app.providers.esxi_govc.create_vmfs_datastore", fake.create)
    monkeypatch.setattr(
        service, "_esxi_answers", lambda ip: {"answering": True, "detail": "ESXi's API answers."}
    )
    return fake


def _started(client, kit, monkeypatch):
    _ready(client, kit, monkeypatch)
    client.post(kit.base + "/installer" + kit.query)
    return client.post(kit.base + "/install" + kit.query).json()


def test_a_host_that_does_not_match_the_plan_is_never_ejected_or_formatted(
    client, kit, monkeypatch, server, esxi
):
    _started(client, kit, monkeypatch)
    esxi.facts["fqdn"] = "localhost.localdomain"
    esxi.facts["management_vlan"] = "120"
    status = client.post(kit.base + "/install/check" + kit.query).json()
    assert status["state"] == "installing" and status["verification"]["passed"] is False
    failed = {check["name"] for check in status["verification"]["checks"] if not check["ok"]}
    assert failed == {"Host name", "Management VLAN"}
    assert "eject" not in server.sent and esxi.created == []
    assert esxi.passwords == {"Lab-Pass-2026"}


def test_datastore_is_created_once_and_an_unknown_outcome_is_confirmed_not_resent(
    client, kit, monkeypatch, server, esxi
):
    _started(client, kit, monkeypatch)
    esxi.fail_create = True
    status = client.post(kit.base + "/install/check" + kit.query).json()
    assert status["state"] == "needs_attention" and status["phase"] == "datastore"
    client.post(kit.base + "/install/check" + kit.query)
    assert len(esxi.created) == 1
    # ESXi does not show it: resume refuses and nothing is re-sent.
    assert client.post(kit.base + "/install/resume" + kit.query).status_code == 409
    esxi.facts["datastores"].append({"name": "VMdata", "disk": "naa.600508b1001cdata"})
    resumed = client.post(kit.base + "/install/resume" + kit.query).json()
    assert resumed["state"] == "verified" and resumed["datastore"]["name"] == "VMdata"
    assert len(esxi.created) == 1


def test_a_data_volume_with_partitions_is_never_formatted_and_the_verified_host_can_be_closed(
    client, kit, monkeypatch, server, esxi
):
    _started(client, kit, monkeypatch)
    esxi.facts["partitions"]["naa.600508b1001cdata"] = 2
    status = client.post(kit.base + "/install/check" + kit.query).json()
    assert status["state"] == "needs_attention" and status["phase"] == "datastore"
    assert esxi.created == [] and "not formatted" in status["message"]
    closed = client.post(kit.base + "/install/close" + kit.query).json()
    assert closed["state"] == "verified" and closed["datastore"] is None


def test_dhcp_install_builds_a_dhcp_kickstart_and_verifies_at_the_reported_address(
    client, kit, monkeypatch, server, esxi
):
    import hashlib

    monkeypatch.setitem(kit.context["resolved_address_plan"], "esxi_management", None)
    _iso(kit.media / "VMware-ESXi-8.0.3-24859861.iso")
    client.post(kit.base + "/media" + kit.query, json={"path": "VMware-ESXi-8.0.3-24859861.iso"})
    saved = client.put(
        kit.base + "/settings" + kit.query,
        json={"hostname": "esxi01.lab.example", "addressing": "dhcp", "vlan_id": 0,
              "management_nic": "vmnic0", "root_password": "Lab-Pass-2026"},
    ).json()
    assert saved["addressing"] == "dhcp" and saved["management_ip"] is None
    seen = {}
    built = kit.tmp / "derived.iso"
    built.write_bytes(b"derived-installer")

    def fake_builder(request, **kwargs):
        seen.update(request=request)
        return {"status": "ready", "derived_artifact": {
            "iso": str(built), "iso_sha256": hashlib.sha256(b"derived-installer").hexdigest(),
            "iso_size_bytes": built.stat().st_size, "kickstart_sha256": "k" * 64}}

    monkeypatch.setattr("app.services.esxi_installer_artifact.prepare_esxi_installer_artifact", fake_builder)
    assert client.post(kit.base + "/installer" + kit.query).json()["status"] == "ready"
    request = seen["request"]
    assert request["bootproto"] == "dhcp" and request["management_ip"] is None and request["gateway"] is None
    assert client.post(kit.base + "/install" + kit.query).json()["state"] == "installing"
    # The iLO has not reported an address yet: the run waits and says so.
    monkeypatch.setattr(service, "_discover_address", lambda *args: None)
    waiting = client.post(kit.base + "/install/check" + kit.query).json()
    assert waiting["state"] == "installing" and "DHCP address" in waiting["last_check"]["detail"]
    # An address typed from the server screen is used as-is.
    esxi.facts["vmk0"] = {"ip": "192.0.2.77", "netmask": "255.255.255.0", "type": "DHCP"}
    done = client.post(kit.base + "/install/check" + kit.query, json={"address": "192.0.2.77"}).json()
    assert done["state"] == "verified" and done["management_ip"] == "192.0.2.77"


def test_dhcp_kickstart_sets_the_name_at_first_boot():
    from app.services import esxi_installer_artifact as artifact

    payload = {
        "profile_id": "kit", "profile_version": 1, "profile_fingerprint": "a" * 64,
        "source_iso_path": "/x.iso", "expected_source_iso_sha256": "b" * 64,
        "hostname": "esxi01.lab.example", "bootproto": "dhcp", "subnet_cidr": "192.0.2.0/24",
        "dns_servers": ["192.0.2.53"], "ntp_servers": [], "management_nic": "vmnic0",
        "management_vlan_id": 0, "install_disk_id": "naa.600508b1001c0000", "system_media_size": "default",
        "root_password_sha512_crypt": "$6$saltsalt$" + "a" * 86, "secure_boot_expected": False,
        "allow_firstboot_network_services": True, "local_datastore_expected": True,
        "acknowledge_install_disk_overwrite": True,
    }
    text = artifact._render_kickstart(artifact.EsxiInstallerArtifactRequest.model_validate(payload))
    assert "network --bootproto=dhcp --device=vmnic0 --addvmportgroup=1" in text
    assert "--ip=" not in text and "--hostname" not in text
    assert "localcli system hostname set --fqdn=esxi01.lab.example" in text
    # DHCP with a fixed address is contradictory and refused.
    with pytest.raises(Exception):
        artifact.EsxiInstallerArtifactRequest.model_validate({**payload, "management_ip": "192.0.2.20"})
    # A port chosen by its MAC goes to the kickstart as-is; ESXi accepts either form.
    by_mac = artifact._render_kickstart(artifact.EsxiInstallerArtifactRequest.model_validate({**payload, "management_nic": "02:00:00:00:00:02"}))
    assert "--device=02:00:00:00:00:02" in by_mac


def test_boot_waits_for_post_to_finish_before_asking_the_ilo(client, kit, monkeypatch, server):
    _ready(client, kit, monkeypatch)
    client.post(kit.base + "/installer" + kit.query)
    monkeypatch.setattr(service.time, "sleep", lambda seconds: None)
    # Read after media, then twice still in POST while waiting.
    server.post_states = ["FinishedPost", "FinishedPost", "InPost", "InPostDiscoveryComplete"]
    started = client.post(kit.base + "/install" + kit.query).json()
    assert started["state"] == "installing", started
    assert server.sent.count("boot") == 1 and "power:ForceRestart" in server.sent


def test_a_refused_boot_shows_the_ilo_reason_and_is_sent_again_only_on_request(client, kit, monkeypatch, server):
    _ready(client, kit, monkeypatch)
    client.post(kit.base + "/installer" + kit.query)
    server.fail = "boot-refused"
    status = client.post(kit.base + "/install" + kit.query).json()
    assert status["state"] == "needs_attention" and status["phase"] == "boot"
    assert "UnableToModifyDuringSystemPOST" in status["message"]
    assert server.sent.count("boot") == 1 and not any(item.startswith("power") for item in server.sent)
    # The iLO applied nothing, so checking again sends the approved boot step once more.
    resumed = client.post(kit.base + "/install/resume" + kit.query).json()
    assert resumed["state"] == "installing", resumed
    assert server.sent.count("boot") == 2 and server.sent.count("media") == 1
    assert "power:ForceRestart" in server.sent


def test_a_host_that_installed_itself_after_a_refused_boot_is_proven_then_cleaned_up(
    client, kit, monkeypatch, server, esxi
):
    _ready(client, kit, monkeypatch)
    client.post(kit.base + "/installer" + kit.query)
    server.fail = "boot-refused"
    stuck = client.post(kit.base + "/install" + kit.query).json()
    assert stuck["state"] == "needs_attention" and stuck["can_check_installed"] is True
    # A host that does not match proves nothing: no phase is marked done, nothing is ejected.
    esxi.facts["fqdn"] = "other.lab.example"
    still = client.post(kit.base + "/install/check" + kit.query).json()
    assert still["state"] == "needs_attention" and still["verification"]["passed"] is False
    assert "eject" not in server.sent and esxi.created == []
    esxi.facts["fqdn"] = "esxi01.lab.example"
    done = client.post(kit.base + "/install/check" + kit.query).json()
    assert done["state"] == "verified", done
    assert done["phases"]["boot"] == "ok" and done["phases"]["power"] == "ok"
    # The boot and restart were never sent again; only the eject and the datastore followed.
    assert server.sent.count("boot") == 1 and not any(item.startswith("power") for item in server.sent)
    assert server.sent.count("eject") == 1 and esxi.created == [("192.0.2.20", "VMdata", "naa.600508b1001cdata")]



def _dhcp_run_with_refused_boot(client, kit, monkeypatch, server):
    monkeypatch.setitem(kit.context["resolved_address_plan"], "esxi_management", None)
    _ready(client, kit, monkeypatch)
    client.put(kit.base + "/settings" + kit.query, json={
        "hostname": "esxi01.lab.example", "addressing": "dhcp", "vlan_id": 0,
        "management_nic": "vmnic0", "root_password": "Lab-Pass-2026"})
    assert client.post(kit.base + "/installer" + kit.query).json()["status"] == "ready"
    server.fail = "boot-refused"
    assert client.post(kit.base + "/install" + kit.query).json()["can_check_installed"] is True


def test_a_self_assigned_address_is_explained_with_the_cabled_port_and_never_signed_in(
    client, kit, monkeypatch, server, esxi
):
    _dhcp_run_with_refused_boot(client, kit, monkeypatch, server)
    monkeypatch.setattr(service, "_network_ports", lambda session, device_id: PORTS)
    monkeypatch.setattr(service, "_esxi_answers", lambda ip: pytest.fail("a link-local address is never contacted"))
    status = client.post(kit.base + "/install/check" + kit.query, json={"address": "169.254.97.119"}).json()
    detail = status["last_check"]["detail"]
    assert "no DHCP server answered on vmnic0" in detail and "only on vmnic1" in detail
    assert status["verification"] is None and esxi.passwords == set()


def test_an_address_set_on_the_console_inside_the_kit_subnet_is_accepted_for_a_dhcp_plan(
    client, kit, monkeypatch, server, esxi
):
    _dhcp_run_with_refused_boot(client, kit, monkeypatch, server)
    subnet = kit.context["resolved_address_plan"]["subnet"]
    inside = str(next(__import__("ipaddress").ip_network(subnet, strict=False).hosts()))
    outside = "198.51.100.9"
    esxi.facts["vmk0"] = {"ip": outside, "netmask": "255.255.255.0", "type": "STATIC"}
    refused = client.post(kit.base + "/install/check" + kit.query, json={"address": outside}).json()
    assert refused["verification"]["passed"] is False and "eject" not in server.sent
    esxi.facts["vmk0"] = {"ip": inside, "netmask": "255.255.255.0", "type": "STATIC"}
    done = client.post(kit.base + "/install/check" + kit.query, json={"address": inside}).json()
    assert done["state"] == "verified" and done["management_ip"] == inside


PORTS = [
    {"mac": "02:00:00:00:00:01", "adapter": "HPE Ethernet 1Gb 4-port 331i Adapter", "location": "Embedded LOM",
     "port": 1, "link": False, "speed_mbps": None, "vmnic": "vmnic0"},
    {"mac": "02:00:00:00:00:02", "adapter": "HPE Ethernet 1Gb 4-port 331i Adapter", "location": "Embedded LOM",
     "port": 2, "link": True, "speed_mbps": 1000, "vmnic": "vmnic1"},
]


def test_network_ports_come_from_the_ilo_and_a_cabled_built_in_port_is_suggested(client, kit, monkeypatch):
    import app.services.esxi_boot_workflow as boot

    monkeypatch.setattr(service, "_config", lambda session, device_id: SimpleNamespace(host="192.0.2.10"))
    resources = {
        "/redfish/v1/Systems/1/BaseNetworkAdapters/": {"Members": [{"@odata.id": "/a/1"}, {"@odata.id": "/a/2"}]},
        "/a/1": {"Name": "Broadcom NetXtreme-E Quad 25Gb SFP28 PCIe Ethernet - NIC", "StructuredName": "NIC.Slot.3.1",
                 "PhysicalPorts": [{"MacAddress": "02-00-00-00-01-01", "LinkStatus": "LinkUp", "SpeedMbps": 25000}]},
        "/a/2": {"Name": "HPE Ethernet 1Gb 4-port 331i Adapter - NIC", "Location": "Embedded LOM", "PhysicalPorts": [
            {"MacAddress": "02:00:00:00:00:01", "LinkStatus": None, "Oem": {"Hpe": {"PortNumber": 1}}},
            {"MacAddress": "02:00:00:00:00:02", "LinkStatus": "LinkUp", "SpeedMbps": 1000, "Name": "vmnic1",
             "Oem": {"Hpe": {"PortNumber": 2}}}]},
    }
    monkeypatch.setattr(boot, "_get_redfish_resource", lambda path, config: resources[path])
    monkeypatch.setattr(boot, "_body", lambda response: response)
    listed = client.get(kit.base + "/network-ports" + kit.query).json()
    assert listed["available"] is True and listed["suggested"] == "02:00:00:00:00:02"
    assert [(port["location"], port["port"], port["link"], port["vmnic"]) for port in listed["ports"]] == [
        ("NIC.Slot.3.1", 1, True, None), ("Embedded LOM", 1, False, None), ("Embedded LOM", 2, True, "vmnic1")]
    assert listed["ports"][0]["adapter"] == "Broadcom NetXtreme-E Quad 25Gb SFP28 PCIe Ethernet"


def test_settings_accept_a_port_by_mac_and_refuse_anything_else(client, kit, monkeypatch):
    _iso(kit.media / "VMware-ESXi-8.0.3-24859861.iso")
    saved = client.put(kit.base + "/settings" + kit.query, json={
        "hostname": "esxi01.lab.example", "management_ip": "192.0.2.20", "vlan_id": 0,
        "management_nic": "02-00-00-00-00-02", "root_password": "Lab-Pass-2026"}).json()
    assert saved["management_nic"] == "02:00:00:00:00:02"
    bad = client.put(kit.base + "/settings" + kit.query, json={
        "hostname": "esxi01.lab.example", "management_ip": "192.0.2.20", "management_nic": "eth0; reboot"})
    assert bad.status_code in {409, 422}


def test_dhcp_accepts_the_domain_dhcp_supplies_but_not_a_different_host_name(client, kit, monkeypatch, server, esxi):
    _dhcp_run_with_refused_boot(client, kit, monkeypatch, server)
    esxi.facts["vmk0"] = {"ip": "192.0.2.77", "netmask": "255.255.255.0", "type": "DHCP"}
    esxi.facts["fqdn"] = "esxi02.dhcp.example"
    other = client.post(kit.base + "/install/check" + kit.query, json={"address": "192.0.2.77"}).json()
    assert other["verification"]["passed"] is False and "eject" not in server.sent
    esxi.facts["fqdn"] = "esxi01.dhcp.example"
    done = client.post(kit.base + "/install/check" + kit.query, json={"address": "192.0.2.77"}).json()
    assert done["state"] == "verified", done
    host = next(check for check in done["verification"]["checks"] if check["name"] == "Host name")
    assert host["found"] == "esxi01.dhcp.example (domain from DHCP)"


def test_a_static_install_still_needs_the_exact_host_name():
    run = {"addressing": "static", "hostname": "esxi01.lab.example", "management_ip": "192.0.2.20",
           "netmask": "255.255.255.0", "install_disk_id": "naa.1"}
    facts = {"fqdn": "esxi01.other.example", "vmk0": {}, "partitions": {}}
    host = next(c for c in service._verification_checks(run, facts, "192.0.2.20") if c["name"] == "Host name")
    assert host["ok"] is False


def test_a_datastore_create_that_left_the_disk_empty_is_sent_again_once_it_has_settled(
    client, kit, monkeypatch, server, esxi
):
    _started(client, kit, monkeypatch)
    esxi.fail_create = True
    assert client.post(kit.base + "/install/check" + kit.query).json()["phase"] == "datastore"
    # Straight away: too early to know, nothing is resent.
    assert client.post(kit.base + "/install/resume" + kit.query).status_code == 409
    assert len(esxi.created) == 1
    esxi.fail_create = False
    monkeypatch.setattr(service, "DATASTORE_SETTLE", timedelta(seconds=-1))
    done = client.post(kit.base + "/install/resume" + kit.query).json()
    assert done["state"] == "verified" and done["datastore"]["name"] == "VMdata"
    assert len(esxi.created) == 2


def test_a_data_disk_with_partitions_after_a_lost_create_is_not_formatted_again(client, kit, monkeypatch, server, esxi):
    _started(client, kit, monkeypatch)
    esxi.fail_create = True
    client.post(kit.base + "/install/check" + kit.query)
    esxi.facts["partitions"]["naa.600508b1001cdata"] = 1
    monkeypatch.setattr(service, "DATASTORE_SETTLE", timedelta(seconds=-1))
    response = client.post(kit.base + "/install/resume" + kit.query)
    assert response.status_code == 409 and "partitions" in response.json()["detail"]
    assert len(esxi.created) == 1
