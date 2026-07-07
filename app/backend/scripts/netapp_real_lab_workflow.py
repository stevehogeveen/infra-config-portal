from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LAB_ENV = REPO_ROOT / ".env.local.real-lab"

from app.services.env_utils import load_real_lab_env  # noqa: E402

load_real_lab_env(REPO_ROOT)

from app.services.netapp_real_lab import (  # noqa: E402
    get_netapp_nfs_vcenter_readiness,
    run_netapp_console_login_state,
    run_netapp_live_state,
    run_netapp_setup_validation,
    run_netapp_console_discovery,
    run_netapp_console_read_state,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run NetApp real-lab read-only workflows.")
    parser.add_argument(
        "action",
        choices=(
            "console-autodiscovery",
            "console-discovery",
            "console-read-state",
            "console-login-state",
            "live-state",
            "validate-setup",
            "nfs-vcenter-readiness",
        ),
    )
    args = parser.parse_args()

    if args.action in {"console-autodiscovery", "console-discovery"}:
        result = run_netapp_console_discovery()
    elif args.action == "console-read-state":
        result = run_netapp_console_read_state()
    elif args.action == "console-login-state":
        result = run_netapp_console_login_state()
    elif args.action == "live-state":
        result = run_netapp_live_state()
    elif args.action == "validate-setup":
        result = run_netapp_setup_validation()
    else:
        result = get_netapp_nfs_vcenter_readiness(write_report=True)

    print(json.dumps(_summary(result), indent=2))
    return 0


def _summary(result: dict) -> dict:
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    return {
        "provider_id": result.get("provider_id"),
        "action": result.get("action"),
        "checked_at": result.get("checked_at"),
        "status": result.get("status"),
        "message": result.get("message"),
        "selected_port": result.get("selected_port"),
        "selected_baud": result.get("selected_baud"),
        "selected_prompt_state": result.get("selected_prompt_state") or result.get("prompt_state"),
        "configured": result.get("configured"),
        "configured_state": result.get("configured_state"),
        "manual_env_flag_required": result.get("manual_env_flag_required"),
        "candidate_count": result.get("candidate_count"),
        "single_management_port_mode": result.get("single_management_port_mode"),
        "identified_state": result.get("identified_state"),
        "login_attempted": result.get("login_attempted"),
        "read_only_commands_attempted": result.get("read_only_commands_attempted"),
        "blockers": result.get("blockers") or [],
        "warnings": result.get("warnings") or [],
        "artifacts": artifacts,
        "no_write_actions_attempted": True,
    }


if __name__ == "__main__":
    raise SystemExit(main())
