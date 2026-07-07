from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.env_utils import env_int, read_env_file_values
from app.services.json_file_store import write_json_object, write_text_value
from app.services.json_utils import parse_json_object
from app.services.list_utils import unique_preserving_order
from app.services.path_utils import display_path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "app" / "backend"
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
REPORT = CODEX_RUN_DIR / "provider-lab-live-status-report.md"
SUMMARY = CODEX_RUN_DIR / "provider-lab-live-status-redacted.json"
REAL_LAB_ENV = REPO_ROOT / ".env.local.real-lab"

STAGES = [
    (
        "ilo-reachability",
        ["scripts/ilo_real_reachability.py"],
        "artifacts/codex-runs/ilo-real-run-report.md",
    ),
    (
        "cisco-console-ethernet",
        ["scripts/cisco_console_ethernet_readiness.py"],
        "artifacts/codex-runs/cisco-console-ethernet-readiness-report.md",
    ),
    (
        "netapp-console-autodiscovery",
        ["scripts/netapp_real_lab_workflow.py", "console-autodiscovery"],
        "artifacts/codex-runs/netapp-console-autodiscovery-report.md",
    ),
    (
        "netapp-console-read-state",
        ["scripts/netapp_real_lab_workflow.py", "console-read-state"],
        "artifacts/codex-runs/netapp-console-state-report.md",
    ),
    (
        "netapp-live-state",
        ["scripts/netapp_real_lab_workflow.py", "live-state"],
        "artifacts/codex-runs/netapp-live-state-report.md",
    ),
    (
        "firmware-compliance",
        ["scripts/firmware_compliance.py", "compliance"],
        "artifacts/codex-runs/firmware-compliance-report.md",
    ),
    (
        "build-verification",
        ["scripts/build_verification.py"],
        "artifacts/codex-runs/build-verification-current-state-report.md",
    ),
]


def main() -> int:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    env = _real_lab_env()
    checked_at = datetime.now(UTC).isoformat()
    stages = [_run_stage(name, command, report, env) for name, command, report in STAGES]
    blockers = [
        blocker
        for stage in stages
        for blocker in stage.get("blockers", [])
        if blocker
    ]
    payload = {
        "provider_id": "provider-lab-live-status",
        "checked_at": checked_at,
        "status": "blocked" if blockers else "ready",
        "source_type": "live_probe",
        "freshness": "current",
        "ttl_seconds": 86400,
        "stale_after_seconds": 86400,
        "is_current": True,
        "is_operator_visible": True,
        "recheck_command": "make provider-lab-refresh-live-state",
        "provider_mode": "local-lab-readwrite",
        "message": "Real lab live status refresh completed with redacted stage summaries.",
        "stages": stages,
        "blockers": unique_preserving_order(blockers),
        "warnings": [
            warning
            for stage in stages
            for warning in stage.get("warnings", [])
            if warning
        ],
        "evidence_artifacts": [report for _name, _command, report in STAGES],
        "artifacts": {
            "report": _rel(REPORT),
            "summary_json": _rel(SUMMARY),
        },
        "next_safe_action": (
            "Review the blocked live stage reports, then rerun `make provider-lab-refresh-live-state`."
            if blockers
            else "Run Build Verification before claiming certification."
        ),
    }
    write_json_object(SUMMARY, payload)
    write_text_value(REPORT, _markdown(payload))
    print(json.dumps(_console_summary(payload), indent=2))
    return 0


def _run_stage(name: str, command: list[str], report: str, env: dict[str, str]) -> dict[str, Any]:
    timeout = env_int("PROVIDER_LAB_LIVE_STAGE_TIMEOUT_SECONDS", 120, minimum=1)
    try:
        result = subprocess.run(
            [_python_executable(), *command],
            cwd=BACKEND_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "stage": name,
            "status": "blocked",
            "returncode": 124,
            "source_type": "live_probe",
            "freshness": "current",
            "is_current": True,
            "report": report,
            "message": "Live stage exceeded the bounded timeout; no secrets were captured.",
            "blockers": [f"{name} exceeded {timeout} seconds; rerun the specific live check or inspect `{report}`."],
            "warnings": [],
        }
    parsed = _parse_json(result.stdout)
    blockers = list(parsed.get("blockers") or [])
    if result.returncode != 0 and not blockers:
        blockers.append(f"{name} exited with code {result.returncode}; inspect `{report}`.")
    status = parsed.get("status")
    if status not in {"ready", "completed", "warning", "blocked", "failed", "not_run"}:
        status = "blocked" if blockers or result.returncode else "completed"
    return {
        "stage": name,
        "status": status,
        "returncode": result.returncode,
        "source_type": "live_probe",
        "freshness": "current",
        "is_current": True,
        "report": report,
        "message": parsed.get("message") or "Live stage completed; redacted summary captured.",
        "blockers": blockers,
        "warnings": list(parsed.get("warnings") or []),
    }


def _real_lab_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(read_env_file_values(REAL_LAB_ENV, skip_keys={"PROVIDER_MODE"}))
    env["PROVIDER_MODE"] = "local-lab-readwrite"
    env["PYTHONPATH"] = "."
    return env


def _parse_json(stdout: str) -> dict[str, Any]:
    return parse_json_object(stdout)


def _python_executable() -> str:
    return os.getenv("PYTHON") or sys.executable


def _rel(path: Path) -> str:
    return display_path(path, REPO_ROOT)


def _console_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "checked_at": payload["checked_at"],
        "status": payload["status"],
        "blockers": payload["blockers"],
        "artifacts": payload["artifacts"],
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Provider Lab Live Status",
        "",
        f"- Checked at: `{payload['checked_at']}`",
        f"- Status: `{payload['status']}`",
        "- Source: `live_probe`",
        "- Runtime mode: `local-lab-readwrite`",
        "",
        "## Stages",
        "",
    ]
    for stage in payload["stages"]:
        lines.append(
            f"- `{stage['status']}` `{stage['stage']}` report=`{stage['report']}`"
        )
        for blocker in stage.get("blockers") or []:
            lines.append(f"  - Blocker: {blocker}")
    lines.extend(["", "## Evidence", ""])
    lines.extend(f"- `{artifact}`" for artifact in payload["evidence_artifacts"])
    lines.extend(["", "## Safety", "", "- No secrets or raw console transcripts are printed.", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
