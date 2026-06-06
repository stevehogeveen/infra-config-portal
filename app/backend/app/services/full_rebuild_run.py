from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.providers.redaction import redact_sensitive
from app.services.hpe_raid import REPO_ROOT

CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
BASELINE_REPORT = CODEX_RUN_DIR / "full-device-rebuild-baseline-report.md"
CISCO_PRIVILEGE_REPORT = CODEX_RUN_DIR / "cisco-privilege-check-report.md"
CISCO_BOOTSTRAP_REPORT = CODEX_RUN_DIR / "cisco-full-bootstrap-report.md"
HPE_ILO_REPORT = CODEX_RUN_DIR / "hpe-full-rebuild-ilo-report.md"
HPE_RAID_REPORT = CODEX_RUN_DIR / "hpe-full-rebuild-raid-report.md"
ESXI_BOOT_REPORT = CODEX_RUN_DIR / "esxi-full-rebuild-boot-report.md"
FINAL_REPORT = CODEX_RUN_DIR / "full-device-rebuild-4h-report.md"
SUMMARY_JSON = CODEX_RUN_DIR / "full-device-rebuild-4h-summary-redacted.json"
EXECUTION_SUMMARY_JSON = CODEX_RUN_DIR / "full-device-rebuild-execution-redacted.json"
REAL_LAB_ENV = REPO_ROOT / ".env.local.real-lab"

REQUESTED_REPORTS = {
    "baseline": BASELINE_REPORT,
    "cisco_privilege": CISCO_PRIVILEGE_REPORT,
    "cisco_bootstrap": CISCO_BOOTSTRAP_REPORT,
    "hpe_ilo": HPE_ILO_REPORT,
    "hpe_raid": HPE_RAID_REPORT,
    "esxi_boot": ESXI_BOOT_REPORT,
    "final": FINAL_REPORT,
}

SOURCE_REPORTS = {
    "firmware_compliance": CODEX_RUN_DIR / "firmware-compliance-report.md",
    "cisco_console": CODEX_RUN_DIR / "cisco-4h-lab-run-report.md",
    "cisco_privilege": CISCO_PRIVILEGE_REPORT,
    "cisco_bootstrap_apply": CODEX_RUN_DIR / "cisco-bootstrap-apply-report.md",
    "ilo_reachability": CODEX_RUN_DIR / "ilo-real-run-report.md",
    "raid_discovery": CODEX_RUN_DIR / "hpe-raid-discovery-report.md",
    "raid_plan": CODEX_RUN_DIR / "hpe-raid-plan-report.md",
    "raid_pending": CODEX_RUN_DIR / "hpe-raid-pending-report.md",
    "raid_validate_after_reset": CODEX_RUN_DIR / "hpe-raid-after-reset-validation-report.md",
    "esxi_readiness": CODEX_RUN_DIR / "esxi-install-readiness-report.md",
    "esxi_media": CODEX_RUN_DIR / "esxi-media-url-report.md",
    "esxi_virtual_media": CODEX_RUN_DIR / "esxi-virtual-media-report.md",
    "esxi_one_time_boot": CODEX_RUN_DIR / "esxi-one-time-boot-report.md",
    "esxi_installer_boot": CODEX_RUN_DIR / "esxi-installer-boot-report.md",
}

SUMMARY_ONLY_MESSAGE = "Report-only summary; no live device calls are attempted by this target."


def build_full_rebuild_summary_reports() -> dict[str, Any]:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    checked_at = _now()
    git_status = _git_status()
    source_summaries = {
        key: _report_summary(path)
        for key, path in SOURCE_REPORTS.items()
    }
    stages = {
        "baseline": _stage("completed", "Baseline captured from repository and existing artifacts."),
        "cisco_privilege": _cisco_privilege_stage(source_summaries),
        "cisco_bootstrap": _stage(
            "summary_only",
            "Cisco bootstrap was not executed by the report-only summary.",
            ["Run `make provider-lab-full-rebuild` for real execution."],
        ),
        "hpe_ilo": _stage(
            "summary_only",
            "iLO inventory refresh was not executed by the report-only summary.",
        ),
        "hpe_raid": _stage(
            "summary_only",
            "RAID workflow was not executed by the report-only summary.",
        ),
        "esxi_boot": _stage(
            "summary_only",
            "ESXi virtual media and boot workflow were not executed by the report-only summary.",
        ),
        "post_build_validation": _stage(
            "summary_only",
            "Post-build device validation is part of the real execution and build verification targets.",
        ),
        "ui_and_tests": _stage(
            "completed",
            "UI summary panel is available; verification commands are recorded in the Codex final response.",
        ),
    }
    payload = {
        "provider_id": "full-device-rebuild",
        "checked_at": checked_at,
        "status": "summary_only",
        "message": SUMMARY_ONLY_MESSAGE,
        "provider_mode": "local-lab-readwrite",
        "env_file": ".env.local.real-lab",
        "mock_results_used": False,
        "blockers": [],
        "warnings": [
            "Existing artifact summaries are referenced as historical evidence only.",
            "No secrets, raw transcripts, or credentials are written by this summary workflow.",
        ],
        "git": git_status,
        "source_reports": source_summaries,
        "stages": stages,
        "artifacts": {
            key: _display_path(path)
            for key, path in REQUESTED_REPORTS.items()
        }
        | {"summary_json": _display_path(SUMMARY_JSON)},
        "next_safe_action": "Run `make provider-lab-full-rebuild` from the repository root for real lab execution.",
    }
    sanitized = _sanitize(payload)
    _write_requested_reports(sanitized)
    SUMMARY_JSON.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
    return sanitized


def build_full_rebuild_reports() -> dict[str, Any]:
    return build_full_rebuild_summary_reports()


def run_full_rebuild_execution() -> dict[str, Any]:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    checked_at = _now()
    git_status = _git_status()
    stages: dict[str, Any] = {
        "baseline": _stage("completed", "Baseline captured before live stages."),
    }
    firmware_report = SOURCE_REPORTS.get("firmware_compliance", CODEX_RUN_DIR / "firmware-compliance-report.md")
    stages["firmware_compliance"] = _run_live_stage(
        ["scripts/firmware_compliance.py", "compliance"],
        firmware_report,
    )

    stage_specs = [
        ("cisco_console_bootstrap", ["scripts/cisco_real_lab_workflow.py", "--apply"], SOURCE_REPORTS["cisco_console"]),
        ("ilo_reachability_inventory", ["scripts/ilo_real_reachability.py"], SOURCE_REPORTS["ilo_reachability"]),
        ("hpe_raid_discovery", ["scripts/hpe_raid_workflow.py", "discovery"], SOURCE_REPORTS["raid_discovery"]),
        ("hpe_raid_plan", ["scripts/hpe_raid_workflow.py", "plan", "--default-esxi-intent"], SOURCE_REPORTS["raid_plan"]),
        ("hpe_raid_pending", ["scripts/hpe_raid_workflow.py", "pending"], SOURCE_REPORTS["raid_pending"]),
        ("esxi_media_url", ["scripts/esxi_boot_workflow.py", "media-url"], SOURCE_REPORTS["esxi_media"]),
        ("esxi_insert_virtual_media", ["scripts/esxi_boot_workflow.py", "insert-virtual-media"], SOURCE_REPORTS["esxi_virtual_media"]),
        ("esxi_one_time_boot", ["scripts/esxi_boot_workflow.py", "one-time-boot"], SOURCE_REPORTS["esxi_one_time_boot"]),
        ("esxi_detect_installer", ["scripts/esxi_boot_workflow.py", "detect-installer"], SOURCE_REPORTS["esxi_installer_boot"]),
    ]
    if os.getenv("LAB_ALLOW_POWER_ACTIONS", "").strip().lower() in {"1", "true", "yes", "on"}:
        stage_specs.insert(
            -1,
            ("esxi_reset_installer_boot", ["scripts/esxi_boot_workflow.py", "reset-installer-boot"], SOURCE_REPORTS["esxi_installer_boot"]),
        )

    if stages["firmware_compliance"].get("status") == "blocked":
        for key, _command, report in stage_specs:
            stages[key] = _stage(
                "blocked",
                "Stage was not run because firmware compliance blocked the full rebuild.",
                [f"Resolve firmware compliance first; inspect `{_display_path(report)}` after rerun."],
            )
    else:
        for key, command, report in stage_specs:
            stages[key] = _run_live_stage(command, report)
    stages["cisco_bootstrap"] = stages["cisco_console_bootstrap"]
    stages["hpe_ilo"] = stages["ilo_reachability_inventory"]
    stages["hpe_raid"] = _combined_stage(
        "HPE RAID discovery, plan, and pending checks ran.",
        [stages["hpe_raid_discovery"], stages["hpe_raid_plan"], stages["hpe_raid_pending"]],
    )
    stages["esxi_boot"] = _combined_stage(
        "ESXi media, VirtualMedia, boot override, and installer detection stages ran.",
        [
            stage
            for key, stage in stages.items()
            if key.startswith("esxi_") and key not in {"esxi_boot"}
        ],
    )

    blockers = [
        blocker
        for stage in stages.values()
        for blocker in stage.get("blockers", [])
        if isinstance(stage, dict)
    ]
    failed = [key for key, stage in stages.items() if stage.get("status") == "failed"]
    blocked = [key for key, stage in stages.items() if stage.get("status") == "blocked"]
    status = "failed" if failed else "blocked" if blocked or blockers else "completed"
    payload = {
        "provider_id": "full-device-rebuild",
        "checked_at": checked_at,
        "status": status,
        "message": "Real full lab rebuild execution ran live local-lab-readwrite stages.",
        "provider_mode": "local-lab-readwrite",
        "env_file": ".env.local.real-lab",
        "mock_results_used": False,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": _execution_warnings(),
        "git": git_status,
        "source_reports": {
            key: _report_summary(path)
            for key, path in SOURCE_REPORTS.items()
        },
        "stages": stages,
        "artifacts": {
            key: _display_path(path)
            for key, path in REQUESTED_REPORTS.items()
        }
        | {"execution_summary_json": _display_path(EXECUTION_SUMMARY_JSON)},
        "next_safe_action": _next_action(status, blockers),
    }
    sanitized = _sanitize(payload)
    _write_requested_reports(sanitized)
    EXECUTION_SUMMARY_JSON.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
    SUMMARY_JSON.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
    return sanitized


def get_full_rebuild_summary() -> dict[str, Any]:
    if SUMMARY_JSON.exists():
        try:
            payload = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except (OSError, ValueError):
            pass
    return {
        "provider_id": "full-device-rebuild",
        "checked_at": None,
        "status": "not_run",
        "message": "Full rebuild orchestration summary has not been generated yet.",
        "provider_mode": "unknown",
        "mock_results_used": False,
        "blockers": ["Full rebuild summary has not been generated yet."],
        "warnings": [],
        "stages": {},
        "artifacts": {
            key: _display_path(path)
            for key, path in REQUESTED_REPORTS.items()
        },
        "next_safe_action": "Run `make provider-lab-full-rebuild` from the repository root.",
    }


def _run_live_stage(command: list[str], report: Path) -> dict[str, Any]:
    env = _real_lab_env()
    python = ".venv/bin/python" if (REPO_ROOT / "app" / "backend" / ".venv" / "bin" / "python").exists() else "python3"
    result = subprocess.run(
        [python, *command],
        cwd=REPO_ROOT / "app" / "backend",
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=int(os.getenv("FULL_REBUILD_STAGE_TIMEOUT_SECONDS", "1800")),
    )
    parsed = _parse_stage_json(result.stdout)
    blockers = list(parsed.get("blockers") or [])
    if result.returncode != 0 and not blockers:
        blockers.extend(_report_blockers(report))
    if result.returncode != 0 and not blockers:
        blockers.append(f"Live stage exited with code {result.returncode}; inspect `{_display_path(report)}`.")
    status = parsed.get("status")
    if status not in {"completed", "ready", "ok", "blocked", "failed"}:
        status = "blocked" if blockers or result.returncode else "completed"
    if status in {"ready", "ok"}:
        status = "completed"
    return {
        "status": status,
        "command": " ".join(command),
        "returncode": result.returncode,
        "report": _display_path(report),
        "message": parsed.get("message") or parsed.get("classification") or "Live stage completed with redacted output captured.",
        "blockers": blockers,
        "warnings": list(parsed.get("warnings") or []),
        "summary": _sanitize(parsed),
    }


def _combined_stage(message: str, stage_items: list[dict[str, Any]]) -> dict[str, Any]:
    blockers = [blocker for stage in stage_items for blocker in stage.get("blockers", [])]
    warnings = [warning for stage in stage_items for warning in stage.get("warnings", [])]
    statuses = [stage.get("status") for stage in stage_items]
    status = "failed" if "failed" in statuses else "blocked" if blockers or "blocked" in statuses else "completed"
    return {
        "status": status,
        "message": message,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
    }


def _report_blockers(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    blockers: list[str] = []
    in_blockers = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_blockers = stripped.lower() == "## blockers"
            continue
        if in_blockers and stripped.startswith("- "):
            blockers.append(stripped[2:])
        elif in_blockers and stripped.startswith("## "):
            break
    return blockers[:12]


def _real_lab_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PROVIDER_MODE"] = "local-lab-readwrite"
    env["PYTHONPATH"] = "."
    if REAL_LAB_ENV.exists():
        from dotenv import dotenv_values

        for key, value in dotenv_values(REAL_LAB_ENV).items():
            if value is not None and key not in env:
                env[key] = value
    return env


def _parse_stage_json(output: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(output):
        if char != "{":
            continue
        candidate = output[index:]
        try:
            parsed, _ = decoder.raw_decode(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _execution_warnings() -> list[str]:
    warnings = ["Real execution target does not block only because the caller is Codex or codex exec."]
    if not REAL_LAB_ENV.exists():
        warnings.append(".env.local.real-lab was not found; live stages may block on missing configuration.")
    if os.getenv("LAB_ALLOW_POWER_ACTIONS", "").strip().lower() not in {"1", "true", "yes", "on"}:
        warnings.append("Server reset stage was skipped because LAB_ALLOW_POWER_ACTIONS is not enabled.")
    return warnings


def _next_action(status: str, blockers: list[str]) -> str:
    if status == "completed":
        return "Run `make provider-lab-build-verification` and review post-build validation."
    if blockers:
        return blockers[0]
    return "Inspect stage reports under artifacts/codex-runs/."


def _write_requested_reports(payload: dict[str, Any]) -> None:
    BASELINE_REPORT.write_text(_baseline_markdown(payload), encoding="utf-8")
    CISCO_BOOTSTRAP_REPORT.write_text(_stage_markdown("Cisco Full Bootstrap Report", payload, "cisco_bootstrap"), encoding="utf-8")
    HPE_ILO_REPORT.write_text(_stage_markdown("HPE Full Rebuild iLO Report", payload, "hpe_ilo"), encoding="utf-8")
    HPE_RAID_REPORT.write_text(_stage_markdown("HPE Full Rebuild RAID Report", payload, "hpe_raid"), encoding="utf-8")
    ESXI_BOOT_REPORT.write_text(_stage_markdown("ESXi Full Rebuild Boot Report", payload, "esxi_boot"), encoding="utf-8")
    FINAL_REPORT.write_text(_final_markdown(payload), encoding="utf-8")


def _cisco_privilege_stage(source_summaries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    summary = source_summaries.get("cisco_privilege") or {}
    text = summary.get("extract", "")
    blockers = []
    if "Privileged exec confirmed: `False`" in text or "Did not reach privileged exec" in text:
        blockers.append("Cisco console reached exec but privileged exec was not confirmed.")
    if not CISCO_PRIVILEGE_REPORT.exists():
        blockers.append("Cisco privilege report is missing.")
    return _stage(
        "blocked" if blockers else "unknown",
        "Cisco privilege state is summarized from the latest report-only evidence.",
        blockers,
    )


def _stage(status: str, message: str, blockers: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "blockers": blockers or [],
        "warnings": [],
    }


def _git_status() -> dict[str, Any]:
    status = _run_git(["status", "--short"])
    changed = [line for line in status.splitlines() if line.strip()]
    diff_stat = _run_git(["diff", "--stat"])
    return {
        "changed_file_count": len(changed),
        "changed_files": changed[:120],
        "diff_stat": diff_stat.splitlines()[:120],
    }


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout + result.stderr).strip()


def _report_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "path": _display_path(path)}
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [line for line in text.splitlines() if line.strip()]
    extract = []
    for line in lines:
        lowered = line.lower()
        if (
            line.startswith("#")
            or "status" in lowered
            or "blocker" in lowered
            or "privileged" in lowered
            or "report" in lowered
        ):
            extract.append(line)
        if len(extract) >= 24:
            break
    return {
        "status": "present",
        "path": _display_path(path),
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
        "line_count": len(lines),
        "extract": "\n".join(extract),
    }


def _baseline_markdown(payload: dict[str, Any]) -> str:
    git = payload["git"]
    reports = payload["source_reports"]
    lines = [
        "# Full Device Rebuild Baseline Report",
        "",
        "## Summary",
        "",
        f"- Checked at: `{payload['checked_at']}`",
        f"- Provider mode: `{payload['provider_mode']}`",
        f"- Env file: `{payload['env_file']}`",
        f"- Changed file count: `{git['changed_file_count']}`",
        f"- Real device calls from this run: `{'attempted' if payload['status'] != 'summary_only' else 'not attempted'}`",
        "",
        "## Changed Files",
        "",
    ]
    lines.extend(f"- `{item}`" for item in git["changed_files"][:80])
    lines.extend(["", "## Existing Report Inventory", ""])
    lines.extend(
        f"- {key}: `{report.get('status')}` `{report.get('path')}`"
        for key, report in reports.items()
    )
    lines.extend(["", "## Safety", "", "- No secrets or raw console transcripts are included.", ""])
    return "\n".join(lines)


def _stage_markdown(title: str, payload: dict[str, Any], stage_key: str) -> str:
    stage = payload["stages"][stage_key]
    lines = [
        f"# {title}",
        "",
        "## Summary",
        "",
        f"- Checked at: `{payload['checked_at']}`",
        f"- Status: `{stage['status']}`",
        f"- Message: {stage['message']}",
        f"- Mock results used: `{payload['mock_results_used']}`",
        "",
        "## Blockers",
        "",
    ]
    blockers = stage.get("blockers") or []
    lines.extend(f"- {blocker}" for blocker in blockers)
    if not blockers:
        lines.append("- none")
    lines.extend(["", "## Referenced Evidence", ""])
    for key, report in payload["source_reports"].items():
        if report.get("status") == "present":
            lines.append(f"- {key}: `{report.get('path')}`")
    lines.extend(["", "## Safety", "", "- No secrets or raw console transcripts are included.", ""])
    return "\n".join(lines)


def _final_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Full Device Rebuild 4h Report",
        "",
        "## Summary",
        "",
        f"- Checked at: `{payload['checked_at']}`",
        f"- Overall status: `{payload['status']}`",
        f"- Provider mode: `{payload['provider_mode']}`",
        f"- Mock results used: `{payload['mock_results_used']}`",
        "",
        "## Stage Status",
        "",
    ]
    for key, stage in payload["stages"].items():
        lines.append(f"- {key}: `{stage['status']}` - {stage['message']}")
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- {blocker}" for blocker in payload["blockers"])
    lines.extend(["", "## Artifacts", ""])
    for key, path in payload["artifacts"].items():
        lines.append(f"- {key}: `{path}`")
    lines.extend(["", "## Next Safe Action", "", payload["next_safe_action"], ""])
    return "\n".join(lines)


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive(payload, [])


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
