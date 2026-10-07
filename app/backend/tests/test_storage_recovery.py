from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from app.services.storage_recovery import confirmed_rejection


@pytest.fixture
def evidence():
    now = datetime.now(UTC)
    snapshot = {"identity": "fixture", "pending_differs": False, "current": {
        "@Redfish.Settings": {"Time": (now - timedelta(seconds=10)).isoformat(),
        "Messages": [{"MessageId": "SmartStorageMessages.2.0.1.CanCreateEditableConfigControllerStatusNotOK"}]}}}
    return snapshot, {"identity": "fixture", "operation": "clear"}, now - timedelta(minutes=1)


def test_timed_target_matched_rejection_is_terminal(evidence):
    assert confirmed_rejection(*evidence)


def test_reset_missing_logical_drives_is_terminal_only_with_exact_evidence(evidence):
    snapshot, attempt, boot = evidence
    attempt['operation'] = 'reset'
    settings = snapshot['current']['@Redfish.Settings']
    settings['Messages'] = [
        {'MessageId': 'SmartStorageMessages.2.0.1.PropertyKeyMissing', 'MessageArgs': ['LogicalDrives']},
        {'MessageId': 'SmartStorageMessages.2.0.1.Success'},
    ]
    assert 'missing LogicalDrives' in confirmed_rejection(snapshot, attempt, boot)['message']
    snapshot['pending_differs'] = True
    assert confirmed_rejection(snapshot, attempt, boot) is None
    snapshot['pending_differs'] = False
    settings['Time'] = (boot - timedelta(seconds=1)).isoformat()
    assert confirmed_rejection(snapshot, attempt, boot) is None


@pytest.mark.parametrize("fault", ["identity", "pending", "no_boot", "old", "future", "no_time", "naive", "other_error", "reset"])
def test_uncertain_evidence_never_releases_operation(evidence, fault):
    snapshot, attempt, boot = deepcopy(evidence)
    settings = snapshot["current"]["@Redfish.Settings"]
    if fault == "identity": snapshot["identity"] = "other"
    if fault == "pending": snapshot["pending_differs"] = True
    if fault == "no_boot": boot = None
    if fault == "old": settings["Time"] = (boot - timedelta(seconds=1)).isoformat()
    if fault == "future": settings["Time"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    if fault == "no_time": settings.pop("Time")
    if fault == "naive": settings["Time"] = datetime.now().isoformat()
    if fault == "other_error": settings["Messages"].append({"MessageId": "Base.1.0.Unknown"})
    if fault == "reset": attempt["operation"] = "reset"
    assert confirmed_rejection(snapshot, attempt, boot) is None
