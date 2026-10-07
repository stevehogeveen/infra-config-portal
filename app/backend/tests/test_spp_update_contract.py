from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.services.spp_update_contract import ApplyRequest, PlanRequest, Step, UpdateStatus


def step(**changes):
    now = datetime.now(UTC)
    return {
        "step_id": "ilo-first",
        "component": "iLO",
        "from": "1.37",
        "to": "1.48",
        "order": 1,
        "restarts": "ilo",
        "state": "done",
        "started_at": now - timedelta(minutes=2),
        "finished_at": now,
        "verified_version": "1.48",
        **changes,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"verified_version": None},
        {"verified_version": "3.19"},
        {"finished_at": None},
        {"state": "installing"},
        {"started_at": datetime(2026, 1, 1)},
        {"finished_at": datetime(2000, 1, 1, tzinfo=UTC)},
    ],
)
def test_done_requires_reviewed_version_and_timestamp(change):
    with pytest.raises(ValidationError):
        Step.model_validate(step(**change))


def status(**changes):
    return {
        "profile_id": "kit",
        "device_id": "srv",
        "operation_id": "run",
        "idempotency_key": "attempt",
        "status": "verified",
        "steps": [Step.model_validate(step())],
        "current_step": None,
        "message": "Updates verified.",
        "next_action": None,
        "evidence_at": datetime.now(UTC),
        "active": False,
        **changes,
    }


def test_wire_contract_preserves_from_alias():
    value = UpdateStatus.model_validate(status()).model_dump(mode="json", by_alias=True)
    assert value["steps"][0]["from"] == "1.37"
    assert "from_version" not in value["steps"][0]


@pytest.mark.parametrize(
    "change",
    [
        {"steps": []},
        {"active": True},
        {"evidence_at": None},
        {"evidence_at": datetime(2026, 1, 1)},
        {"operation_id": None},
        {"idempotency_key": None},
        {"current_step": "other"},
        {"status": "uncertain"},
        {"dispatch_prevented": True},
    ],
)
def test_invalid_progress_cannot_claim_completion(change):
    with pytest.raises(ValidationError):
        UpdateStatus.model_validate(status(**change))


def test_uncertain_first_step_cannot_be_followed_by_another_dispatch():
    first = Step.model_validate(step(state="uncertain", verified_version=None, finished_at=None))
    second = Step.model_validate(
        step(
            step_id="ilo-second",
            order=2,
            **{"from": "1.48", "to": "3.19", "verified_version": "3.19"},
        )
    )
    with pytest.raises(ValidationError, match="later step"):
        UpdateStatus.model_validate(status(status="uncertain", active=True, steps=[first, second]))


def test_partial_failure_keeps_verified_steps_and_unstarted_remainder():
    first = Step.model_validate(step())
    second = Step.model_validate(
        step(step_id="ilo-second", order=2, state="failed", verified_version=None)
    )
    third = Step.model_validate(
        step(
            step_id="rom",
            order=3,
            state="not_started",
            started_at=None,
            finished_at=None,
            verified_version=None,
        )
    )
    result = UpdateStatus.model_validate(status(status="failed", steps=[first, second, third]))
    assert result.steps[0].verified_version == "1.48"
    assert result.steps[2].started_at is None


def test_request_cannot_choose_host_or_commands():
    with pytest.raises(ValidationError):
        PlanRequest(device_id="srv", host="192.0.2.1")
    with pytest.raises(ValidationError):
        ApplyRequest(
            review_token="opaque",
            confirmation_phrase="APPROVE",
            idempotency_key="key",
            commands=["deploy"],
        )
    with pytest.raises(ValidationError):
        ApplyRequest(
            review_token="opaque", confirmation_phrase="APPROVE", idempotency_key="bad key"
        )
