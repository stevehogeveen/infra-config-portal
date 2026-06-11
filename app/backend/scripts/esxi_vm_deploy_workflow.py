from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.esxi_vm_deploy import (  # noqa: E402
    apply_esxi_vm_deploy,
    build_esxi_vm_deploy_preview,
    validate_esxi_vm_deploy,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate guarded direct ESXi OVF deployment reports.")
    parser.add_argument("action", choices=("preview", "apply", "validate"))
    args = parser.parse_args()

    if args.action == "preview":
        result = build_esxi_vm_deploy_preview()
    elif args.action == "apply":
        result = apply_esxi_vm_deploy()
    else:
        result = validate_esxi_vm_deploy()

    print(
        json.dumps(
            {
                "provider_id": result.get("provider_id"),
                "action": result.get("action"),
                "checked_at": result.get("checked_at"),
                "status": result.get("status"),
                "apply_enabled": result.get("apply_enabled"),
                "vm_name": (result.get("deployment_plan") or {}).get("vm_name"),
                "datastore": (result.get("deployment_plan") or {}).get("datastore"),
                "target_datastore_visible": (result.get("datastore_check") or {}).get("exists"),
                "blockers": result.get("blockers", []),
                "warnings": result.get("warnings", []),
                "artifacts": result.get("artifacts", {}),
                "no_write_actions_attempted": result.get("status") == "blocked" or args.action != "apply",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
