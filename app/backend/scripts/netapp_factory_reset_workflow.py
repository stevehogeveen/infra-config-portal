from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REAL_LAB_ENV = Path(__file__).resolve().parents[3] / ".env.local.real-lab"
from app.services.env_utils import load_env_file  # noqa: E402

load_env_file(REAL_LAB_ENV)

from app.services.netapp_factory_reset import (  # noqa: E402
    apply_netapp_factory_reset,
    build_netapp_factory_reset_preview,
    validate_netapp_factory_reset,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run guarded NetApp factory-reset workflows.")
    parser.add_argument("action", choices=("preview", "apply", "validate"))
    args = parser.parse_args()
    if args.action == "preview":
        result = build_netapp_factory_reset_preview()
    elif args.action == "apply":
        result = apply_netapp_factory_reset()
    else:
        result = validate_netapp_factory_reset()
    print(
        json.dumps(
            {
                "checked_at": result.get("checked_at"),
                "status": result.get("status"),
                "apply_enabled": result.get("apply_enabled"),
                "blockers": result.get("blockers") or [],
                "report": (result.get("artifacts") or {}).get("report"),
                "destructive_commands_attempted": bool((result.get("apply") or {}).get("destructive_commands_attempted")),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
