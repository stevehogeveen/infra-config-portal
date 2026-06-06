from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.providers.ilo_redfish import IloRedfishAdapter
from app.providers.redaction import redact_sensitive
from app.core.config import settings

REPO_ROOT = Path(__file__).resolve().parents[3]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
ILO_REPORT = CODEX_RUN_DIR / "ilo-real-run-report.md"
RAID_REPORT = CODEX_RUN_DIR / "hpe-raid-plan-report.md"


def main() -> int:
    result = IloRedfishAdapter(provider_mode="local-lab-readwrite").probe()
    inventory = _inventory_summary(result)
    storage = result.get("storage") if isinstance(result.get("storage"), dict) else {}
    plan = _raid_plan(inventory, storage)
    sanitized = redact_sensitive(
        {
            "checked_at": datetime.now(UTC).isoformat(),
            "provider_mode": "local-lab-readwrite",
            "inventory": inventory,
            "storage": storage,
            "raid_plan": plan,
            "not_attempted": _not_attempted(),
        },
        [settings.ilo_test_host, settings.ilo_test_username, settings.ilo_test_password],
    )
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    ILO_REPORT.write_text(_ilo_report(result, sanitized), encoding="utf-8")
    RAID_REPORT.write_text(_raid_report(sanitized), encoding="utf-8")
    print(json.dumps(_console_summary(sanitized), indent=2))
    print(f"ilo_report={ILO_REPORT.relative_to(REPO_ROOT)}")
    print(f"raid_report={RAID_REPORT.relative_to(REPO_ROOT)}")
    return 0


def _console_summary(report: dict[str, Any]) -> dict[str, Any]:
    inventory = report["inventory"]
    storage = report["storage"]
    plan = report["raid_plan"]
    return {
        "checked_at": report["checked_at"],
        "provider_mode": report["provider_mode"],
        "server_model": inventory.get("server_model"),
        "ilo_model": inventory.get("ilo_model"),
        "ilo_firmware": inventory.get("ilo_firmware"),
        "bios_version": inventory.get("bios_version"),
        "power_state": inventory.get("power_state"),
        "health": inventory.get("health"),
        "nic_count": inventory.get("network_adapter_count"),
        "storage_inventory_available": plan.get("storage_inventory_available"),
        "controller_count": len(storage.get("controllers") or []),
        "physical_drive_count": len(storage.get("physical_drives") or []),
        "logical_drive_count": len(storage.get("logical_drives") or []),
        "raid_recommendation": (plan.get("planned_layout") or {}).get("recommendation"),
        "apply_allowed": plan.get("apply_allowed"),
        "not_attempted": plan.get("not_attempted", []),
    }


def _inventory_summary(result: dict[str, Any]) -> dict[str, Any]:
    managers = result.get("managers") if isinstance(result.get("managers"), list) else []
    systems = result.get("systems") if isinstance(result.get("systems"), list) else []
    firmware = result.get("firmware") if isinstance(result.get("firmware"), list) else []
    system = systems[0] if systems else {}
    manager = managers[0] if managers else {}
    return {
        "probe_status": result.get("status"),
        "message": result.get("message"),
        "redfish_service": result.get("service_root", {}),
        "server_model": _first_present(system, "Model", "ProductName", "Name"),
        "serial_number_present": bool(
            system.get("serial_number_present") or system.get("SerialNumber")
        ),
        "product_info_present": bool(system.get("ProductName") or system.get("Model")),
        "ilo_model": _first_present(manager, "Model", "Name"),
        "ilo_firmware": manager.get("FirmwareVersion"),
        "bios_version": _bios_version(firmware, system),
        "power_state": system.get("PowerState"),
        "health": _status_health(system.get("Status")),
        "network_adapter_count": len(result.get("network_adapters") or []),
        "network_adapters": result.get("network_adapters") or [],
        "requests": result.get("requests") or [],
        "blockers": result.get("blockers") or [],
        "warnings": result.get("warnings") or [],
    }


def _raid_plan(inventory: dict[str, Any], storage: dict[str, Any]) -> dict[str, Any]:
    drives = storage.get("physical_drives") if isinstance(storage.get("physical_drives"), list) else []
    logical = storage.get("logical_drives") if isinstance(storage.get("logical_drives"), list) else []
    controllers = storage.get("controllers") if isinstance(storage.get("controllers"), list) else []
    boot_logical = _find_logical_drive(logical, purpose="boot")
    datastore_logical = _find_logical_drive(logical, purpose="datastore")
    recommended = "manual-review"
    rationale = "Drive inventory was not sufficient to choose a concrete ESXi layout."
    if boot_logical and datastore_logical:
        recommended = "preserve existing OS and data logical drives for ESXi preview"
        rationale = (
            "The current layout already has a RAID1 OS logical drive and a separate "
            "data logical drive; no RAID change is proposed."
        )
    elif len(drives) >= 6:
        recommended = "RAID1 OS volume plus RAID5 or RAID10 datastore volume"
        rationale = "Enough drives were discovered to separate ESXi boot from datastore capacity."
    elif len(drives) >= 2:
        recommended = "RAID1 ESXi boot/install volume"
        rationale = "At least two drives were discovered; RAID1 is the conservative ESXi install preview."

    return {
        "status": "preview_only",
        "target_server_model": inventory.get("server_model"),
        "storage_inventory_available": bool(controllers or drives or logical),
        "current_layout": {
            "controllers": controllers,
            "physical_drives": drives,
            "logical_drives": logical,
        },
        "planned_layout": {
            "recommendation": recommended,
            "rationale": rationale,
            "boot_volume": {
                "purpose": "ESXi install",
                "raid": (boot_logical or {}).get("RAIDType")
                or ("RAID1" if len(drives) >= 2 else "manual-review"),
                "candidate_drive_count": 0 if boot_logical else min(len(drives), 2),
                "source": "existing-logical-drive" if boot_logical else "candidate-physical-drives",
                "current_logical_drive": _planned_logical_summary(boot_logical),
            },
            "datastore_volume": {
                "purpose": "VM datastore",
                "raid": (datastore_logical or {}).get("RAIDType")
                or ("RAID5/RAID10 review" if len(drives) >= 6 else "not-planned"),
                "candidate_drive_count": 0 if datastore_logical else max(len(drives) - 2, 0),
                "source": "existing-logical-drive" if datastore_logical else "candidate-physical-drives",
                "current_logical_drive": _planned_logical_summary(datastore_logical),
            },
        },
        "apply_allowed": False,
        "not_attempted": _not_attempted(),
    }


def _find_logical_drive(
    logical_drives: list[dict[str, Any]],
    *,
    purpose: str,
) -> dict[str, Any] | None:
    for drive in logical_drives:
        name = str(drive.get("LogicalDriveName") or drive.get("Name") or "").lower()
        raid = str(drive.get("RAIDType") or drive.get("Raid") or "").upper()
        if purpose == "boot" and ("os" in name or "boot" in name or raid == "RAID1"):
            return drive
        if purpose == "datastore" and drive.get("LogicalDriveNumber") != 1:
            return drive
    return None


def _planned_logical_summary(drive: dict[str, Any] | None) -> dict[str, Any] | None:
    if not drive:
        return None
    return {
        "name": drive.get("LogicalDriveName") or drive.get("Name"),
        "raid": drive.get("RAIDType"),
        "capacity_mib": drive.get("CapacityMiB"),
        "health": _status_health(drive.get("Status")),
    }


def _ilo_report(raw_result: dict[str, Any], report: dict[str, Any]) -> str:
    inventory = report["inventory"]
    storage = report["storage"]
    lines = [
        "# iLO Real Run Report",
        "",
        f"Date: {report['checked_at']}",
        "",
        "## Scope",
        "",
        "- Mode: `PROVIDER_MODE=local-lab-readwrite`",
        "- Env file: repo-root `.env.local.real-lab`",
        "- Target access: real iLO Redfish GET-only inventory",
        "- Mock results: not used",
        "",
        "## Inventory",
        "",
        f"- Probe status: {inventory.get('probe_status')}",
        f"- Redfish message: {inventory.get('message')}",
        f"- Server model: {inventory.get('server_model') or 'unknown'}",
        f"- Product info present: {inventory.get('product_info_present')}",
        f"- Serial present: {inventory.get('serial_number_present')}",
        f"- iLO model: {inventory.get('ilo_model') or 'unknown'}",
        f"- iLO firmware: {inventory.get('ilo_firmware') or 'unknown'}",
        f"- BIOS version: {inventory.get('bios_version') or 'unknown'}",
        f"- Power state: {inventory.get('power_state') or 'unknown'}",
        f"- Health: {inventory.get('health') or 'unknown'}",
        f"- NIC inventory count: {inventory.get('network_adapter_count', 0)}",
        f"- Storage discovery status: {storage.get('status', 'unknown')}",
        f"- Storage controllers: {len(storage.get('controllers') or [])}",
        f"- Physical drives: {len(storage.get('physical_drives') or [])}",
        f"- Logical drives: {len(storage.get('logical_drives') or [])}",
        "",
        "## Safety",
        "",
    ]
    for item in raw_result.get("not_attempted", _not_attempted()):
        lines.append(f"- not attempted: {item}")
    lines.append("")
    return "\n".join(lines)


def _raid_report(report: dict[str, Any]) -> str:
    inventory = report["inventory"]
    storage = report["storage"]
    plan = report["raid_plan"]
    lines = [
        "# HPE RAID Plan Report",
        "",
        f"Date: {report['checked_at']}",
        "",
        "## Result",
        "",
        f"- Server model: {inventory.get('server_model') or 'unknown'}",
        f"- iLO model: {inventory.get('ilo_model') or 'unknown'}",
        f"- Storage/RAID inventory available through Redfish: {plan['storage_inventory_available']}",
        f"- Controller count: {len(storage.get('controllers') or [])}",
        f"- Physical drive count: {len(storage.get('physical_drives') or [])}",
        f"- Logical drive count: {len(storage.get('logical_drives') or [])}",
        "",
        "## Current Layout",
        "",
    ]
    lines.extend(_item_lines("Controller", storage.get("controllers") or []))
    lines.extend(_item_lines("Physical drive", storage.get("physical_drives") or []))
    lines.extend(_item_lines("Logical drive", storage.get("logical_drives") or []))
    lines.extend(
        [
            "",
            "## Planned Layout",
            "",
            f"- Status: {plan['status']}",
            f"- Recommendation: {plan['planned_layout']['recommendation']}",
            f"- Rationale: {plan['planned_layout']['rationale']}",
            "- Boot volume: "
            + _planned_volume_line(plan["planned_layout"]["boot_volume"]),
            "- Datastore volume: "
            + _planned_volume_line(plan["planned_layout"]["datastore_volume"]),
            f"- Apply allowed: {plan['apply_allowed']}",
            "",
            "## Not Attempted",
            "",
        ]
    )
    for item in plan["not_attempted"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def _item_lines(label: str, items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return [f"- {label}: none discovered"]
    lines = []
    for index, item in enumerate(items, start=1):
        name = item.get("LogicalDriveName") or item.get("Name") or item.get("Id") or f"{label} {index}"
        details = _item_detail_text(label, item)
        lines.append(f"- {label} {index}: {name}{details}")
    return lines


def _item_detail_text(label: str, item: dict[str, Any]) -> str:
    health = _status_health(item.get("Status")) or "unknown"
    if label == "Controller":
        return (
            f"; model={item.get('Model', 'unknown')}"
            f"; location={item.get('Location', 'unknown')}"
            f"; firmware={_firmware_version(item.get('FirmwareVersion'))}"
            f"; mode={item.get('CurrentOperatingMode', 'unknown')}"
            f"; cache_mib={item.get('CacheMemorySizeMiB', 'unknown')}"
            f"; health={health}"
        )
    if label == "Physical drive":
        return (
            f"; bay/location={item.get('Bay') or item.get('Location') or 'unknown'}"
            f"; capacity_gb={item.get('CapacityGB', 'unknown')}"
            f"; media={item.get('MediaType', 'unknown')}"
            f"; interface={item.get('InterfaceType') or item.get('Protocol') or 'unknown'}"
            f"; health={health}"
            f"; serial_present={item.get('serial_number_present', False)}"
        )
    if label == "Logical drive":
        return (
            f"; raid={item.get('RAIDType') or item.get('Raid') or 'unknown'}"
            f"; capacity_mib={item.get('CapacityMiB', 'unknown')}"
            f"; media={item.get('MediaType', 'unknown')}"
            f"; interface={item.get('InterfaceType', 'unknown')}"
            f"; logical_number={item.get('LogicalDriveNumber', 'unknown')}"
            f"; health={health}"
        )
    return f"; health={health}"


def _planned_volume_line(volume: dict[str, Any]) -> str:
    current = volume.get("current_logical_drive") if isinstance(volume, dict) else None
    if isinstance(current, dict):
        return (
            f"{volume.get('purpose', 'unknown')} uses existing logical drive "
            f"{current.get('name', 'unknown')} "
            f"({current.get('raid', 'unknown')}, "
            f"capacity_mib={current.get('capacity_mib', 'unknown')}, "
            f"health={current.get('health', 'unknown')})"
        )
    return (
        f"{volume.get('purpose', 'unknown')} planned as {volume.get('raid', 'unknown')} "
        f"from {volume.get('candidate_drive_count', 0)} candidate physical drives"
    )


def _firmware_version(value: Any) -> str:
    if isinstance(value, dict):
        current = value.get("Current")
        if isinstance(current, dict) and current.get("VersionString"):
            return str(current["VersionString"])
    if value:
        return str(value)
    return "unknown"


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value:
            return value
    return None


def _bios_version(firmware: list[dict[str, Any]], system: dict[str, Any]) -> str | None:
    for item in firmware:
        name = str(item.get("Name") or item.get("Id") or "").lower()
        if "bios" in name or "system rom" in name:
            version = item.get("FirmwareVersion")
            if version:
                return str(version)
    bios = system.get("BiosVersion") or system.get("BIOSVersion")
    return str(bios) if bios else None


def _status_health(status: Any) -> str | None:
    if isinstance(status, dict):
        health = status.get("Health") or status.get("State")
        return str(health) if health else None
    return None


def _not_attempted() -> list[str]:
    return [
        "RAID create/delete/update",
        "drive erase",
        "logical drive delete",
        "controller configuration write",
        "device POST/PATCH/PUT/DELETE",
        "power action",
        "firmware update",
    ]


if __name__ == "__main__":
    raise SystemExit(main())
