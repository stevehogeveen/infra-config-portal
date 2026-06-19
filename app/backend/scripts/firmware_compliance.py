from __future__ import annotations

import argparse
import json

from app.services.firmware_compliance import (
    get_firmware_inventory,
    write_firmware_inventory_report,
    write_firmware_reports,
    write_waiver_report,
)
from app.providers.cisco_console import CiscoConsoleAdapter


def main() -> int:
    parser = argparse.ArgumentParser(description="Real-lab firmware inventory and compliance gate")
    parser.add_argument("mode", choices=("inventory", "cisco-inventory", "compliance", "waiver-check"))
    parser.add_argument("--scope", choices=("hpe", "cisco", "netapp", "full"), default="full")
    args = parser.parse_args()

    if args.mode == "inventory":
        result = get_firmware_inventory(refresh_live=True, refresh_scope=args.scope)
        write_firmware_inventory_report(result)
        print(json.dumps(_inventory_summary(result), indent=2))
        return 0
    if args.mode == "cisco-inventory":
        result = CiscoConsoleAdapter(provider_mode="local-lab-readwrite").firmware_inventory()
        print(json.dumps(_cisco_inventory_summary(result), indent=2))
        return 0 if result.get("status") == "ok" else 1
    if args.mode == "waiver-check":
        result = write_waiver_report()
        print(json.dumps(_waiver_summary(result), indent=2))
        return 0 if result.get("waiver", {}).get("active") or not result.get("waiver", {}).get("configured") else 1

    result = write_firmware_reports(refresh_live=True, scope=args.scope)
    print(json.dumps(_compliance_summary(result), indent=2))
    return 0 if result.get("status") in {"passed", "warning", "waived"} else 1


def _inventory_summary(result: dict) -> dict:
    ilo = ((result.get("live_inventory") or {}).get("ilo") or {})
    return {
        "checked_at": result.get("checked_at"),
        "provider_mode": result.get("provider_mode"),
        "source_type": result.get("source_type"),
        "freshness": result.get("freshness"),
        "ilo_status": ilo.get("status"),
        "ilo_firmware": ilo.get("ilo_firmware"),
        "bios_version": ilo.get("bios_version"),
        "smart_array_firmware": ilo.get("smart_array_firmware"),
        "controller_count": len(ilo.get("controllers") or []),
        "warnings": result.get("warnings") or [],
        "blockers": result.get("blockers") or [],
        "media_candidate_count": (result.get("media_inventory") or {}).get("candidate_count"),
    }


def _waiver_summary(result: dict) -> dict:
    waiver = result.get("waiver") or {}
    return {
        "checked_at": result.get("checked_at"),
        "configured": waiver.get("configured"),
        "active": waiver.get("active"),
        "errors": waiver.get("errors") or [],
        "report": waiver.get("report"),
    }


def _compliance_summary(result: dict) -> dict:
    return {
        "checked_at": result.get("checked_at"),
        "status": result.get("status"),
        "blockers": result.get("blockers") or [],
        "warnings": result.get("warnings") or [],
        "reports": result.get("reports") or {},
    }


def _cisco_inventory_summary(result: dict) -> dict:
    return {
        "status": result.get("status"),
        "source": result.get("source"),
        "prompt_state": result.get("prompt_state"),
        "ios_xe_version": result.get("ios_xe_version"),
        "blockers": result.get("blockers") or [],
        "warnings": result.get("warnings") or [],
    }


if __name__ == "__main__":
    raise SystemExit(main())
