"""Contract orchestration tests: every equipment boundary is replaced, never run."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import AuditEvent
from app.services import kit_contract as service
from app.services.audit import record_audit_event

P = "fixture"
D = "server-fixture"


@pytest.fixture
def lab(monkeypatch, db_session):
    from app.api import disk_preparation, raid_rebuild, routes
    from app.services import ilo_access_settings, spp_update_runtime

    items = [
        {
            "id": f"{step}:{D}",
            "step": step,
            "device_id": D,
            "title": service.TITLES[step],
            "desired": {},
            "href": service.LINKS[step],
        }
        for step in service.ORDER
    ]
    desired = {
        "profile_id": P,
        "kit": "Fixture kit",
        "network": {"gateway": "192.0.2.1"},
        "items": items,
    }
    monkeypatch.setattr(service, "_desired", lambda session, p: deepcopy(desired))
    states = {
        step: {"state": "not_started", "active": False, "message": ""} for step in service.ORDER
    }
    calls, scopes = [], []
    scope = {"scope": "read_only"}

    def active(session):
        return [v for v in states.values() if v.get("active")]

    monkeypatch.setattr(service.runtime_write_scope, "active_operations", active)
    monkeypatch.setattr(service.runtime_write_scope, "state", lambda session: scope)

    def preview(session, actor, target):
        calls.append(("scope-preview", target))
        return {"blockers": [], "review_token": target, "confirmation_phrase": "fixture"}

    def apply(session, actor, token, phrase):
        assert phrase == "fixture"
        scopes.append(token)
        scope["scope"] = token

    monkeypatch.setattr(service.runtime_write_scope, "preview", preview)
    monkeypatch.setattr(service.runtime_write_scope, "apply", apply)

    def start(step):
        def run(*args, **kwargs):
            calls.append(("start", step))
            states[step].update(state="running", active=True)
            return deepcopy(states[step])

        return run

    def advance(step):
        def run(*args, **kwargs):
            calls.append(("advance", step))
            states[step].update(state="verified", active=False)
            return deepcopy(states[step])

        return run

    for step, module, status_name, start_name, advance_name in (
        ("switch", service.switch_setup, "status", "start", "advance"),
        ("firmware", service.parts_update, "status", "start", "advance"),
        ("esxi", service.esxi_install, "install_status", "start_install", "check_install"),
        ("windows", service.windows_deploy, "status", "start", "advance"),
        ("acceptance", service.acceptance, "status", "start", "advance"),
    ):
        monkeypatch.setattr(module, status_name, lambda *a, step=step, **k: deepcopy(states[step]))
        monkeypatch.setattr(module, start_name, start(step))
        monkeypatch.setattr(module, advance_name, advance(step))
    states["acceptance"]["signin"] = {"password_saved": True}
    monkeypatch.setattr(
        service.switch_setup, "review", lambda *a: {"blockers": [], "replace_needed": False}
    )
    monkeypatch.setattr(
        service.windows_deploy, "review", lambda *a: {"blockers": [], "ready": True}
    )
    monkeypatch.setattr(
        service.esxi_install, "build_status", lambda *a: {"status": "ready", "blockers": []}
    )
    monkeypatch.setattr(
        service.esxi_install,
        "build_installer",
        lambda *a: pytest.fail("Unexpected installer build"),
    )
    monkeypatch.setattr(service.parts_update, "review", lambda *a: {"parts": [], "blockers": []})
    monkeypatch.setattr(
        spp_update_runtime,
        "recorded_status",
        lambda *a, **k: {"status": "verified", "active": False},
    )
    monkeypatch.setattr(service, "_spp_backend", lambda: object())
    monkeypatch.setattr(spp_update_runtime, "plan", lambda *a: {"updates": [], "blockers": []})
    monkeypatch.setattr(
        spp_update_runtime, "submit", lambda *a: pytest.fail("Unexpected SPP submit")
    )

    def access(*a):
        return {
            "last_probe_status": "ok"
            if states["connect"]["state"] == "verified"
            else "not_checked",
            "last_probe_time": datetime.now(UTC).isoformat(),
            "last_probe_is_current": True,
            "last_probe_target_matches_access_host": True,
        }

    monkeypatch.setattr(ilo_access_settings, "read_ilo_access_settings", access)

    def probe(*a):
        calls.append(("start", "connect"))
        states["connect"].update(state="verified")
        return {"status": "ok"}

    monkeypatch.setattr(routes, "probe_provider", probe)
    monkeypatch.setattr(
        raid_rebuild,
        "rebuild_status",
        lambda *a: {
            **deepcopy(states["raid"]),
            "status": states["raid"]["state"],
            "operation": "create",
        },
    )
    view = {"volumes": [], "blockers": []}
    monkeypatch.setattr(disk_preparation, "disk_preparation", lambda *a: deepcopy(view))
    review = {
        "blockers": [],
        "apply_enabled": True,
        "preview_id": "00000000-0000-0000-0000-000000000000",
        "confirmation": "fixture",
        "empty_bays": [],
    }
    for name in ("preview_rebuild", "preview_boot", "preview_shutdown"):
        monkeypatch.setattr(raid_rebuild, name, lambda *a: deepcopy(review))
    monkeypatch.setattr(raid_rebuild, "read_reset_power", lambda *a: {"power": "Off"})

    def raid_start(*a):
        calls.append(("start", "raid"))
        states["raid"].update(state="staged", active=True)

    monkeypatch.setattr(raid_rebuild, "apply_rebuild", raid_start)

    def boot(*a):
        calls.append(("boot", "raid"))
        states["raid"].update(state="waiting")

    monkeypatch.setattr(raid_rebuild, "apply_boot", boot)
    monkeypatch.setattr(raid_rebuild, "verify_rebuild", advance("raid"))
    monkeypatch.setattr(
        raid_rebuild, "apply_shutdown", lambda *a: pytest.fail("Unexpected shutdown")
    )
    monkeypatch.setattr(
        service.handover,
        "build",
        lambda *a: {"kit": "Fixture kit", "generated_at": "2026-10-16T00:00:00Z", "servers": []},
    )
    return SimpleNamespace(
        states=states, calls=calls, scopes=scopes, desired=desired, view=view, review=review
    )


def approve(db_session):
    return service.approve(db_session, P, "tester", service.contract(db_session, P)["digest"])


def skip_to(lab, db_session, step):
    for earlier in service.ORDER[: service.ORDER.index(step)]:
        lab.states[earlier].update(state="verified", active=False)
        if earlier == "firmware":
            record_audit_event(
                db_session,
                actor="tester",
                event_type="kit.contract.firmware_checked",
                message="Fixture firmware proof",
                data={"profile_id": P, "device_id": D, "desired": {}},
            )
            db_session.commit()


def test_unapproved_never_acts(db_session, lab):
    assert service.reconcile(db_session, P, "tester")["state"] == "unapproved"
    assert lab.calls == []


@pytest.mark.parametrize("state", ["needs_attention", "uncertain", "failed", "closed", "reachable"])
def test_later_blocker_prevents_earlier_hardware_dispatch(db_session, lab, state):
    lab.states["windows"].update(state=state, message="Later unresolved run")
    approve(db_session)
    result = service.reconcile(db_session, P, "tester")
    assert result["state"] == "blocked"
    assert result["item"] == f"windows:{D}"
    assert lab.calls == []


def test_digest_rechecked_after_review_before_dispatch(db_session, lab, monkeypatch):
    skip_to(lab, db_session, "switch")

    def review(*args):
        lab.desired["network"]["gateway"] = "192.0.2.99"
        return {"blockers": [], "replace_needed": False}

    monkeypatch.setattr(service.switch_setup, "review", review)
    approve(db_session)
    result = service.reconcile(db_session, P, "tester")
    assert result["state"] == "blocked" and "before dispatch" in result["message"]
    assert not any(action == "start" for action, _ in lab.calls)


def test_spp_updates_block_without_worker_submission(db_session, lab, monkeypatch):
    from app.services import spp_update_runtime

    skip_to(lab, db_session, "firmware")
    monkeypatch.setattr(
        spp_update_runtime, "plan", lambda *a: {"updates": [{"name": "fixture"}], "blockers": []}
    )
    approve(db_session)
    for _ in range(2):
        result = service.reconcile(db_session, P, "tester")
        assert result["state"] == "blocked" and "SPP updates needed" in result["message"]
        assert result["href"] == "/setup/check-firmware"
    assert lab.scopes == []


def test_new_firmware_package_requires_fresh_parts_comparison(db_session, lab, monkeypatch):
    skip_to(lab, db_session, "firmware")
    lab.states["firmware"].update(state="verified", run_id="old-parts")
    record_audit_event(
        db_session,
        actor="tester",
        event_type="kit.contract.firmware_checked",
        message="Old package proof",
        data={
            "profile_id": P,
            "device_id": D,
            "package_path": "old.iso",
            "parts_run_id": "old-parts",
            "desired": {"package": {"path": "old.iso"}},
        },
    )
    db_session.commit()
    lab.desired["items"][2]["desired"] = {"package": {"path": "new.iso"}}
    reviews = []

    def review(*args):
        reviews.append(True)
        return {"parts": [{"name": "direct-update"}], "review_id": "fixture", "blockers": []}

    monkeypatch.setattr(service.parts_update, "review", review)
    approve(db_session)
    service.reconcile(db_session, P, "tester")
    assert reviews == [True]
    assert ("start", "firmware") in lab.calls
    assert service.certificate(db_session, P)["state"] == "incomplete"


def test_raid_payload_normalizes_spare_defaults():
    volume = {"Raid": "Raid1", "DataDrives": ["1", "2"]}
    assert service._raid_payload({"LogicalDrives": [volume]}) == service._raid_payload(
        {"LogicalDrives": [{**volume, "SpareDrives": []}]}
    )
    assert service._raid_payload({"LogicalDrives": [volume]}) != service._raid_payload(
        {"LogicalDrives": [{**volume, "SpareDrives": ["3"]}]}
    )


def test_created_raid_without_spares_is_verified(db_session, lab, monkeypatch):
    from app.api import raid_rebuild
    from app.services import hpe_raid

    intent = SimpleNamespace(
        controller_ref="controller",
        wipe_existing_logical_drives=False,
        volumes=[
            SimpleNamespace(
                name="Boot",
                bootable=True,
                raid_level="RAID1",
                drive_bays=["1", "2"],
                spare_bays=[],
                size_policy="max",
            )
        ],
    )
    view = {
        "controllers": [{"id": "controller"}],
        "drives": [
            {
                "location": bay,
                "eligible": True,
                "id": f"controller/{bay}",
                "capacity_bytes": 100,
                "media": "SSD",
            }
            for bay in ("1", "2")
        ],
    }
    payload = raid_rebuild.planned_payload(intent, view)
    attempt = record_audit_event(
        db_session,
        actor="tester",
        event_type="kit.raid_rebuild.attempt",
        message="Fixture create",
        data={"profile_id": P, "payload": payload},
    )
    db_session.commit()
    monkeypatch.setattr(hpe_raid, "get_hpe_raid_intent", lambda *a: intent)
    monkeypatch.setattr(
        raid_rebuild,
        "rebuild_status",
        lambda *a: {
            "operation": "create",
            "status": "verified",
            "attempt_id": attempt.id,
            "active": False,
        },
    )
    observed = service._observed(db_session, P, lab.desired["items"][3])
    assert observed["state"] == "verified" and observed["matches_desired"] is True
    intent.volumes[0].drive_bays = ["3", "4"]
    assert service._observed(db_session, P, lab.desired["items"][3])["matches_desired"] is False


def test_esxi_build_records_complete_inputs_before_start(db_session, lab, monkeypatch):
    skip_to(lab, db_session, "esxi")
    desired = {
        "network": {"gateway": "192.0.2.1"},
        "disk_identities": {"boot": {"disk_id": "naa.fixture"}},
        "volumes": [{"drive_bays": ["1", "2"]}],
    }
    lab.desired["items"][4]["desired"] = desired

    def build(session, p, d, actor):
        record_audit_event(
            session,
            actor=actor,
            event_type="kit.esxi_installer_built",
            message="Fixture installer",
            data={"profile_id": p, "device_id": d, "iso_sha256": "fixture-sha"},
        )
        session.commit()
        return {"status": "ready", "blockers": []}

    monkeypatch.setattr(service.esxi_install, "build_installer", build)
    approve(db_session)
    service.reconcile(db_session, P, "tester")
    proof = service._latest(db_session, "kit.contract.esxi_inputs", profile_id=P, device_id=D)
    assert proof.data_json["desired"] == desired
    assert proof.data_json["iso_sha256"] == "fixture-sha"
    assert ("start", "esxi") in lab.calls


@pytest.mark.parametrize("change", ["network", "disk_identities", "volumes"])
def test_esxi_proof_binds_complete_inputs(db_session, lab, change):
    desired = {
        "network": {"gateway": "192.0.2.1"},
        "disk_identities": {"boot": {"disk_id": "naa.fixture"}},
        "volumes": [{"drive_bays": ["1", "2"]}],
    }
    item = {**lab.desired["items"][4], "desired": deepcopy(desired)}
    lab.states["esxi"].update(state="verified", run_id="fixture-install")
    for event, data in (
        ("kit.esxi_installer_built", {"iso_sha256": "fixture-sha"}),
        ("kit.contract.esxi_inputs", {"desired": desired, "iso_sha256": "fixture-sha"}),
        ("kit.esxi_install.run", {"run_id": "fixture-install", "iso_sha256": "fixture-sha"}),
    ):
        record_audit_event(
            db_session,
            actor="tester",
            event_type=event,
            message="Fixture build proof",
            data={"profile_id": P, "device_id": D, **data},
        )
        db_session.commit()
    assert service._observed(db_session, P, item)["matches_desired"] is True
    item["desired"][change] = {"changed": True}
    assert service._observed(db_session, P, item)["matches_desired"] is False


def test_compact_display_preserves_full_digest(db_session, lab):
    firmware = lab.desired["items"][2]["desired"]
    firmware["package"] = {
        "path": "private/path.iso",
        "file_name": "path.iso",
        "release_hint": "fixture",
        "size_bytes": 42,
        "manifest_files": ["many"],
    }
    lab.desired["items"][4]["desired"] = {
        "hostname": "fixture.example",
        "media": {"name": "esxi.iso", "path": "hidden/esxi.iso"},
        "volumes": ["duplicate"],
        "network": {"subnet": "192.0.2.0/24", "gateway": "192.0.2.1"},
    }
    document = service.contract(db_session, P)
    assert document["items"][2]["desired"] == {
        "file_name": "path.iso",
        "release_hint": "fixture",
        "size_bytes": 42,
    }
    esxi = document["items"][4]["desired"]
    assert "volumes" not in esxi and "network" not in esxi
    assert esxi["media"] == "esxi.iso" and esxi["network_summary"] == "192.0.2.0/24 via 192.0.2.1"
    assert document["digest"] == service._contract(db_session, P)["digest"]
    firmware["package"]["path"] = "another/path.iso"
    assert service.contract(db_session, P)["digest"] != document["digest"]


def test_approval_binds_the_exact_digest(db_session, lab):
    digest = service.contract(db_session, P)["digest"]
    with pytest.raises(service.ContractError):
        service.approve(db_session, P, "tester", "0" * 64)
    assert approve(db_session)["digest"] == digest
    event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "kit.contract.approved")
    )
    assert event.data_json == {"profile_id": P, "digest": digest}
    assert lab.calls == []


def test_drift_blocks_and_approval_stays_invalid_even_if_values_reverted(db_session, lab):
    approve(db_session)
    original = lab.desired["network"]["gateway"]
    lab.desired["network"]["gateway"] = "192.0.2.2"
    assert "drift" in service.reconcile(db_session, P, "tester")["message"]
    lab.desired["network"]["gateway"] = original
    assert service.reconcile(db_session, P, "tester")["state"] == "unapproved"
    assert lab.calls == []


def test_verified_steps_are_skipped_and_one_tick_starts_only_first_missing(db_session, lab):
    skip_to(lab, db_session, "windows")
    approve(db_session)
    result = service.reconcile(db_session, P, "tester")
    assert result["state"] == "converging"
    assert [(a, s) for a, s in lab.calls if a in {"start", "advance"}] == [("start", "windows")]
    assert lab.scopes == ["vm_deploy_only"]


@pytest.mark.parametrize("step", ["switch", "firmware", "esxi", "windows", "acceptance"])
def test_active_run_is_advanced_not_restarted(db_session, lab, step):
    skip_to(lab, db_session, step)
    lab.states[step].update(state="running", active=True)
    approve(db_session)
    service.reconcile(db_session, P, "tester")
    assert ("advance", step) in lab.calls
    assert not any(a == "start" for a, _ in lab.calls)
    assert lab.scopes == [service.SCOPES[step], "read_only"]


def test_existing_raid_volumes_block_without_delete_or_stage(db_session, lab):
    skip_to(lab, db_session, "raid")
    lab.view["volumes"] = [{"id": "existing-volume"}]
    approve(db_session)
    result = service.reconcile(db_session, P, "tester")
    assert result["state"] == "blocked" and "Existing RAID volumes" in result["message"]
    assert result["href"] == "/setup/disks"
    assert ("start", "raid") not in lab.calls
    assert lab.scopes == []


def test_raid_stages_boots_then_verifies_in_separate_ticks(db_session, lab):
    skip_to(lab, db_session, "raid")
    approve(db_session)
    for expected in ("start", "boot", "advance"):
        service.reconcile(db_session, P, "tester")
        assert lab.calls[-1] == (expected, "raid") or lab.calls[-1] == (
            "scope-preview",
            "read_only",
        )
    assert [(a, s) for a, s in lab.calls if s == "raid"] == [
        ("start", "raid"),
        ("boot", "raid"),
        ("advance", "raid"),
    ]


@pytest.mark.parametrize("step", service.ORDER[1:])
def test_needs_attention_never_resends(db_session, lab, step):
    skip_to(lab, db_session, step)
    lab.states[step].update(
        state="needs_attention", active=True, message="Inspect the fixture target"
    )
    approve(db_session)
    result = service.reconcile(db_session, P, "tester")
    assert result["state"] == "blocked" and result["message"] == "Inspect the fixture target"
    assert lab.calls == []


def test_converged_certificate_uses_recorded_evidence_only(db_session, lab):
    skip_to(lab, db_session, "acceptance")
    lab.states["acceptance"].update(state="verified", finished_at="2026-10-16T00:00:00Z")
    approve(db_session)
    assert service.reconcile(db_session, P, "tester")["state"] == "converged"
    proof = service.certificate(db_session, P)
    assert proof["state"] == "converged"
    assert proof["handover"]["kit"] == "Fixture kit"
    assert proof["items"][-1]["verified_at"] == "2026-10-16T00:00:00Z"
    assert lab.calls == []


def test_verified_windows_with_different_values_is_not_convergence(db_session, lab):
    skip_to(lab, db_session, "windows")
    lab.desired["items"][5]["desired"] = {"vm_name": "desired-fixture"}
    lab.states["windows"].update(state="verified", vm_name="old-fixture")
    approve(db_session)
    result = service.reconcile(db_session, P, "tester")
    assert result["state"] == "blocked" and "differs" in result["message"]
    assert lab.calls == []


def test_routes_are_registered_and_reads_do_not_act(client, lab):
    base = f"/api/v1/rack-plans/{P}/contract"
    response = client.get(base)
    assert response.status_code == 200
    digest = response.json()["digest"]
    assert client.post(base + "/approve", json={"digest": "0" * 64}).status_code == 409
    assert client.post(base + "/approve", json={"digest": digest}).status_code == 200
    assert client.get(base + "/certificate").json()["state"] == "incomplete"
    assert lab.calls == []


def test_actual_contract_assembly_is_stable_and_uses_stored_settings_only(db_session, monkeypatch):
    from app.api import rack_plans
    from app.services import hpe_raid, ilo_access_settings, lab_profiles

    monkeypatch.setattr(
        rack_plans, "kit_profile", lambda p: {"id": P, "name": "Fixture kit", "version": 2}
    )
    monkeypatch.setattr(
        rack_plans,
        "get_plan",
        lambda *a: SimpleNamespace(
            equipment=[
                SimpleNamespace(device_id=D, kind="server", name="Fixture server"),
                SimpleNamespace(device_id="sw", kind="switch", name="Fixture switch"),
            ]
        ),
    )
    monkeypatch.setattr(
        lab_profiles,
        "active_lab_profile_context",
        lambda *a: {"active_profile": {"id": P, "gateway": "192.0.2.1"}},
    )
    access = {"host": "192.0.2.10", "username": "fixture-user", "last_probe_time": "old"}
    monkeypatch.setattr(ilo_access_settings, "read_ilo_access_settings", lambda *a: access)
    monkeypatch.setattr(
        hpe_raid,
        "get_hpe_raid_intent",
        lambda *a: SimpleNamespace(
            model_dump=lambda **k: {
                "controller_ref": "fixture-controller",
                "volumes": [{"bootable": True, "drive_bays": ["1", "2"], "raid_level": "RAID1"}],
            }
        ),
    )
    monkeypatch.setattr(
        service.esxi_install,
        "_boot_volume",
        lambda *a: {"disk_id": "naa.fixture", "bays": ["1", "2"], "read_at": "old"},
    )
    monkeypatch.setattr(service.esxi_install, "_data_volume", lambda *a: None)
    monkeypatch.setattr(
        service.switch_setup,
        "get_setup",
        lambda *a: {
            "settings": {"hostname": "fixture-switch"},
            "username": "fixture",
            "console": {"port": "fixture-port", "baud": 9600},
        },
    )
    monkeypatch.setattr(service.acceptance, "_default_lookup", lambda *a: "fixture.lab.example")
    for event, data in (
        (
            "kit.windows.settings",
            {
                "vm_name": "fixture-vm",
                "image": "fixture.ova",
                "network": "fixture-network",
                "datastore": "fixture-data",
            },
        ),
        ("kit.esxi_settings_saved", {"hostname": "fixture.lab.example", "vlan_id": 100}),
        ("kit.firmware_package_selected", {"package": {"path": "fixture.iso", "size_bytes": 42}}),
    ):
        record_audit_event(
            db_session,
            actor="tester",
            event_type=event,
            message="Fixture settings",
            data={"profile_id": P, "device_id": D, **data},
        )
    db_session.commit()
    monkeypatch.setattr(service, "_probe", lambda *a: pytest.fail("Contract contacted equipment"))
    monkeypatch.setattr(
        service.windows_deploy,
        "get_setup",
        lambda *a: pytest.fail("Windows setup probes ESXi; must not be used"),
    )
    first = service.contract(db_session, P)
    access["last_probe_time"] = "new"
    assert service.contract(db_session, P) == first
    assert first["items"][3]["desired"]["volumes"][0]["drive_bays"] == ["1", "2"]
    assert first["items"][5]["desired"]["image"] == "fixture.ova"
    access["host"] = "192.0.2.11"
    assert service.contract(db_session, P)["digest"] != first["digest"]


def test_external_spp_run_blocks_contract_without_admission(db_session, lab, monkeypatch):
    from app.services import spp_update_runtime

    skip_to(lab, db_session, "firmware")
    lab.states["firmware"].update(state="verified")
    disc = {"status": "running", "active": True, "operation_id": "fixture-disc"}
    monkeypatch.setattr(spp_update_runtime, "recorded_status", lambda *a, **k: deepcopy(disc))
    monkeypatch.setattr(
        spp_update_runtime,
        "plan",
        lambda *a: pytest.fail("An existing disc run must never be planned again"),
    )
    approve(db_session)
    result = service.reconcile(db_session, P, "tester")
    assert result["state"] == "blocked"
    assert "Check firmware" in result["message"]
    assert not any(a == "start" for a, _ in lab.calls)


def test_switch_replace_needed_is_a_blocker(db_session, lab, monkeypatch):
    skip_to(lab, db_session, "switch")
    monkeypatch.setattr(
        service.switch_setup, "review", lambda *a: {"blockers": [], "replace_needed": True}
    )
    approve(db_session)
    result = service.reconcile(db_session, P, "tester")
    assert result["state"] == "blocked" and "replacement" in result["message"]
    assert lab.calls == []


def test_raid_shutdown_is_previewed_once_then_waits_and_forces_only_after_grace(
    db_session, lab, monkeypatch
):
    from app.api import raid_rebuild as raid

    skip_to(lab, db_session, "raid")
    power = {"value": "On", "force": False, "pending": False}

    def preview(p, d, payload, session, actor):
        power["force"] = payload.force
        lab.calls.append(("shutdown-preview", payload.force))
        return deepcopy(lab.review)

    def shutdown(p, d, payload, session, actor):
        lab.calls.append(("shutdown-apply", power["force"]))
        power["pending"] = True
        record_audit_event(
            session,
            actor=actor,
            event_type="kit.raid_rebuild.shutdown_attempt",
            message="Fixture shutdown",
            data={"device_id": d, "force": power["force"]},
        )
        session.commit()

    monkeypatch.setattr(raid, "read_reset_power", lambda *a: {"power": power["value"]})
    monkeypatch.setattr(raid, "preview_shutdown", preview)
    monkeypatch.setattr(raid, "apply_shutdown", shutdown)
    monkeypatch.setattr(
        service.runtime_write_scope,
        "active_operations",
        lambda *a: ["fixture-power"] if power["pending"] else [],
    )
    approve(db_session)
    service.reconcile(db_session, P, "tester")
    service.reconcile(db_session, P, "tester")
    assert [(a, b) for a, b in lab.calls if a.startswith("shutdown")] == [
        ("shutdown-preview", False),
        ("shutdown-apply", False),
    ]
    assert ("start", "raid") not in lab.calls
    prior = raid.latest_event(db_session, D, "shutdown_attempt")
    prior.created_at = datetime.now(UTC) - timedelta(seconds=131)
    db_session.commit()
    service.reconcile(db_session, P, "tester")
    service.reconcile(db_session, P, "tester")
    assert [(a, b) for a, b in lab.calls if a.startswith("shutdown")] == [
        ("shutdown-preview", False),
        ("shutdown-apply", False),
        ("shutdown-preview", True),
        ("shutdown-apply", True),
    ]
    power["value"] = "Off"
    service.reconcile(db_session, P, "tester")
    assert ("start", "raid") in lab.calls
    assert "read_only" not in lab.scopes  # the admitted power/storage sequence is still active
