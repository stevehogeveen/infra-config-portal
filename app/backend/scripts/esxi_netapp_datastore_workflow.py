from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.esxi_netapp_datastore import (  # noqa: E402
    apply_esxi_netapp_datastore,
    build_esxi_netapp_datastore_preview,
    validate_esxi_netapp_datastore,
)


def _load_local_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env.local.real-lab"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate guarded ESXi NetApp NFS datastore reports.")
    parser.add_argument("action", choices=("preview", "apply", "validate"))
    args = parser.parse_args()
    _load_local_env()

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
