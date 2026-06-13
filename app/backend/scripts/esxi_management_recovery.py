from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.esxi_management_recovery import (  # noqa: E402
    recover_esxi_management,
    validate_esxi_post_recovery,
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
    parser = argparse.ArgumentParser(description="Generate ESXi management recovery reports.")
    parser.add_argument("action", choices=("recover", "validate"))
    args = parser.parse_args()
    _load_local_env()

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
