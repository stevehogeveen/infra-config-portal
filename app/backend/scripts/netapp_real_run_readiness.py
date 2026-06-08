from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LAB_ENV = REPO_ROOT / ".env.local.real-lab"
REPORT_DIR = REPO_ROOT / "artifacts" / "real-lab"

if REAL_LAB_ENV.exists():
    for key, value in dotenv_values(REAL_LAB_ENV).items():
        if value is None or key in os.environ:
            continue
        os.environ[key] = value

# Load local lab env before app imports; settings reads env at import time.
from app.core.config import settings  # noqa: E402
from app.providers.netapp import NetAppOntapAdapter  # noqa: E402
from app.providers.redaction import redact_sensitive  # noqa: E402
from app.services.netapp_artifacts import list_netapp_artifact_placeholders  # noqa: E402
from app.services.netapp_console_readiness import get_netapp_console_readiness  # noqa: E402
from app.services.netapp_readiness_comparison import (  # noqa: E402
    get_netapp_readiness_comparison,
)
from app.services.netapp_upgrade_readiness import get_netapp_upgrade_readiness  # noqa: E402


def main() -> int:
    plan_preview = NetAppOntapAdapter().plan_preview()
    console_readiness = get_netapp_console_readiness()
    readiness_comparison = get_netapp_readiness_comparison()
    upgrade_readiness = get_netapp_upgrade_readiness()
    artifact_placeholders = list_netapp_artifact_placeholders()

    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "provider_id": "netapp-ontap",
        "provider_mode": settings.provider_mode,
        "safe_real_run_scope": "netapp-readiness-only",
        "env_file": {
            "path": ".env.local.real-lab",
            "exists": REAL_LAB_ENV.exists(),
            "mode": _file_mode(REAL_LAB_ENV),
        },
        "safety": {
            "netapp_configured": settings.netapp_configured,
            "local_readonly_ack": settings.lab_readonly_ack == "YES",
            "closed_loop_ack": settings.lab_closed_loop_ack == "YES",
            "destructive_ack": settings.lab_destructive_ack == "REBUILD_LAB",
            "apply_enabled": False,
            "probe_enabled": False,
            "upgrade_enabled": False,
        },
        "planned_targets": plan_preview["planned_targets"],
        "current_discovered_targets": plan_preview["current_discovered_targets"],
        "setup_readiness": plan_preview["setup_readiness"],
        "upgrade_readiness": plan_preview["upgrade_readiness"],
        "console_blockers": console_readiness["blockers"],
        "comparison_counts": {
            "matched": len(readiness_comparison["matched_items"]),
            "unknown": len(readiness_comparison["unknown_items"]),
            "warning": len(readiness_comparison["warning_items"]),
            "blocker": len(readiness_comparison["blocker_items"]),
        },
        "comparison_blockers": readiness_comparison["blockers"],
        "upgrade_blockers": upgrade_readiness["blockers"],
        "artifact_placeholders": artifact_placeholders,
        "operator_steps": _operator_steps(),
        "not_attempted": [
            "ONTAP API discovery",
            "Service Processor probe",
            "serial console open",
            "console command send",
            "cluster create",
            "node management configuration",
            "SVM create/configure",
            "iSCSI LIF create/configure",
            "storage provisioning",
            "ONTAP image upload",
            "ONTAP upgrade",
            "takeover/giveback",
            "controller reboot",
            "disk wipe",
            "configuration apply",
        ],
    }

    sanitized = redact_sensitive(report, _redaction_values())
    _write_report(sanitized)
    _print_summary(sanitized)
    return 0


def _operator_steps() -> list[str]:
    return [
        "Keep NETAPP_CONFIGURED=false for this readiness run.",
        "Use the portal NetApp page to review planned targets separately from current/discovered targets.",
        "Physically verify controller identity, power, cabling, and management network patching.",
        "Use an operator-managed serial terminal if console state must be observed.",
        "Record manual observations in the portal; do not paste passwords, tokens, or raw configs.",
        "Do not run ONTAP setup, firmware upgrade, takeover/giveback, reboot, wipe, or apply from this app.",
    ]


def _file_mode(path: Path) -> str | None:
    if not path.exists():
        return None
    return oct(path.stat().st_mode & 0o777)


def _redaction_values() -> list[str]:
    values: list[str] = []
    for key, value in os.environ.items():
        if _sensitive_key(key) and value:
            values.append(value)
    return values


def _sensitive_key(key: str) -> bool:
    key = key.lower()
    return any(
        fragment in key
        for fragment in ("password", "token", "secret", "credential", "authorization", "cookie")
    )


def _write_report(report: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = REPORT_DIR / f"netapp-readiness-{stamp}.json"
    markdown_path = REPORT_DIR / f"netapp-readiness-{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")


def _markdown_report(report: dict[str, Any]) -> str:
    safety = report["safety"]
    comparison = report["comparison_counts"]
    lines = [
        "# NetApp Real-Run Readiness",
        "",
        f"Checked at: {report['checked_at']}",
        f"Provider mode: {report['provider_mode']}",
        f"Scope: {report['safe_real_run_scope']}",
        "",
        "## Safety",
        f"- NETAPP_CONFIGURED: {safety['netapp_configured']}",
        f"- local_readonly_ack: {safety['local_readonly_ack']}",
        f"- apply_enabled: {safety['apply_enabled']}",
        f"- probe_enabled: {safety['probe_enabled']}",
        f"- upgrade_enabled: {safety['upgrade_enabled']}",
        "",
        "## Readiness",
        f"- setup: {report['setup_readiness']['status']}",
        f"- upgrade: {report['upgrade_readiness']['status']}",
        f"- matched comparison rows: {comparison['matched']}",
        f"- unknown comparison rows: {comparison['unknown']}",
        f"- warning comparison rows: {comparison['warning']}",
        f"- blocker comparison rows: {comparison['blocker']}",
        "",
        "## Operator Steps",
    ]
    lines.extend(f"- {step}" for step in report["operator_steps"])
    lines.extend(["", "## Not Attempted"])
    lines.extend(f"- {item}" for item in report["not_attempted"])
    lines.extend(["", "## Blockers"])
    for blocker in [
        *report.get("console_blockers", []),
        *report.get("comparison_blockers", []),
        *report.get("upgrade_blockers", []),
    ]:
        lines.append(f"- {blocker}")
    lines.append("")
    return "\n".join(lines)


def _print_summary(report: dict[str, Any]) -> None:
    comparison = report["comparison_counts"]
    print("netapp_real_run_readiness=complete")
    print(f"provider_mode={report['provider_mode']}")
    print(f"netapp_configured={report['safety']['netapp_configured']}")
    print(f"setup_status={report['setup_readiness']['status']}")
    print(f"upgrade_status={report['upgrade_readiness']['status']}")
    print(
        "comparison_counts="
        f"matched:{comparison['matched']} "
        f"unknown:{comparison['unknown']} "
        f"warning:{comparison['warning']} "
        f"blocker:{comparison['blocker']}"
    )
    print("artifacts_dir=artifacts/real-lab")
    print("no_netapp_calls_made=true")


if __name__ == "__main__":
    raise SystemExit(main())
