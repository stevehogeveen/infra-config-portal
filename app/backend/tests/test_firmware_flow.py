from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import AuditEvent, FirmwareApproval, GuardedOperation
from app.services.audit import record_audit_event
from app.services.firmware_worker import PreparedFirmware


@pytest.fixture(params=[("1.37", "1.48"), ("1.48", "3.19")])
def flow(client, db_session, monkeypatch, request):
    installed, target = request.param
    kit = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Firmware fixture",
            "profile_topology": "custom",
            "subnet_cidr": "192.0.2.0/24",
        },
    ).json()
    base = "/api/v1/rack-plans/" + kit["id"]
    plan = client.put(
        base,
        json={
            "equipment": [
                {"id": "server", "name": "Fixture", "kind": "server", "position": 1, "height": 1}
            ]
        },
    ).json()
    device = plan["equipment"][0]["device_id"]
    capabilities = {
        "profile_id": kit["id"],
        "device_id": device,
        "checked_at": datetime.now(UTC).isoformat(),
        "source": "live-ilo-firmware-capabilities",
        "authenticated": True,
        "exact_target_only": True,
        "identity_verified": True,
        "state": "Idle",
        "http_push_uri": "/cgi-bin/uploadFile",
        "target_identity_sha256": "a" * 64,
        "target_fingerprint": "b" * 16,
        "manager_firmware_version": installed,
        "inventory": [{"targets": ["fixture-target"], "updateable": True, "version": installed}],
        "system_health": "OK",
        "health_issues": [],
        "ilo_update_health": {"scope": "ilo-only-v1", "blockers": [], "warnings": []},
        "errors": [],
    }
    record_audit_event(
        db_session,
        actor="fixture",
        event_type="kit.firmware_package_selected",
        message="Fixture SPP",
        data={"profile_id": kit["id"], "package": {"fixture": True}},
    )
    capevent = record_audit_event(
        db_session,
        actor="fixture",
        event_type="kit.firmware_capabilities_read",
        message="Fixture only",
        data=capabilities,
    )
    db_session.commit()
    bridge = {"sha256": "c" * 64, "payload": {"binary": {"sha256": "d" * 64}}}
    auth = {
        "binary_authenticated": True,
        "component_sha256": "c" * 64,
        "binary": {"sha256": "d" * 64, "size_bytes": 100},
        "authenticated_declaration": {
            "version": target,
            "direct_flash": True,
            "host_power_change_required": False,
            "targets": ["fixture-target"],
        },
    }
    monkeypatch.setenv("LAB_ALLOWED_WRITE_ACTIONS", "ilo.firmware-update")
    monkeypatch.setattr(
        "app.services.firmware_flow.current_lab_action_policy",
        lambda: SimpleNamespace(action_blockers=lambda *args: []),
    )
    monkeypatch.setattr("app.services.firmware_flow.inspect_spp_bridge", lambda p, *args: bridge)
    monkeypatch.setattr("app.services.firmware_flow.verify_bridge_from_spp", lambda p, b: auth)
    calls = {"prepare": 0, "send": 0, "reads": 0, "lost": False, "reject": False}

    class Adapter:
        def __init__(self, session):
            pass

        def prepare(self, review):
            calls["prepare"] += 1
            return PreparedFirmware(
                review.intent_json, ("changed target",) if calls["reject"] else (), None
            )

        def send(self, prepared):
            calls["send"] += 1
            if calls["lost"]:
                raise TimeoutError("SECRET")

    def read(*args):
        calls["reads"] += 1
        return {
            **capabilities,
            "checked_at": datetime.now(UTC).isoformat(),
            "manager_firmware_version": target,
        }

    monkeypatch.setattr("app.services.firmware_flow.HpeFirmwareAdapter", Adapter)
    monkeypatch.setattr("app.services.firmware_flow.collect_firmware_capabilities", read)
    return base + "/firmware-execution", {"device_id": device}, calls, capevent


def test_preview_apply_duplicate_explicit_verify_and_recorded_status(client, db_session, flow):
    base, params, calls, _ = flow
    preview = client.post(base + "/preview", params=params, json={}).json()
    assert preview["can_apply"] is True
    target = preview["operations"][0]["package_version"]
    assert target in {"1.48", "3.19"}
    assert preview["confirmation_phrase"] == f"INSTALL ILO {target}"
    assert preview["blocker_details"] == []
    assert "iLO will reset" in preview["message"]
    assert "Keep power connected" in preview["message"]
    assert preview["operations"][0]["file"] == f"ilo5_{target.replace('.', '')}.bin"
    assert calls == {"prepare": 0, "send": 0, "reads": 0, "lost": False, "reject": False}
    body = {
        "review_token": preview["review_token"],
        "confirmation_phrase": preview["confirmation_phrase"],
        "idempotency_key": "fixture-attempt",
    }
    first = client.post(base + "/apply", params=params, json=body)
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["status"] == "running"
    assert (
        client.post(base + "/apply", params=params, json=body).json()["operation_id"]
        == result["operation_id"]
    )
    assert calls["prepare"] == calls["send"] == 1
    assert client.get(base + "/status", params=params).json()["evidence_at"] is None
    assert calls["reads"] == 0
    verify = {"operation_id": result["operation_id"], "confirm_read_only": True}
    assert (
        client.post(
            base + "/verify", params=params, json={**verify, "confirm_read_only": False}
        ).status_code
        == 409
    )
    assert calls["reads"] == 0
    completed = client.post(base + "/verify", params=params, json=verify)
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "verified"
    status = client.get(base + "/status", params=params).json()
    assert status["evidence_at"] == completed.json()["evidence_at"]
    assert calls["reads"] == 1
    assert db_session.scalar(select(GuardedOperation)).active_device is None
    # Even after completion, a different attempt key cannot reuse this approval.
    assert (
        client.post(
            base + "/apply", params=params, json={**body, "idempotency_key": "another"}
        ).status_code
        == 409
    )
    assert calls["send"] == 1


def test_preparation_selects_version_from_recorded_capabilities(
    client, db_session, flow, monkeypatch
):
    base, params, calls, event = flow
    from app.services.firmware_catalog import next_ilo_version

    target = next_ilo_version(event.data_json["manager_firmware_version"])

    def inspect(package, version="1.48"):
        assert version == target
        return {"payload": {"declared_version": version}}

    monkeypatch.setattr("app.api.firmware_execution.inspect_spp_bridge", inspect)
    monkeypatch.setattr(
        "app.api.firmware_execution.verify_bridge_from_spp",
        lambda p, b: {"binary_authenticated": True},
    )
    result = client.post(base + "/prepare-spp-bridge", params=params, json={})
    assert result.status_code == 200, result.text
    assert result.json()["target_version"] == target
    assert result.json()["can_apply"] is False
    assert calls["reads"] == calls["send"] == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("state", "Updating"),
        ("ilo_update_health", None),
        ("errors", ["Update service error"]),
        ("errors", None),
        ("checked_at", "2000-01-01T00:00:00Z"),
        ("identity_verified", False),
        ("inventory", []),
        ("ilo_update_health", {"scope": "ilo-only-v1", "blockers": ["Power fault"]}),
    ],
)
def test_missing_or_stale_capability_never_issues_approval(client, db_session, flow, field, value):
    base, params, calls, event = flow
    event.data_json = {**event.data_json, field: value}
    db_session.commit()
    preview = client.post(base + "/preview", params=params, json={}).json()
    assert preview["can_apply"] is False
    assert preview["blockers"]
    assert not list(db_session.scalars(select(FirmwareApproval)))
    assert calls["reads"] == calls["send"] == 0


def test_storage_warnings_are_reviewed_without_clearing_them(client, db_session, flow):
    base, params, calls, event = flow
    warning = {"group": "Drive", "health": "Warning", "title": "Erased disk"}
    event.data_json = {
        **event.data_json,
        "system_health": "Warning",
        "health_issues": [warning],
        "ilo_update_health": {"scope": "ilo-only-v1", "blockers": [], "warnings": [warning]},
    }
    db_session.commit()
    preview = client.post(base + "/preview", params=params, json={}).json()
    assert preview["can_apply"] is True
    assert preview["warnings"] == [warning]
    assert "Keep power connected" in preview["message"]
    approval = db_session.scalar(select(FirmwareApproval))
    assert approval.intent_json["ilo_update_health"]["warnings"] == [warning]
    assert calls["reads"] == calls["send"] == 0


def test_lost_response_preserves_lock_and_no_secrets(client, db_session, flow):
    base, params, calls, _ = flow
    preview = client.post(base + "/preview", params=params, json={}).json()
    body = {
        "review_token": preview["review_token"],
        "confirmation_phrase": preview["confirmation_phrase"],
        "idempotency_key": "fixture-lost",
    }
    calls["lost"] = True
    result = client.post(base + "/apply", params=params, json=body).json()
    assert result["status"] == "uncertain"
    assert client.post(base + "/apply", params=params, json=body).json()["status"] == "uncertain"
    assert calls["send"] == 1
    assert db_session.scalar(select(GuardedOperation)).active_device == params["device_id"]
    assert "SECRET" not in str(
        [(e.message, e.data_json) for e in db_session.scalars(select(AuditEvent))]
    )


def test_changed_preflight_does_not_consume_or_send(client, db_session, flow):
    base, params, calls, _ = flow
    preview = client.post(base + "/preview", params=params, json={}).json()
    calls["reject"] = True
    response = client.post(
        base + "/apply",
        params=params,
        json={
            "review_token": preview["review_token"],
            "confirmation_phrase": preview["confirmation_phrase"],
            "idempotency_key": "changed",
        },
    )
    assert response.status_code == 409
    assert not list(db_session.scalars(select(GuardedOperation)))
    assert db_session.scalar(select(FirmwareApproval)).operation_id is None
    assert calls["send"] == 0


def test_missing_send_is_fenced_before_late_request(client, db_session, flow):
    base, params, calls, _ = flow
    preview = client.post(base + "/preview", params=params, json={}).json()
    body = {
        "review_token": preview["review_token"],
        "confirmation_phrase": preview["confirmation_phrase"],
        "idempotency_key": "lost-before-server",
    }
    before = client.get(
        base + "/reconcile", params={**params, "idempotency_key": body["idempotency_key"]}
    ).json()
    assert before["record_found"] is False
    closed = client.post(
        base + "/reconcile-unsent",
        params=params,
        json={
            "review_token": body["review_token"],
            "idempotency_key": body["idempotency_key"],
            "prevent_late_dispatch": True,
        },
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["dispatch_prevented"] is True
    assert closed.json()["status"] == "failed"
    late = client.post(base + "/apply", params=params, json=body)
    assert late.status_code == 200
    assert late.json()["dispatch_prevented"] is True
    assert calls["prepare"] == calls["send"] == calls["reads"] == 0
    assert db_session.scalar(select(GuardedOperation)).active_device is None


def test_reconcile_cannot_cancel_claimed_or_invent_legacy_proof(client, flow):
    base, params, calls, _ = flow
    assert (
        client.post(
            base + "/reconcile-unsent",
            params=params,
            json={
                "review_token": "legacy-missing",
                "idempotency_key": "legacy",
                "prevent_late_dispatch": True,
            },
        ).status_code
        == 409
    )
    preview = client.post(base + "/preview", params=params, json={}).json()
    body = {
        "review_token": preview["review_token"],
        "confirmation_phrase": preview["confirmation_phrase"],
        "idempotency_key": "sent",
    }
    client.post(base + "/apply", params=params, json=body)
    closed = client.post(
        base + "/reconcile-unsent",
        params=params,
        json={
            "review_token": body["review_token"],
            "idempotency_key": "sent",
            "prevent_late_dispatch": True,
        },
    )
    assert closed.json()["status"] == "running"
    assert not closed.json().get("dispatch_prevented")
    assert calls["send"] == 1
