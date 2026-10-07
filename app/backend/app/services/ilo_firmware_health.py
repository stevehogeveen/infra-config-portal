"""Component-scoped iLO update checks, not clearance for storage operations."""

import hashlib
import json

from app.core.config import settings
from app.services.hardware_health import health_issues, reported_reasons
from app.services.blocker_guidance import with_blocker_details


# Self-test results that are not failures. iLO 5 reports version notes as Informational.
_SELF_TEST_OK = {"OK", "Informational", "NotTested"}


def _manager_blockers(managers):
    """Say what the iLO itself reported. Older iLO 5 firmware (e.g. 1.37) reports only
    Status.State on the manager, with no Health; its own self-test results then decide."""
    if len(managers) != 1:
        return [f"Exactly one iLO must answer; this read found {len(managers)}."]
    manager = managers[0]
    status = manager.get("Status") or {}
    health, state = status.get("Health"), status.get("State")
    tests = manager.get("ilo_self_tests")
    blockers = []
    if state not in (None, "Enabled"):
        blockers.append(f"The iLO reports its state as {state}, not Enabled.")
    if health not in (None, "OK"):
        state_note = f" (State {state})" if state is not None else ""
        blockers.append(f"The iLO reports its own health as {health}{state_note}.")
    for test in [t for t in tests or [] if t.get("status") not in _SELF_TEST_OK]:
        note = f": {test['notes']}" if test.get("notes") else ""
        blockers.append(
            f"iLO self-test {test.get('name') or 'unnamed'} reports "
            f"{test.get('status') or 'no result'}{note}."
        )
    if health is None and not tests:
        blockers.append(
            "The iLO did not report its health or any self-test results, so its health is unknown."
        )
    return blockers


def assess_ilo_firmware_health(probe):
    blockers = []
    warnings = [
        {
            "group": item["group"],
            "health": item["health"],
            "title": item["title"],
            "details": " ".join(item["details"]),
        }
        for item in health_issues(probe)
    ]
    blockers.extend(_manager_blockers(probe.get("managers") or []))

    supplies = [s for p in probe.get("power") or [] for s in p.get("PowerSupplies") or []]
    powered = []
    for supply in supplies:
        status = supply.get("Status") or {}
        voltage = supply.get("LineInputVoltage")
        if status.get("State") == "Absent":
            continue
        if isinstance(voltage, (float, int)) and not isinstance(voltage, bool) and voltage > 0:
            if status.get("Health") != "OK" or status.get("State") != "Enabled":
                blockers.append("An energized power supply reports a fault or unknown state.")
            else:
                powered.append(str(supply.get("MemberId") or supply.get("Id") or "supply"))
        elif voltage != 0 or status.get("Health") == "Critical":
            blockers.append("A power supply has unknown input power or a critical fault.")
    if not powered:
        blockers.append("At least one enabled healthy power supply with input voltage is required.")
    if len(powered) == 1:
        warnings.append(
            {
                "group": "Power",
                "health": "Warning",
                "title": "One healthy powered supply observed. Keep its power feed connected throughout the update.",
            }
        )

    thermals = probe.get("thermal") or []
    if not thermals or any(t.get("sensor_inventory_complete") is not True for t in thermals):
        blockers.append("Fresh cooling and temperature inventory is required.")
    for thermal in thermals:
        for category in ("Fans", "Temperatures"):
            if not any(
                (s.get("Status") or {}).get("State") != "Absent"
                for s in thermal.get(category) or []
            ):
                blockers.append("Present cooling and temperature sensor evidence is required.")
        sensors = (thermal.get("Fans") or []) + (thermal.get("Temperatures") or [])
        for sensor in sensors:
            status = sensor.get("Status") or {}
            if status.get("State") == "Absent":
                continue
            if status.get("Health") != "OK" or status.get("State") != "Enabled":
                blockers.append("Cooling or temperature sensor reports a fault or unknown state.")
    storage = probe.get("storage") or {}
    active = {"EraseInProgress", "QueuedForErase", "Rebuilding", "Recovering", "Transforming"}
    for resource in (storage.get("physical_drives") or []) + (storage.get("logical_drives") or []):
        if active.intersection(reported_reasons(resource)):
            blockers.append(
                "A storage operation is active; wait for verified completion before resetting iLO."
            )
    if any(
        (s.get("Status") or {}).get("Health") == "Critical"
        for s in (probe.get("systems") or []) + (probe.get("chassis") or [])
    ):
        blockers.append("Critical server or chassis health requires diagnosis before updating iLO.")
    if settings.provider_mode == "local-lab-readwrite":
        conflicts = [
            b for b in blockers if b.startswith(("Exactly one iLO", "A storage operation"))
        ]
        warnings.extend(
            {"group": "Firmware", "health": "Warning", "title": finding}
            for finding in blockers
            if finding not in conflicts
        )
        blockers = conflicts
    # Preserve non-clearance warnings in the immutable review without changing
    # their hardware health or making these devices eligible for RAID operations.
    evidence = {
        "scope": "ilo-only-v1",
        "powered_supplies": sorted(powered),
        "warnings": sorted(warnings, key=lambda w: (w["group"], w["title"], w["health"])),
        "blockers": sorted(set(blockers)),
    }
    evidence["assessment_sha256"] = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return with_blocker_details(evidence)
