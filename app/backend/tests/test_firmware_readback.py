from datetime import UTC, datetime, timedelta

import pytest

from app.services.firmware_readback import evaluate_ilo_readback

NOW = datetime(2026, 9, 28, 17, tzinfo=UTC)


def observation():
    return {"checked_at": (NOW - timedelta(seconds=10)).isoformat(),
            "source": "live-ilo-firmware-readback", "authenticated": True,
            "exact_target_only": True, "identity_verified": True,
            "device_id": "fixture", "target_identity_sha256": "a" * 64,
            "manager_firmware_version": "iLO 5 v3.19", "update_state": "Complete",
            "errors": []}


def evaluate(data):
    return evaluate_ilo_readback(
        device_id="fixture", target_identity_sha256="a" * 64, target_version="3.19",
        submitted_at=NOW - timedelta(minutes=1), observation=data, now=NOW,
    )


def test_only_fresh_independent_target_version_readback_verifies():
    result = evaluate(observation())
    assert result["status"] == "verified"
    assert result["evidence_at"]
    assert result["safe_to_retry"] is False


@pytest.mark.parametrize("field,value", [
    ("device_id", "other"), ("target_identity_sha256", "b" * 64),
    ("source", "mock"), ("authenticated", False), ("exact_target_only", False),
    ("identity_verified", False), ("manager_firmware_version", "iLO 5 v1.37"),
    ("manager_firmware_version", "unknown"), ("update_state", "Updating"),
    ("update_state", None), ("errors", None), ("errors", ["signature rejected"]),
    ("checked_at", None), ("checked_at", "2026-09-28T17:00:01+00:00"),
    ("checked_at", "2026-09-28T16:58:00+00:00"),
    ("checked_at", "2026-09-28T16:59:50"),
])
def test_missing_stale_wrong_or_unfinished_evidence_stays_uncertain(field, value):
    data = observation()
    data[field] = value
    result = evaluate(data)
    assert result["status"] == "uncertain"
    assert result["evidence_at"] is None
    assert result["blockers"]


def test_http_acceptance_is_not_completion():
    assert evaluate({"status_code": 200})["status"] == "uncertain"


def test_hardware_identity_is_compared_when_the_review_recorded_it():
    # iLO 1.48 -> 3.19 changed the manager's own identity fields; the server hardware did not.
    data = {**observation(), "target_identity_sha256": "c" * 64, "target_hardware_identity_sha256": "d" * 64}
    result = evaluate_ilo_readback(
        device_id="fixture", target_identity_sha256="a" * 64, target_hardware_identity_sha256="d" * 64,
        target_version="3.19", submitted_at=NOW - timedelta(minutes=1), observation=data, now=NOW,
    )
    assert result["status"] == "verified"


def test_a_different_server_hardware_identity_is_still_refused():
    data = {**observation(), "target_hardware_identity_sha256": "e" * 64}
    result = evaluate_ilo_readback(
        device_id="fixture", target_identity_sha256="a" * 64, target_hardware_identity_sha256="d" * 64,
        target_version="3.19", submitted_at=NOW - timedelta(minutes=1), observation=data, now=NOW,
    )
    assert result["status"] == "uncertain"
    assert "Readback does not match the reviewed hardware identity." in result["blockers"]
