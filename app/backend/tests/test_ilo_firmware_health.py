from copy import deepcopy

import pytest

from app.providers.ilo_redfish import _thermal_summary
from app.services.ilo_firmware_health import assess_ilo_firmware_health


@pytest.fixture
def probe():
    ok = {"Health": "OK", "State": "Enabled"}
    return {
        "managers": [{"Status": deepcopy(ok)}],
        "systems": [{"Status": {"Health": "Warning"}}],
        "power": [
            {
                "PowerSupplies": [
                    {"MemberId": "1", "Status": deepcopy(ok), "LineInputVoltage": 230},
                    {
                        "MemberId": "2",
                        "Status": {"Health": "Warning", "State": "Enabled"},
                        "LineInputVoltage": 0,
                        "PowerSupplyType": "AC",
                    },
                ]
            }
        ],
        "thermal": [
            _thermal_summary(
                {"Fans": [{"Status": deepcopy(ok)}], "Temperatures": [{"Status": deepcopy(ok)}]}
            )
        ],
        "storage": {
            "physical_drives": [
                {
                    "Id": "1",
                    "Model": "Fixture drive",
                    "CapacityBytes": 100,
                    "Status": {"Health": "Warning"},
                    "DiskDriveStatusReasons": ["EraseCompleted"],
                },
                {"Id": "2", "Status": {"Health": "Warning", "State": "Absent"}},
            ],
            "controllers": [
                {
                    "Model": "Fixture controller",
                    "Status": {"Health": "Warning"},
                    "BackupPowerSourceStatus": "NotPresent",
                }
            ],
        },
    }


def test_storage_and_single_feed_warnings_do_not_block_ilo_only(probe):
    original = deepcopy(probe)
    assessment = assess_ilo_firmware_health(probe)
    assert assessment["blockers"] == []
    assert {w["group"] for w in assessment["warnings"]} >= {
        "Drive",
        "Controller",
        "Power",
        "Server",
    }
    assert len(assessment["assessment_sha256"]) == 64
    assert all(isinstance(w.get("details", ""), str) for w in assessment["warnings"])
    assert probe == original


@pytest.mark.parametrize(
    "change",
    [
        "bmc",
        "no-power",
        "bad-power",
        "unknown-power",
        "cooling",
        "missing-thermal",
        "absent-sensors",
        "active",
        "critical",
    ],
)
def test_operation_relevant_faults_still_block(probe, change):
    if change == "bmc":
        probe["managers"][0]["Status"]["Health"] = "Warning"
    elif change == "no-power":
        probe["power"][0]["PowerSupplies"][0]["LineInputVoltage"] = 0
    elif change == "bad-power":
        probe["power"][0]["PowerSupplies"][0]["Status"]["Health"] = "Critical"
    elif change == "unknown-power":
        probe["power"][0]["PowerSupplies"][0].pop("LineInputVoltage")
    elif change == "cooling":
        probe["thermal"][0]["Fans"][0]["Status"]["Health"] = "Critical"
    elif change == "missing-thermal":
        probe["thermal"] = [_thermal_summary({})]
    elif change == "absent-sensors":
        probe["thermal"][0]["Fans"][0]["Status"]["State"] = "Absent"
    elif change == "active":
        probe["storage"]["physical_drives"][0]["DiskDriveStatusReasons"] = ["EraseInProgress"]
    else:
        probe["systems"][0]["Status"]["Health"] = "Critical"
    assert assess_ilo_firmware_health(probe)["blockers"]


def test_warning_change_invalidates_assessment(probe):
    before = assess_ilo_firmware_health(probe)
    probe["storage"]["physical_drives"][0]["Status"]["Health"] = "Critical"
    after = assess_ilo_firmware_health(probe)
    assert before["assessment_sha256"] != after["assessment_sha256"]


@pytest.mark.parametrize("value", [None, [], [{"Status": {}}] * 129, ["invalid"]])
def test_incomplete_thermal_inventory_is_not_clearance(value):
    assert (
        _thermal_summary({"Fans": value, "Temperatures": value})["sensor_inventory_complete"]
        is False
    )


SELF_TESTS = [
    {"name": "NVRAMData", "status": "OK", "notes": ""},
    {"name": "EmbeddedFlash", "status": "OK", "notes": "Controller firmware revision 2.10.00"},
    {"name": "PowerManagementController", "status": "Informational", "notes": "Version 1.0.4"},
]


def test_ilo5_137_without_manager_health_passes_on_its_self_tests(probe):
    # iLO 5 1.37 reports manager Status {"State": "Enabled"} with no Health (observed 2026-09-29).
    probe["managers"] = [{"Status": {"State": "Enabled"}, "ilo_self_tests": deepcopy(SELF_TESTS)}]
    assert assess_ilo_firmware_health(probe)["blockers"] == []


def test_a_failing_self_test_is_named(probe):
    tests = deepcopy(SELF_TESTS)
    tests[1]["status"] = "Degraded"
    probe["managers"] = [{"Status": {"State": "Enabled"}, "ilo_self_tests": tests}]
    assert assess_ilo_firmware_health(probe)["blockers"] == [
        "iLO self-test EmbeddedFlash reports Degraded: Controller firmware revision 2.10.00."
    ]


def test_reported_manager_health_is_named(probe):
    probe["managers"][0]["Status"]["Health"] = "Warning"
    result = assess_ilo_firmware_health(probe)
    assert "The iLO reports its own health as Warning (State Enabled)." in result["blockers"]
    assert result["blocker_details"][0]["code"] == "ilo_health_reported"
    assert result["blocker_details"][0]["action"] == "read_again"


def test_no_health_and_no_self_tests_is_unknown_not_healthy(probe):
    probe["managers"] = [{"Status": {"State": "Enabled"}}]
    assert assess_ilo_firmware_health(probe)["blockers"] == [
        "The iLO did not report its health or any self-test results, so its health is unknown."
    ]


def test_manager_count_is_stated(probe):
    probe["managers"] = []
    assert assess_ilo_firmware_health(probe)["blockers"] == [
        "Exactly one iLO must answer; this read found 0."
    ]


def test_resource_summary_keeps_ilo_self_tests():
    from app.providers.ilo_redfish import _resource_summary

    summary = _resource_summary(
        {
            "Status": {"State": "Enabled"},
            "Oem": {
                "Hpe": {
                    "iLOSelfTestResults": [
                        {"SelfTestName": "EEPROM", "Status": "OK", "Notes": " "},
                        "not-a-dict",
                    ]
                }
            },
        }
    )
    assert summary["ilo_self_tests"] == [{"name": "EEPROM", "status": "OK", "notes": ""}]


def test_local_lab_health_is_advisory_but_operation_conflicts_remain(probe, monkeypatch):
    from dataclasses import replace
    from app.services import ilo_firmware_health

    monkeypatch.setattr(
        ilo_firmware_health,
        "settings",
        replace(ilo_firmware_health.settings, provider_mode="local-lab-readwrite"),
    )
    probe["thermal"] = []
    probe["power"] = []
    probe["managers"][0]["Status"]["Health"] = "Warning"
    result = assess_ilo_firmware_health(probe)
    assert result["blockers"] == []
    assert any("temperature inventory" in w["title"] for w in result["warnings"])
    assert any("own health" in w["title"] for w in result["warnings"])
    probe["storage"]["physical_drives"][0]["DiskDriveStatusReasons"] = ["EraseInProgress"]
    assert assess_ilo_firmware_health(probe)["blockers"]
    probe["managers"] = []
    assert any("Exactly one iLO" in b for b in assess_ilo_firmware_health(probe)["blockers"])
