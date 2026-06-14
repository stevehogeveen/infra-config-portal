from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LAB_ENV = REPO_ROOT / ".env.local.real-lab"

if REAL_LAB_ENV.exists():
    for key, value in dotenv_values(REAL_LAB_ENV).items():
        if value is None or key in os.environ:
            continue
        os.environ[key] = value

from app.services.vcenter_netapp_readiness import (  # noqa: E402
    get_vcenter_attach_esxi_apply,
    get_vcenter_attach_esxi_preview,
    get_vcenter_install_apply,
    get_vcenter_install_plan,
    get_vcenter_install_preview,
    get_vcenter_install_readiness,
    get_vcenter_netapp_datastore_plan,
    get_vcenter_netapp_readiness,
    validate_vcenter_post_attach,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate vCenter readiness and datastore plan reports.")
    parser.add_argument(
        "action",
        choices=(
            "readiness",
            "datastore-plan",
            "install-readiness",
            "install-plan",
            "install-preview",
            "install-apply",
            "attach-esxi-preview",
            "attach-esxi-apply",
            "post-attach-validation",
        ),
    )
    args = parser.parse_args()

    if args.action == "datastore-plan":
        result = get_vcenter_netapp_datastore_plan(write_report=True)
    elif args.action == "install-readiness":
        result = get_vcenter_install_readiness(check_ports=True, write_report=True)
    elif args.action == "install-plan":
        result = get_vcenter_install_plan(write_report=True)
    elif args.action == "install-preview":
        result = get_vcenter_install_preview(write_report=True)
    elif args.action == "install-apply":
        result = get_vcenter_install_apply(write_report=True)
    elif args.action == "attach-esxi-preview":
        result = get_vcenter_attach_esxi_preview(write_report=True)
    elif args.action == "attach-esxi-apply":
        result = get_vcenter_attach_esxi_apply(write_report=True)
    elif args.action == "post-attach-validation":
        result = validate_vcenter_post_attach(write_report=True)
    else:
        result = get_vcenter_netapp_readiness(check_ports=True, write_report=True)

    print(json.dumps(_summary(result), indent=2))
    if args.action in {"install-apply", "attach-esxi-apply"} and result.get("status") not in {"completed", "ready"}:
        return 1
    if args.action == "post-attach-validation" and result.get("status") != "ready":
        return 1
    return 0


def _summary(result: dict) -> dict:
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    write_attempted = bool((result.get("apply") or {}).get("vcsa_deploy_attempted")) or any(
        bool(operation.get("attempted")) for operation in result.get("operations") or [] if isinstance(operation, dict)
    )
    return {
        "provider_id": result.get("provider_id"),
        "action": result.get("action"),
        "checked_at": result.get("checked_at"),
        "status": result.get("status"),
        "netapp_stage": result.get("netapp_stage"),
        "blockers": result.get("blockers") or [],
        "warnings": result.get("warnings") or [],
        "artifacts": artifacts,
        "apply_enabled": result.get("apply_enabled"),
        "no_write_actions_attempted": not write_attempted,
    }


if __name__ == "__main__":
    raise SystemExit(main())
