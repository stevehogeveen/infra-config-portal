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

from app.services.esxi_management_recovery import (  # noqa: E402
    recover_esxi_management,
    validate_esxi_post_recovery,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ESXi management recovery reports.")
    parser.add_argument("action", choices=("recover", "validate"))
    args = parser.parse_args()

    result = recover_esxi_management() if args.action == "recover" else validate_esxi_post_recovery()
    print(
        json.dumps(
            {
                "provider_id": result.get("provider_id"),
                "action": result.get("action"),
                "checked_at": result.get("checked_at"),
                "status": result.get("status"),
                "apply_enabled": result.get("apply_enabled"),
                "current_state": result.get("current_state") or result.get("checks"),
                "target_state": result.get("target_state"),
                "blockers": result.get("blockers", []),
                "warnings": result.get("warnings", []),
                "artifacts": result.get("artifacts", {}),
                "no_write_actions_attempted": not bool((result.get("apply") or {}).get("attempted")),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
