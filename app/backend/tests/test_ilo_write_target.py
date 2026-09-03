from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.providers.ilo_redfish import (
    IloRedfishConfig,
    _attach_write_target_evidence,
    _resource_summary,
    ilo_target_fingerprint,
)
from app.schemas import HpeRaidApplyCreate, IloSetupApplyCreate
from app.services import (
    esxi_boot_workflow,
    esxi_management_recovery,
    hpe_raid,
    ilo_setup_apply,
    ilo_write_target,
)

CURRENT_ACCESS_HOST = "192.168.1.11"
DESIRED_SAVED_HOST = "192.168.1.201"
NOW = datetime(2026, 7, 23, 15, 0, tzinfo=UTC)


def test_exact_current_access_evidence_never_falls_through_to_desired_host(
    monkeypatch,
) -> None:
    result = _cached_evidence(CURRENT_ACCESS_HOST)
    monkeypatch.setattr(
        ilo_write_target,
        "get_probe_result",
        lambda _provider_id: (result, result["checked_at"]),
    )
    monkeypatch.setattr(
        IloRedfishConfig,
        "from_settings",
        classmethod(
            lambda cls: cls(
                host=DESIRED_SAVED_HOST,
                username="operator",
                password="secret",
                verify_tls=False,
                timeout_seconds=3.0,
                host_source="active_saved_profile",
                fallback_hosts=(CURRENT_ACCESS_HOST,),
                fallback_host_sources=("original_dhcp_ip",),
            )
        ),
    )

    context, blockers = ilo_write_target.resolve_ilo_write_target_context(
        CURRENT_ACCESS_HOST,
        now=NOW,
    )

    assert blockers == []
    assert context is not None
    assert context.current_access_host == CURRENT_ACCESS_HOST
    exact = ilo_write_target.exact_ilo_write_config(context)
    assert exact.host == CURRENT_ACCESS_HOST
    assert exact.host != DESIRED_SAVED_HOST
    assert exact.target_candidates == [
        {"host": CURRENT_ACCESS_HOST, "source": "exact_write_target_context"}
    ]


def test_desired_host_cannot_reuse_current_access_evidence(monkeypatch) -> None:
    result = _cached_evidence(CURRENT_ACCESS_HOST)
    monkeypatch.setattr(
        ilo_write_target,
        "get_probe_result",
        lambda _provider_id: (result, result["checked_at"]),
    )

    context, blockers = ilo_write_target.resolve_ilo_write_target_context(
        DESIRED_SAVED_HOST,
        now=NOW,
    )

    assert context is None
    assert any("not bound to the requested current-access host" in item for item in blockers)


def test_fallback_candidate_evidence_is_never_write_authority(monkeypatch) -> None:
    result = _cached_evidence(CURRENT_ACCESS_HOST, candidate_index=2, candidate_count=2)
    monkeypatch.setattr(
        ilo_write_target,
        "get_probe_result",
        lambda _provider_id: (result, result["checked_at"]),
    )

    context, blockers = ilo_write_target.resolve_ilo_write_target_context(
        CURRENT_ACCESS_HOST,
        now=NOW,
    )

    assert context is None
    assert any("Fallback or multi-candidate" in item for item in blockers)
    assert any("exact-target-only" in item for item in blockers)


def test_stale_evidence_is_never_write_authority(monkeypatch) -> None:
    checked_at = NOW - timedelta(minutes=6)
    result = _cached_evidence(CURRENT_ACCESS_HOST, checked_at=checked_at)
    monkeypatch.setattr(
        ilo_write_target,
        "get_probe_result",
        lambda _provider_id: (result, result["checked_at"]),
    )

    context, blockers = ilo_write_target.resolve_ilo_write_target_context(
        CURRENT_ACCESS_HOST,
        now=NOW,
    )

    assert context is None
    assert any("stale" in item for item in blockers)


def test_missing_explicit_host_is_blocked_without_reading_cache(monkeypatch) -> None:
    monkeypatch.setattr(
        ilo_write_target,
        "get_probe_result",
        lambda _provider_id: (_ for _ in ()).throw(
            AssertionError("cache must not be read without an explicit host")
        ),
    )

    context, blockers = ilo_write_target.resolve_ilo_write_target_context(None, now=NOW)

    assert context is None
    assert blockers == [
        "An explicit current-access ilo_host IP is required for every iLO-backed write."
    ]


def test_probe_evidence_hashes_hardware_identity_without_exposing_serial() -> None:
    result = _attach_write_target_evidence(
        {
            "status": "ok",
            "target_source": "operator_first_contact",
            "target_fingerprint": ilo_target_fingerprint(CURRENT_ACCESS_HOST),
            "candidate_index": 1,
            "target_candidate_count": 1,
            "managers": [
                _resource_summary(
                    {
                        "@odata.id": "/redfish/v1/Managers/1/",
                        "Id": "1",
                        "Model": "iLO 5",
                        "SerialNumber": "PRIVATE-MANAGER-SERIAL",
                    }
                )
            ],
            "systems": [
                _resource_summary(
                    {
                        "@odata.id": "/redfish/v1/Systems/1/",
                        "Id": "1",
                        "UUID": "00000000-0000-0000-0000-000000000011",
                        "SerialNumber": "PRIVATE-SERVER-SERIAL",
                    }
                )
            ],
            "chassis": [],
        }
    )

    evidence = result["write_target_evidence"]
    assert evidence["identity_verified"] is True
    assert len(evidence["identity_fingerprint_sha256"]) == 64
    assert evidence["evidence_digest_sha256"] == (
        ilo_write_target.ilo_write_evidence_digest(evidence)
    )
    assert "PRIVATE-MANAGER-SERIAL" not in str(result)
    assert "PRIVATE-SERVER-SERIAL" not in str(result)


def test_generic_redfish_ids_are_not_hardware_identity_proof() -> None:
    result = _attach_write_target_evidence(
        {
            "status": "ok",
            "target_source": "operator_first_contact",
            "target_fingerprint": ilo_target_fingerprint(CURRENT_ACCESS_HOST),
            "candidate_index": 1,
            "target_candidate_count": 1,
            "managers": [
                _resource_summary(
                    {"@odata.id": "/redfish/v1/Managers/1/", "Id": "1"}
                )
            ],
            "systems": [
                _resource_summary(
                    {"@odata.id": "/redfish/v1/Systems/1/", "Id": "1"}
                )
            ],
            "chassis": [],
        }
    )

    evidence = result["write_target_evidence"]
    assert evidence["identity_verified"] is False
    assert evidence["inventory_complete"] is False
    assert evidence["identity_fingerprint_sha256"] is None


def test_immediate_preflight_rejects_hardware_identity_change(monkeypatch) -> None:
    original = _context(identity="a" * 64)
    changed = _context(identity="c" * 64)
    config = IloRedfishConfig(
        host=CURRENT_ACCESS_HOST,
        username="operator",
        password="secret",
        verify_tls=False,
        timeout_seconds=3.0,
        host_source="exact_write_target_context",
    )

    class FakeAdapter:
        def __init__(self, *, provider_mode, config) -> None:
            assert provider_mode == "local-lab-readwrite"
            assert config.host == CURRENT_ACCESS_HOST

        def probe(self) -> dict:
            return {"status": "ok"}

    monkeypatch.setattr(ilo_write_target, "IloRedfishAdapter", FakeAdapter)
    monkeypatch.setattr(ilo_write_target, "exact_ilo_write_config", lambda _context: config)
    monkeypatch.setattr(
        ilo_write_target,
        "resolve_ilo_write_target_context",
        lambda host: (changed, []) if host == CURRENT_ACCESS_HOST else (None, ["mismatch"]),
    )

    refreshed, refreshed_config, blockers = (
        ilo_write_target.refresh_ilo_write_target_context(original)
    )

    assert refreshed is None
    assert refreshed_config is None
    assert blockers == [
        "Immediate iLO preflight hardware identity does not match the reviewed target."
    ]


def test_esxi_ilo_mutations_make_zero_write_calls_without_exact_target(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ILO_WRITE_TARGET_HOST", raising=False)
    monkeypatch.setattr(esxi_boot_workflow, "_action_blockers", lambda *_args: [])
    monkeypatch.setattr(esxi_boot_workflow, "firmware_gate_blockers", lambda *_args: [])
    monkeypatch.setattr(
        esxi_boot_workflow,
        "_write_report",
        lambda _path, _title, payload: payload,
    )

    def unexpected(*_args, **_kwargs):
        raise AssertionError("an iLO read or mutation was attempted before target proof")

    monkeypatch.setattr(esxi_boot_workflow, "prepare_esxi_media_url", unexpected)
    monkeypatch.setattr(esxi_boot_workflow, "_select_virtual_media_device", unexpected)
    monkeypatch.setattr(esxi_boot_workflow, "_get_redfish_resource", unexpected)
    monkeypatch.setattr(esxi_boot_workflow, "_post_redfish", unexpected)
    monkeypatch.setattr(esxi_boot_workflow, "_patch_system_boot", unexpected)
    monkeypatch.setattr(esxi_boot_workflow, "_post_system_reset", unexpected)

    results = [
        esxi_boot_workflow.insert_esxi_virtual_media(),
        esxi_boot_workflow.eject_esxi_virtual_media(),
        esxi_boot_workflow.set_esxi_one_time_boot(),
        esxi_boot_workflow.reset_for_esxi_installer_boot(),
    ]

    assert all(result["status"] == "blocked" for result in results)
    assert all(
        any("explicit current-access ilo_host" in item for item in result["blockers"])
        for result in results
    )


def test_fallback_evidence_blocks_esxi_mutation_before_media_preparation(
    monkeypatch,
) -> None:
    result = _cached_evidence(
        CURRENT_ACCESS_HOST,
        candidate_index=2,
        candidate_count=2,
    )
    monkeypatch.setattr(
        ilo_write_target,
        "get_probe_result",
        lambda _provider_id: (result, result["checked_at"]),
    )
    monkeypatch.setattr(esxi_boot_workflow, "_action_blockers", lambda *_args: [])
    monkeypatch.setattr(esxi_boot_workflow, "firmware_gate_blockers", lambda *_args: [])
    monkeypatch.setattr(
        esxi_boot_workflow,
        "_write_report",
        lambda _path, _title, payload: payload,
    )
    monkeypatch.setattr(
        esxi_boot_workflow,
        "prepare_esxi_media_url",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("media preparation must not start")
        ),
    )

    response = esxi_boot_workflow.insert_esxi_virtual_media(
        ilo_host=CURRENT_ACCESS_HOST
    )

    assert response["status"] == "blocked"
    assert any("Fallback or multi-candidate" in item for item in response["blockers"])


def test_ilo_setup_patch_is_not_attempted_without_exact_target(monkeypatch) -> None:
    monkeypatch.delenv("ILO_WRITE_TARGET_HOST", raising=False)
    monkeypatch.setattr(
        ilo_setup_apply,
        "resolve_ilo_write_target_context",
        lambda _host: (None, ["exact target evidence missing"]),
    )
    monkeypatch.setattr(
        ilo_setup_apply,
        "build_ilo_setup_apply_plan",
        lambda _session, *, config=None: {"blockers": [], "warnings": []},
    )
    monkeypatch.setattr(
        ilo_setup_apply,
        "_environment_gate_blockers",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        ilo_setup_apply,
        "_record_result",
        lambda _config, result, **_kwargs: result,
    )
    monkeypatch.setattr(
        ilo_setup_apply.httpx,
        "Client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("PATCH client must not be created")
        ),
    )

    result = ilo_setup_apply.apply_ilo_setup(
        object(),
        IloSetupApplyCreate(
            confirmation_phrase=ilo_setup_apply.CONFIRMATION_PHRASE,
            ilo_host=CURRENT_ACCESS_HOST,
        ),
    )

    assert result["status"] == "blocked"
    assert result["patch_attempted"] is False
    assert result["patch_count"] == 0


def test_raid_patch_and_reset_are_not_attempted_without_exact_target(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ILO_WRITE_TARGET_HOST", raising=False)
    monkeypatch.setattr(
        hpe_raid,
        "resolve_ilo_write_target_context",
        lambda _host: (None, ["exact target evidence missing"]),
    )
    preview = SimpleNamespace(
        blockers=[],
        warnings=[],
        desired_intent=SimpleNamespace(volumes=[]),
        current_layout={},
    )
    monkeypatch.setattr(hpe_raid, "get_hpe_raid_plan_preview", lambda _session: preview)
    monkeypatch.setattr(hpe_raid, "_apply_blockers", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(hpe_raid, "_layout_summary", lambda _layout: {})
    monkeypatch.setattr(hpe_raid, "_write_apply_artifacts", lambda _result: None)
    monkeypatch.setattr(hpe_raid, "_write_reset_report", lambda _result: None)
    monkeypatch.setattr(hpe_raid, "_reset_blockers", lambda **_kwargs: [])

    def unexpected(*_args, **_kwargs):
        raise AssertionError("RAID PATCH/POST must not be attempted")

    monkeypatch.setattr(hpe_raid, "_patch_smartstorage_settings", unexpected)
    monkeypatch.setattr(hpe_raid, "_server_reset_observation", unexpected)
    monkeypatch.setattr(hpe_raid, "_post_system_reset", unexpected)

    apply_result = hpe_raid.apply_hpe_raid_plan(
        object(),
        HpeRaidApplyCreate(
            confirmation_phrase=hpe_raid.CONFIRMATION_PHRASE,
            ilo_host=CURRENT_ACCESS_HOST,
        ),
    )
    reset_result = hpe_raid.reset_server_for_raid(ilo_host=CURRENT_ACCESS_HOST)

    assert apply_result["status"] == "blocked"
    assert reset_result["status"] == "blocked"
    assert apply_result["redfish_result"] is None
    assert reset_result["reset"] is None


def test_esxi_recovery_does_not_probe_or_post_without_exact_target(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ILO_WRITE_TARGET_HOST", raising=False)
    monkeypatch.setattr(
        esxi_management_recovery,
        "_recovery_gates",
        lambda: {"flag_state": {}, "blockers": []},
    )

    def unexpected(*_args, **_kwargs):
        raise AssertionError("live target probe or power POST must not run")

    monkeypatch.setattr(esxi_management_recovery, "_target_state", unexpected)
    monkeypatch.setattr(esxi_management_recovery, "_safe_system_state", unexpected)
    monkeypatch.setattr(esxi_management_recovery, "_safe_ilo_probe", unexpected)
    monkeypatch.setattr(esxi_management_recovery, "_post_system_reset", unexpected)

    result = esxi_management_recovery.recover_esxi_management(write_report=False)

    assert result["status"] == "blocked"
    assert result["apply"]["attempted"] is False
    assert any("explicit current-access ilo_host" in item for item in result["blockers"])


def test_direct_write_routes_require_request_bound_ilo_host(client) -> None:
    requests = (
        (
            "/api/v1/providers/ilo-redfish/setup-apply",
            {"confirmation_phrase": ilo_setup_apply.CONFIRMATION_PHRASE},
        ),
        (
            "/api/v1/providers/ilo-redfish/hpe-raid-apply",
            {"confirmation_phrase": hpe_raid.CONFIRMATION_PHRASE},
        ),
        ("/api/v1/providers/ilo-redfish/hpe-raid-reset", {}),
        ("/api/v1/providers/esxi-readonly/recover-management", {}),
    )

    for path, payload in requests:
        response = client.post(path, json=payload)
        assert response.status_code == 422, path


def test_raid_patch_does_not_run_after_non_2xx_settings_preflight(
    monkeypatch,
) -> None:
    patch_calls = 0

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            pass

        def get(self, url: str) -> httpx.Response:
            return httpx.Response(404, request=httpx.Request("GET", url))

        def patch(self, *_args, **_kwargs):
            nonlocal patch_calls
            patch_calls += 1
            raise AssertionError("PATCH must not run after a failed GET")

    monkeypatch.setattr(hpe_raid.httpx, "Client", FakeClient)

    with pytest.raises(httpx.HTTPStatusError):
        hpe_raid._patch_smartstorage_settings(
            {"DataGuard": "Disabled", "LogicalDrives": []},
            config=_exact_config(),
        )

    assert patch_calls == 0


def test_reset_post_does_not_run_without_successful_advertised_action(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        hpe_raid,
        "_get_redfish_resource",
        lambda _path, *, config: {"status_code": 401, "body": {}},
    )
    monkeypatch.setattr(
        hpe_raid.httpx,
        "Client",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("POST client must not be created")
        ),
    )

    with pytest.raises(RuntimeError, match="HTTP 2xx"):
        hpe_raid._post_system_reset("On", config=_exact_config())


def test_virtual_media_wrong_iso_never_satisfies_insert_precondition(
    monkeypatch,
) -> None:
    context = _context(identity="a" * 64)
    config = _exact_config()
    monkeypatch.setattr(
        esxi_boot_workflow,
        "_resolve_write_target",
        lambda *_args: (context, config, []),
    )
    monkeypatch.setattr(
        esxi_boot_workflow,
        "refresh_ilo_write_target_context",
        lambda _context: (context, config, []),
    )
    monkeypatch.setattr(esxi_boot_workflow, "_action_blockers", lambda *_args: [])
    monkeypatch.setattr(esxi_boot_workflow, "firmware_gate_blockers", lambda *_args: [])
    monkeypatch.setattr(
        esxi_boot_workflow,
        "prepare_esxi_media_url",
        lambda *, config: {
            "status": "ready",
            "selected_iso": {"name": "reviewed.iso"},
            "media_url": "http://192.0.2.10/reviewed.iso",
            "blockers": [],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        esxi_boot_workflow,
        "_select_virtual_media_device",
        lambda *, config: {
            "path": "/redfish/v1/Managers/1/VirtualMedia/2/",
            "insert_target": "/redfish/v1/Managers/1/VirtualMedia/2/Actions/VirtualMedia.InsertMedia/",
        },
    )
    reads = iter(
        [
            {"status_code": 200, "body": {"Inserted": False, "Image": None}},
            {
                "status_code": 200,
                "body": {
                    "Inserted": True,
                    "Image": "http://192.0.2.10/different.iso",
                },
            },
        ]
    )
    monkeypatch.setattr(
        esxi_boot_workflow,
        "_get_redfish_resource",
        lambda *_args, **_kwargs: next(reads),
    )
    monkeypatch.setattr(
        esxi_boot_workflow,
        "_post_virtual_media_action",
        lambda *_args, **_kwargs: {"status_code": 200},
    )
    monkeypatch.setattr(esxi_boot_workflow, "write_json_object", lambda *_args: None)
    monkeypatch.setattr(
        esxi_boot_workflow,
        "_write_report",
        lambda _path, _title, payload: payload,
    )

    result = esxi_boot_workflow.insert_esxi_virtual_media(
        ilo_host=CURRENT_ACCESS_HOST
    )

    assert result["status"] == "blocked"
    assert result["inserted"] is True
    assert any("does not show inserted ISO" in item for item in result["blockers"])


def _cached_evidence(
    host: str,
    *,
    checked_at: datetime = NOW,
    candidate_index: int = 1,
    candidate_count: int = 1,
) -> dict:
    evidence = {
        "source": ilo_write_target.WRITE_EVIDENCE_SOURCE,
        "collected_at": checked_at.isoformat(),
        "target_source": "operator_first_contact",
        "target_fingerprint": ilo_target_fingerprint(host),
        "identity_fingerprint_sha256": "a" * 64,
        "candidate_index": candidate_index,
        "target_candidate_count": candidate_count,
        "exact_target_only": candidate_index == 1 and candidate_count == 1,
        "authenticated": True,
        "read_only_collection": True,
        "inventory_complete": True,
        "identity_verified": True,
    }
    evidence["evidence_digest_sha256"] = (
        ilo_write_target.ilo_write_evidence_digest(evidence)
    )
    return {
        "provider_id": "ilo-redfish",
        "status": "ok",
        "checked_at": checked_at.isoformat(),
        "target_source": "operator_first_contact",
        "target_fingerprint": ilo_target_fingerprint(host),
        "candidate_index": candidate_index,
        "target_candidate_count": candidate_count,
        "write_target_evidence": evidence,
    }


def _context(*, identity: str) -> ilo_write_target.IloWriteTargetContext:
    return ilo_write_target.IloWriteTargetContext(
        current_access_host=CURRENT_ACCESS_HOST,
        target_fingerprint=ilo_target_fingerprint(CURRENT_ACCESS_HOST) or "",
        identity_fingerprint_sha256=identity,
        evidence_digest_sha256="b" * 64,
        evidence_checked_at=NOW,
        target_source="operator_first_contact",
    )


def _exact_config() -> IloRedfishConfig:
    return IloRedfishConfig(
        host=CURRENT_ACCESS_HOST,
        username="operator",
        password="secret",
        verify_tls=False,
        timeout_seconds=3.0,
        host_source="exact_write_target_context",
    )
