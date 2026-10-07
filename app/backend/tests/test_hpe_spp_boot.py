"""Transport boundary tests; all Redfish and media calls are isolated fixtures."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.providers.hpe_spp_boot import OfflineTransport, qualify_configs, CommandNotSent
from app.providers.hpe_firmware_inventory import _hardware_identity
from app.providers.ilo_redfish import _resource_summary, ilo_target_fingerprint
from app.services import esxi_boot_workflow as boot
from app.services.firmware_packages import FirmwarePackageError


@pytest.fixture
def transport(monkeypatch):
    subject = OfflineTransport()
    config = SimpleNamespace(host="192.0.2.10")
    system = {
        "UUID": "fixture-uuid",
        "SerialNumber": "fixture-serial",
        "PowerState": "On",
        "Boot": {"BootSourceOverrideEnabled": "Once", "BootSourceOverrideTarget": "Cd"},
    }
    media = {
        "Inserted": True,
        "Image": "http://192.0.2.20/fixture.iso",
        "Actions": {
            "#VirtualMedia.EjectMedia": {
                "target": "/redfish/v1/Managers/1/VirtualMedia/2/Actions/VirtualMedia.EjectMedia"
            }
        },
    }
    facts = {
        "profile_id": "kit",
        "hardware_identity": _hardware_identity({"systems": [_resource_summary(system)]}),
        "endpoint_identity": ilo_target_fingerprint(config.host),
        "component_identity": "drives",
        "package_sha256": "iso",
        "boot_profile": "boot",
        "media_url": media["Image"],
        "media_device": {
            "path": "/redfish/v1/Managers/1/VirtualMedia/2",
            "insert_target": "/redfish/v1/Managers/1/VirtualMedia/2/Actions/VirtualMedia.InsertMedia",
        },
        "post_timestamp": "2026-01-01T00:00:00Z",
        "media_inserted": True,
        "media_image": media["Image"],
        "boot_override": system["Boot"],
        "update_idle": True,
        "expected": [{"component": "ROM", "target": "3.66", "kind": "numeric"}],
        "rows": [{"component": "ROM", "installed": "U32 v3.66"}],
    }
    monkeypatch.setattr(subject, "_config", lambda *args: config)
    monkeypatch.setattr(
        boot,
        "_get_redfish_resource",
        lambda path, **kw: {"body": system if path == boot.SYSTEM_PATH else media},
    )
    monkeypatch.setattr(subject, "capture", lambda *args: deepcopy(facts))
    return subject, system, media, facts


@pytest.mark.parametrize("power,command", [("On", "ForceRestart"), ("Off", "On")])
def test_reset_uses_raw_system_hardware_identity_and_exact_power_command(
    transport, monkeypatch, power, command
):
    subject, system, _, facts = transport
    system["PowerState"] = power
    calls = []
    monkeypatch.setattr(
        boot, "_post_system_reset", lambda value, **kw: calls.append(value) or {"status_code": 202}
    )
    subject.dispatch(None, "srv", facts, "reset")
    assert calls == [command]
    system["SerialNumber"] = "another-server"
    with pytest.raises(CommandNotSent):
        subject.dispatch(None, "srv", facts, "reset")
    assert calls == [command]


def test_boot_sends_only_once_cd_and_requires_readback(transport, monkeypatch):
    subject, system, _, facts = transport
    calls = []
    monkeypatch.setattr(
        boot, "_patch_system_boot", lambda value, **kw: calls.append(value) or {"status_code": 200}
    )
    subject.dispatch(None, "srv", facts, "boot")
    assert calls == [
        {"Boot": {"BootSourceOverrideEnabled": "Once", "BootSourceOverrideTarget": "Cd"}}
    ]
    system["Boot"]["BootSourceOverrideEnabled"] = "Continuous"
    with pytest.raises(FirmwarePackageError, match="not yet confirmed"):
        subject.dispatch(None, "srv", facts, "boot")


def test_eject_never_removes_someone_elses_media(transport, monkeypatch):
    subject, _, media, facts = transport
    calls = []
    monkeypatch.setattr(
        boot, "_post_redfish", lambda *args, **kw: calls.append(args) or {"status_code": 204}
    )
    media["Image"] = "http://192.0.2.20/other.iso"
    with pytest.raises(CommandNotSent):
        subject.dispatch(None, "srv", facts, "eject")
    assert not calls
    media["Inserted"] = False
    assert subject.dispatch(None, "srv", facts, "eject")["already_disconnected"]
    assert not calls


@pytest.mark.parametrize(
    "post", [None, "bad", "2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "2026-01-01T01:00:00"]
)
def test_reset_reconciliation_needs_a_later_timezone_aware_post(transport, post):
    subject, _, _, facts = transport
    original = deepcopy(facts)
    facts["post_timestamp"] = post
    facts["boot_override"]["BootSourceOverrideEnabled"] = "Disabled"
    assert not subject.reconcile_phase(None, "srv", original, "reset")["applied"]


def test_reconcile_reset_requires_our_media_and_same_components(transport):
    subject, _, _, facts = transport
    original = deepcopy(facts)
    facts["post_timestamp"] = "2026-01-01T00:01:00Z"
    facts["boot_override"]["BootSourceOverrideEnabled"] = "Disabled"
    assert subject.reconcile_phase(None, "srv", original, "reset")["applied"]
    facts["media_inserted"] = False
    assert not subject.reconcile_phase(None, "srv", original, "reset")["applied"]
    facts["media_inserted"] = True
    facts["component_identity"] = "different-drives"
    assert not subject.reconcile_phase(None, "srv", original, "reset")["applied"]


def test_eject_preflight_requires_current_versions_not_an_old_success(transport):
    subject, _, _, facts = transport
    original = deepcopy(facts)
    subject.preflight(None, "srv", original, "eject")
    facts["rows"][0]["installed"] = "1.46"
    with pytest.raises(FirmwarePackageError, match="not currently verified"):
        subject.preflight(None, "srv", original, "eject")


def test_unknown_generation_or_modified_boot_profile_not_assumed_supported():
    with pytest.raises(FirmwarePackageError, match="separately supported"):
        qualify_configs({}, 7)
    with pytest.raises(FirmwarePackageError, match="qualified automatic boot"):
        qualify_configs({}, 5)


def test_unreachable_iso_is_proven_unsent(transport, monkeypatch, tmp_path):
    from app.providers import hpe_spp_boot

    subject, _, _, facts = transport
    facts.update(media_path="fixture.iso", selected_package={"size_bytes": 10})
    monkeypatch.setenv("SPP_MEDIA_BASE_URL", "http://192.0.2.20")
    monkeypatch.setattr(hpe_spp_boot, "media_path", lambda path: tmp_path / path)
    monkeypatch.setattr(hpe_spp_boot, "package_hash", lambda package: "iso")
    monkeypatch.setattr(boot, "_validate_media_url", lambda *args: {"reachable": False})
    calls = []
    monkeypatch.setattr(boot, "_post_virtual_media_action", lambda *args, **kw: calls.append(args))
    with pytest.raises(CommandNotSent):
        subject.dispatch(None, "srv", facts, "media")
    assert not calls


def test_send_timeout_is_never_classified_as_unsent(transport, monkeypatch):
    subject, _, _, facts = transport

    def lose_response(*args, **kwargs):
        raise TimeoutError("lost fixture response")

    monkeypatch.setattr(boot, "_post_system_reset", lose_response)
    with pytest.raises(TimeoutError):
        subject.dispatch(None, "srv", facts, "reset")


@pytest.mark.parametrize("phase", ["boot", "reset"])
def test_preflight_will_not_boot_without_the_reviewed_iso(transport, phase):
    subject, _, _, facts = transport
    original = deepcopy(facts)
    facts["media_inserted"] = False
    with pytest.raises(FirmwarePackageError, match="no longer mounted"):
        subject.preflight(None, "srv", original, phase)


def test_preflight_will_not_restart_with_changed_boot_selection(transport):
    subject, _, _, facts = transport
    original = deepcopy(facts)
    facts["boot_override"]["BootSourceOverrideTarget"] = "Hdd"
    with pytest.raises(FirmwarePackageError, match="no longer selected"):
        subject.preflight(None, "srv", original, "reset")


def test_capture_normalizes_raw_and_probe_identity_consistently(transport, monkeypatch, tmp_path):
    from contextlib import nullcontext
    from app.api import firmware_review
    from app.providers import hpe_spp_boot, hpe_firmware_inventory, hpe_storage_rebuild, ilo_redfish
    from app.services import firmware_flow, spp_assessment

    subject, system, media, facts = transport
    monkeypatch.delattr(subject, "capture")
    system.update(
        Model="Fixture Gen10",
        Oem={"Hpe": {"PostDiscoveryCompleteTimeStamp": facts["post_timestamp"]}},
    )
    monkeypatch.setattr(
        firmware_review,
        "server_in_kit",
        lambda *args: SimpleNamespace(model="Fixture Gen10", name="Fixture server"),
    )
    package = {"path": "fixture.iso", "file_name": "fixture.iso"}
    monkeypatch.setattr(
        firmware_flow, "_latest", lambda *args: SimpleNamespace(data_json={"package": package})
    )
    monkeypatch.setattr(hpe_spp_boot, "package_unchanged", lambda p: True)
    monkeypatch.setattr(hpe_spp_boot, "package_hash", lambda p: "iso-hash")
    monkeypatch.setattr(hpe_spp_boot, "media_path", lambda p: tmp_path / p)
    monkeypatch.setattr(
        hpe_spp_boot,
        "inspect_boot_profile",
        lambda *args: SimpleNamespace(configuration_sha256="boot-hash", release="2026.05.00.00"),
    )
    monkeypatch.setattr(
        ilo_redfish,
        "IloRedfishAdapter",
        lambda **kw: SimpleNamespace(
            probe=lambda: {
                "status": "ok",
                "systems": [_resource_summary(system)],
                "managers": [{"Model": "iLO 5", "FirmwareVersion": "iLO 5 v3.19"}],
            }
        ),
    )
    monkeypatch.setattr(spp_assessment, "load_catalog", lambda p: {})
    monkeypatch.setattr(
        spp_assessment,
        "assess",
        lambda *args: {
            "rom_family": "U32",
            "detected_model": "Fixture Gen10",
            "rows": [
                {
                    "component": "ROM",
                    "installed": "1.46",
                    "target": "3.66",
                    "status": "Update available",
                },
            ],
        },
    )
    monkeypatch.setattr(hpe_storage_rebuild, "client_for", lambda c: nullcontext(object()))
    monkeypatch.setattr(
        hpe_firmware_inventory,
        "discover_update_service",
        lambda *args: {"state": "Idle", "errors": []},
    )
    monkeypatch.setattr(boot, "_select_virtual_media_device", lambda **kw: facts["media_device"])
    monkeypatch.setenv("SPP_MEDIA_BASE_URL", "http://192.0.2.20:8088")
    result = subject.capture(None, "kit", "srv")
    assert result["hardware_identity"] == facts["hardware_identity"]
    assert result["server"]["manager_generation"] == 5 and result["update_idle"]
    assert result["expected"][0]["target"] == "3.66"
    assert result["media_url"] == "http://192.0.2.20:8088/fixture.iso"
