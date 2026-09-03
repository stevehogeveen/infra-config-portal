from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LAB_ENV = REPO_ROOT / ".env.local.real-lab"

from app.services.env_utils import load_real_lab_env  # noqa: E402

load_real_lab_env(REPO_ROOT)

from app.services.netapp_setup_intent import (  # noqa: E402
    apply_netapp_setup,
    build_netapp_setup_baseline,
    build_netapp_setup_plan,
    build_netapp_setup_preview,
    run_netapp_post_setup_validation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run guarded NetApp setup workflows.")
    parser.add_argument(
        "action",
        choices=("baseline", "plan", "preview", "apply", "post-setup-validation"),
    )
    args = parser.parse_args()

    if args.action == "baseline":
        result = build_netapp_setup_baseline(run_address_scan=True)
    elif args.action == "plan":
        result = build_netapp_setup_plan(run_address_scan=False)
    elif args.action == "preview":
        result = build_netapp_setup_preview(run_address_scan=True)
    elif args.action == "apply":
        result = apply_netapp_setup()
    else:
        result = run_netapp_post_setup_validation()

    print(json.dumps(_summary(result), indent=2))
    return 0


def _summary(result: dict) -> dict:
    return {
        "provider_id": result.get("provider_id"),
        "action": result.get("action"),
        "checked_at": result.get("checked_at"),
        "status": result.get("status"),
        "detected_state": result.get("detected_state"),
        "apply_enabled": result.get("apply_enabled"),
        "missing_fields": result.get("missing_fields") or [],
        "blockers": result.get("blockers") or [],
        "warnings": result.get("warnings") or [],
        "artifacts": result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {},
        "no_setup_apply_attempted": result.get("action") != "setup-apply"
        or not bool(result.get("apply_enabled")),
        "secrets_redacted": True,
    }


if __name__ == "__main__":
    raise SystemExit(main())
