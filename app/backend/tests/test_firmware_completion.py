from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import AuditEvent, GuardedOperation
from app.services.firmware_completion import complete_from_readback
from app.services.guarded_operation_ledger import OperationConflict
from test_firmware_reviews import Adapter, execute, issued as issued


def observed():
    return {
        "source": "live-ilo-firmware-readback",
        "authenticated": True,
        "exact_target_only": True,
        "identity_verified": True,
        "device_id": "device",
        "target_identity_sha256": "a" * 64,
        "manager_firmware_version": "1.48",
        "checked_at": datetime.now(UTC).isoformat(),
        "update_state": "Idle",
        "errors": [],
    }


def test_readback_commits_evidence_and_releases_only_exact_operation(db_session, issued):
    result = execute(db_session, issued, Adapter())
    observation = observed()
    completed = complete_from_readback(
        db_session,
        profile_id="kit",
        device_id="device",
        operation_id=result["operation_id"],
        observation=observation,
        actor="fixture",
    )
    assert completed["status"] == "verified"
    assert completed["evidence_at"] == observation["checked_at"]
    assert db_session.get(GuardedOperation, result["operation_id"]).active_device is None
    again = complete_from_readback(
        db_session,
        profile_id="kit",
        device_id="device",
        operation_id=result["operation_id"],
        observation={},
        actor="fixture",
    )
    assert again == completed
    assert (
        len(
            list(
                db_session.scalars(
                    select(AuditEvent).where(AuditEvent.event_type == "firmware.operation.verified")
                )
            )
        )
        == 1
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"device_id": "wrong"},
        {"manager_firmware_version": "1.37"},
        {"errors": None},
        {"authenticated": False},
        {"checked_at": "2000-01-01T00:00:00Z"},
    ],
)
def test_unproven_readback_retains_lock(db_session, issued, changes):
    result = execute(db_session, issued, Adapter())
    completed = complete_from_readback(
        db_session,
        profile_id="kit",
        device_id="device",
        operation_id=result["operation_id"],
        observation={**observed(), **changes},
        actor="fixture",
    )
    assert completed["status"] != "verified"
    assert completed["evidence_at"] is None
    assert db_session.get(GuardedOperation, result["operation_id"]).active_device == "device"


def test_cross_scope_cannot_complete(db_session, issued):
    result = execute(db_session, issued, Adapter())
    with pytest.raises(OperationConflict):
        complete_from_readback(
            db_session,
            profile_id="wrong",
            device_id="device",
            operation_id=result["operation_id"],
            observation=observed(),
            actor="fixture",
        )
