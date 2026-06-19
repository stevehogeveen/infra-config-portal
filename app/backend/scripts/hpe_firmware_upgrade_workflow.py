from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LAB_ENV = REPO_ROOT / ".env.local.real-lab"

if REAL_LAB_ENV.exists():
    for key, value in dotenv_values(REAL_LAB_ENV).items():
        if value is None or key in os.environ:
            continue
        os.environ[key] = value

from app.services.hpe_firmware_upgrade import (  # noqa: E402
    apply_hpe_firmware_upgrade,
    build_hpe_firmware_upgrade_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run guarded HPE firmware upgrade workflows.")
    parser.add_argument("action", choices=("plan", "apply"))
    parser.add_argument(
        "--component-id",
        default=os.environ.get("HPE_FIRMWARE_COMPONENT_ID") or None,
        help="Optional HPE firmware component id to plan/apply, such as hpe_ilo_firmware, hpe_bios_version, or hpe_smart_array_firmware.",
    )
    args = parser.parse_args()

    if args.action == "plan":
        result = build_hpe_firmware_upgrade_plan(component_id=args.component_id)
    else:
        result = apply_hpe_firmware_upgrade(component_id=args.component_id)

    print(json.dumps(_summary(result), indent=2))
    return 0


def _summary(result: dict) -> dict:
    return {
        "provider_id": result.get("provider_id"),
        "action": result.get("action"),
        "checked_at": result.get("checked_at"),
        "status": result.get("status"),
        "selected_component_id": result.get("selected_component_id"),
        "selected_component_label": result.get("selected_component_label"),
        "apply_enabled": result.get("apply_enabled"),
        "ordered_step_count": len(result.get("ordered_steps") or []),
        "upgrade_step_count": len(result.get("upgrade_steps") or []),
        "blockers": result.get("blockers") or [],
        "warnings": result.get("warnings") or [],
        "artifacts": result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {},
        "upgrade_writes_attempted": bool(result.get("upgrade_writes_attempted")),
        "secrets_redacted": True,
    }


if __name__ == "__main__":
    raise SystemExit(main())
