from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditEvent, GuardedOperation, RuntimeDispatchLease
from app.services.firmware_completion import complete_from_readback
from app.services.firmware_recovery import PHRASE, close_unverified, preview_closure
from app.services.guarded_operation_ledger import OperationConflict, mark_uncertain
from test_firmware_reviews import Adapter, execute, issued as issued


@pytest.fixture
def uncertain(db_session, issued):
    result = execute(db_session, issued, Adapter())
    operation_id = result["operation_id"]
    mark_uncertain(db_session, operation_id, actor="fixture")
    dispatch = db_session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "guarded.operation.dispatch_claimed")
    )
    dispatch.created_at = datetime.now(UTC) - timedelta(minutes=12)
    db_session.commit()
    observation = {
        "source": "live-ilo-firmware-readback",
        "authenticated": True,
        "exact_target_only": True,
        "identity_verified": True,
        "device_id": "device",
        "target_identity_sha256": "a" * 64,
        "manager_firmware_version": "1.37",
        "checked_at": datetime.now(UTC).isoformat(),
        "update_state": "Idle",
        "errors": [],
    }
    complete_from_readback(
        db_session,
        profile_id="kit",
        device_id="device",
        operation_id=operation_id,
        observation=observation,
        actor="fixture",
    )
    return dict(profile_id="kit", device_id="device", operation_id=operation_id, actor="fixture")


def test_review_does_not_unlock_and_explicit_close_keeps_uncertainty(db_session, uncertain):
    preview = preview_closure(db_session, **uncertain)
    assert preview["can_close"]
    assert db_session.get(GuardedOperation, uncertain["operation_id"]).active_device == "device"
    closed = close_unverified(
        db_session, **uncertain, review_token=preview["review_token"], confirmation_phrase=PHRASE
    )
    assert closed["status"] == "failed"
    assert closed["resolution"] == "operator_closed_unverified"
    assert closed["dispatch_prevented"] is False
    assert closed["safe_to_retry"] is False
    assert db_session.get(GuardedOperation, uncertain["operation_id"]).active_device is None
    with pytest.raises(OperationConflict):
        close_unverified(
            db_session,
            **uncertain,
            review_token=preview["review_token"],
            confirmation_phrase=PHRASE,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"update_state": "Updating"},
        {"update_state": "Complete"},
        {"manager_firmware_version": "1.48"},
        {"manager_firmware_version": "1.38"},
        {"identity_verified": False},
        {"target_identity_sha256": "b" * 64},
        {"device_id": "other"},
        {"errors": None},
        {"checked_at": "2000-01-01T00:00:00Z"},
        {"checked_at": "invalid"},
    ],
)
def test_operator_abandonment_does_not_require_health_or_fresh_readback(
    db_session, uncertain, change
):
    event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "firmware.readback.unproven")
    )
    event.data_json = {
        **event.data_json,
        "observation": {**event.data_json["observation"], **change},
    }
    db_session.commit()
    preview = preview_closure(db_session, **uncertain)
    assert preview["can_close"]
    closed = close_unverified(
        db_session, **uncertain, review_token=preview["review_token"], confirmation_phrase=PHRASE
    )
    assert closed["resolution"] == "operator_closed_unverified"
    assert closed["dispatch_prevented"] is False


@pytest.mark.parametrize("case", ["recent", "lease", "running", "missing_evidence"])
def test_wait_and_dispatch_guards(db_session, uncertain, case):
    if case == "recent":
        event = db_session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "guarded.operation.dispatch_claimed")
        )
        event.created_at = datetime.now(UTC) - timedelta(minutes=2)
    elif case == "lease":
        db_session.add(RuntimeDispatchLease(action_id="ilo.firmware-update"))
    elif case == "running":
        db_session.get(GuardedOperation, uncertain["operation_id"]).status = "running"
    else:
        event = db_session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "firmware.readback.unproven")
        )
        event.data_json = {"operation_id": uncertain["operation_id"]}
    db_session.commit()
    assert preview_closure(db_session, **uncertain)["can_close"] == (
        case in {"recent", "missing_evidence"}
    )


@pytest.mark.parametrize("case", ["actor", "token", "phrase", "expired", "scope"])
def test_apply_rechecks_review_and_evidence(db_session, uncertain, case):
    preview = preview_closure(db_session, **uncertain)
    args = {**uncertain, "review_token": preview["review_token"], "confirmation_phrase": PHRASE}
    if case == "actor":
        args["actor"] = "someone-else"
    elif case == "token":
        args["review_token"] = "wrong"
    elif case == "phrase":
        args["confirmation_phrase"] = "wrong"
    elif case == "scope":
        args["device_id"] = "wrong"
    elif case == "expired":
        event = db_session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "firmware.recovery.review")
        )
        event.data_json = {**event.data_json, "expires_at": "2000-01-01T00:00:00+00:00"}
        db_session.commit()
    with pytest.raises(OperationConflict):
        close_unverified(db_session, **args)
    db_session.rollback()
    assert db_session.get(GuardedOperation, uncertain["operation_id"]).active_device == "device"


def test_explicit_close_without_any_readback(db_session, uncertain):
    event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "firmware.readback.unproven")
    )
    db_session.delete(event)
    db_session.commit()
    preview = preview_closure(db_session, **uncertain)
    assert preview["can_close"]
    closed = close_unverified(
        db_session, **uncertain, review_token=preview["review_token"], confirmation_phrase=PHRASE
    )
    assert closed["resolution"] == "operator_closed_unverified"
    assert closed["dispatch_prevented"] is False


def test_http_contract_does_not_accept_client_evidence_or_implicit_closure(
    client, db_session, uncertain, monkeypatch
):
    from app.api import firmware_execution as api

    monkeypatch.setattr(api, "server_in_kit", lambda *args: None)
    base = "/api/v1/rack-plans/kit/firmware-execution"
    params = {"device_id": "device"}
    body = {"operation_id": uncertain["operation_id"]}
    headers = {"X-Local-User": "fixture"}
    assert (
        client.post(
            base + "/recovery-preview",
            params=params,
            json={**body, "observation": {"update_state": "Idle"}},
        ).status_code
        == 422
    )
    response = client.post(base + "/recovery-preview", params=params, json=body, headers=headers)
    assert response.status_code == 200
    preview = response.json()
    assert preview["can_close"]
    closure = {**body, "review_token": preview["review_token"], "confirmation_phrase": ""}
    assert (
        client.post(
            base + "/close-unverified", params=params, json=closure, headers=headers
        ).status_code
        == 409
    )
    closure["confirmation_phrase"] = PHRASE
    result = client.post(base + "/close-unverified", params=params, json=closure, headers=headers)
    assert result.status_code == 200
    assert result.json()["resolution"] == "operator_closed_unverified"


def test_a_running_install_read_back_on_the_target_version_can_be_closed(db_session, uncertain):
    # Observed live 2026-09-29: 1.48 -> 3.19 installed, but the iLO's own identity changed, so the
    # completion match failed and the operation stayed "running". Idle + target version = finished.
    from app.models import FirmwareApproval
    op = db_session.get(GuardedOperation, uncertain["operation_id"])
    op.status = "running"
    target = db_session.scalar(select(FirmwareApproval).where(FirmwareApproval.operation_id == op.id)).intent_json["target_version"]
    event = db_session.scalar(select(AuditEvent).where(AuditEvent.event_type == "firmware.readback.unproven"))
    event.data_json = {**event.data_json, "observation": {**event.data_json["observation"], "manager_firmware_version": f"iLO 5 v{target}"}}
    db_session.commit()
    assert preview_closure(db_session, **uncertain)["can_close"] is True
    event.data_json = {**event.data_json, "observation": {**event.data_json["observation"], "update_state": "Updating"}}
    db_session.commit()
    assert preview_closure(db_session, **uncertain)["can_close"] is False


def test_a_finished_running_install_closes_through_the_normal_close_out(db_session, uncertain):
    from app.models import FirmwareApproval
    op = db_session.get(GuardedOperation, uncertain["operation_id"])
    op.status = "running"
    target = db_session.scalar(select(FirmwareApproval).where(FirmwareApproval.operation_id == op.id)).intent_json["target_version"]
    event = db_session.scalar(select(AuditEvent).where(AuditEvent.event_type == "firmware.readback.unproven"))
    event.data_json = {**event.data_json, "observation": {**event.data_json["observation"], "manager_firmware_version": f"iLO 5 v{target}"}}
    db_session.commit()
    review = preview_closure(db_session, **uncertain)
    result = close_unverified(db_session, **uncertain, review_token=review["review_token"], confirmation_phrase=review["confirmation_phrase"])
    assert result["status"] == "failed"
    assert db_session.get(GuardedOperation, op.id).active_device is None
