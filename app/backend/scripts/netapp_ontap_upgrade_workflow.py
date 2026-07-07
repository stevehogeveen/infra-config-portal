from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LAB_ENV = REPO_ROOT / ".env.local.real-lab"

from app.services.env_utils import load_real_lab_env  # noqa: E402

load_real_lab_env(REPO_ROOT)

from app.services.netapp_upgrade_center import (  # noqa: E402
    apply_netapp_upgrade,
    build_netapp_upgrade_inventory,
    build_netapp_upgrade_plan,
    validate_netapp_upgrade,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run guarded NetApp ONTAP upgrade workflows.")
    parser.add_argument("action", choices=("inventory", "plan", "validate", "apply"))
    args = parser.parse_args()

    if args.action == "inventory":
        result = build_netapp_upgrade_inventory()
    elif args.action == "plan":
        result = build_netapp_upgrade_plan()
    elif args.action == "validate":
        result = validate_netapp_upgrade()
    else:
        result = apply_netapp_upgrade()

    print(json.dumps(_summary(result), indent=2))
    return 0


def _summary(result: dict) -> dict:
    return {
        "provider_id": result.get("provider_id"),
        "action": result.get("action"),
        "checked_at": result.get("checked_at"),
        "status": result.get("status"),
        "current_version": result.get("current_ontap_version") or result.get("current_version"),
        "target_version": result.get("target_version"),
        "button_state": result.get("button_state"),
        "apply_enabled": result.get("apply_enabled"),
        "validation_passed": result.get("validation_passed"),
        "blockers": result.get("blockers") or [],
        "warnings": result.get("warnings") or [],
        "artifacts": result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {},
        "upgrade_writes_attempted": bool(result.get("upgrade_writes_attempted")),
        "secrets_redacted": True,
    }


if __name__ == "__main__":
    raise SystemExit(main())
