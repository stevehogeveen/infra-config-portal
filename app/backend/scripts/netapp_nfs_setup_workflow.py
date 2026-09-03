from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LAB_ENV = REPO_ROOT / ".env.local.real-lab"

from app.services.env_utils import load_real_lab_env  # noqa: E402

load_real_lab_env(REPO_ROOT)

from app.services.netapp_nfs_setup import (  # noqa: E402
    apply_netapp_nfs_setup,
    build_netapp_nfs_setup_preview,
    validate_netapp_nfs_setup,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run guarded NetApp NFS setup workflows.")
    parser.add_argument("action", choices=("preview", "apply", "validate"))
    args = parser.parse_args()

    if args.action == "preview":
        result = build_netapp_nfs_setup_preview()
    elif args.action == "apply":
        result = apply_netapp_nfs_setup()
    else:
        result = validate_netapp_nfs_setup()

    print(json.dumps(_summary(result), indent=2))
    return 0


def _summary(result: dict) -> dict:
    return {
        "provider_id": result.get("provider_id"),
        "action": result.get("action"),
        "checked_at": result.get("checked_at"),
        "status": result.get("status"),
        "configured_state": result.get("configured_state"),
        "apply_enabled": result.get("apply_enabled"),
        "api_access_present": result.get("api_access_present"),
        "blockers": result.get("blockers") or [],
        "warnings": result.get("warnings") or [],
        "artifacts": result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {},
        "no_write_actions_attempted": not bool(((result.get("apply") or {}).get("rest_result") or {}).get("ontap_writes_attempted")),
    }


if __name__ == "__main__":
    raise SystemExit(main())
