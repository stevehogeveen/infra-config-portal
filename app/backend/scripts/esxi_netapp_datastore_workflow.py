from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REAL_LAB_ENV = ROOT / ".env.local.real-lab"
from app.services.env_utils import load_env_file  # noqa: E402

load_env_file(REAL_LAB_ENV)

from app.services.esxi_netapp_datastore import (  # noqa: E402
    apply_esxi_netapp_datastore,
    build_esxi_netapp_datastore_preview,
    validate_esxi_netapp_datastore,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate guarded ESXi NetApp NFS datastore reports.")
    parser.add_argument("action", choices=("preview", "apply", "validate"))
    args = parser.parse_args()

    if args.action == "preview":
        result = build_esxi_netapp_datastore_preview()
    elif args.action == "apply":
        result = apply_esxi_netapp_datastore()
    else:
        result = validate_esxi_netapp_datastore()

    print(
        json.dumps(
            {
                "provider_id": result.get("provider_id"),
                "action": result.get("action"),
                "checked_at": result.get("checked_at"),
                "status": result.get("status"),
                "apply_enabled": result.get("apply_enabled"),
                "datastore": (result.get("target_state") or {}).get("datastore_name"),
                "remote_host": (result.get("target_state") or {}).get("remote_host"),
                "current_exists": (result.get("current_state") or {}).get("exists"),
                "current_accessible": (result.get("current_state") or {}).get("accessible"),
                "blockers": result.get("blockers", []),
                "warnings": result.get("warnings", []),
                "artifacts": result.get("artifacts", {}),
                "no_write_actions_attempted": not bool((result.get("apply") or {}).get("govc_datastore_create_attempted")),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
