from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REAL_LAB_ENV = Path(__file__).resolve().parents[3] / ".env.local.real-lab"
from app.services.env_utils import load_env_file  # noqa: E402

load_env_file(REAL_LAB_ENV)

from app.services.netapp_address_plan import (  # noqa: E402
    apply_netapp_address_remediation,
    build_netapp_address_remediation_plan,
    build_netapp_address_remediation_preview,
    diagnose_netapp_ha_node_warning,
    validate_netapp_address_remediation,
)


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if action == "plan":
        result = build_netapp_address_remediation_plan()
    elif action == "preview":
        result = build_netapp_address_remediation_preview()
    elif action == "apply":
        result = apply_netapp_address_remediation()
    elif action == "validate":
        result = validate_netapp_address_remediation()
    elif action == "ha-diagnose":
        result = diagnose_netapp_ha_node_warning()
    else:
        print(f"unsupported action: {action}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "checked_at": result["checked_at"],
                "status": result["status"],
                "apply_enabled": result["apply_enabled"],
                "blockers": result["blockers"],
                "report": result["artifacts"]["report"],
            },
            indent=2,
        )
    )
    return 0 if result["status"] in {"ready", "blocked", "preview_only", "applied", "failed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
