from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = REPO_ROOT / "artifacts" / "real-lab"

from app.services.env_utils import load_real_lab_env  # noqa: E402

load_real_lab_env(REPO_ROOT)

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.providers.action_policy import LOCAL_LAB_MODE, LOCAL_READONLY_MODE  # noqa: E402
from app.providers.redaction import redact_sensitive  # noqa: E402
from app.services.json_file_store import write_json_object, write_text_value  # noqa: E402
from app.services.lab_profiles import list_lab_profiles  # noqa: E402
from app.services.workflow_action_runner import run_workflow_action  # noqa: E402

REAL_MODES = {LOCAL_READONLY_MODE, LOCAL_LAB_MODE}
REAL_SOURCE_TYPES = {"live_probe", "live_cached"}
ACTION_GROUPS = (
    ("network", "cisco.setup-readiness", "Cisco setup readiness"),
    ("network", "cisco.ssh-readonly-probe", "Cisco SSH read-only show commands"),
    ("network", "cisco.current-intent-diff", "Cisco current-to-intent diff"),
    ("server", "ilo.reachability", "iLO reachability"),
    ("server", "raid.discovery", "HPE RAID discovery"),
    ("server", "raid.plan", "HPE RAID plan"),
    ("server", "raid.pending-check", "HPE RAID pending check"),
    ("storage", "netapp.live-state", "NetApp live state"),
    ("storage", "netapp.nfs-setup-validate", "NetApp NFS validation"),
    ("storage", "netapp.iscsi-setup-validate", "NetApp iSCSI validation"),
    ("virtualization", "esxi.management-validation", "ESXi management validation"),
    ("virtualization", "esxi.iscsi-datastore-validate", "ESXi iSCSI datastore validation"),
    ("virtualization", "esxi.vm-deploy-validate", "ESXi VM deployment validation"),
    ("virtualization", "vcenter-netapp.readiness", "vCenter NetApp readiness"),
    ("virtualization", "vcenter.post-attach-validation", "vCenter post-attach validation"),
    ("firmware", "firmware.compliance-check", "Firmware compliance"),
    ("validation", "lab-validation.summary", "Lab validation summary"),
)


def main() -> int:
    profile_state = _profile_state()
    selected_actions = _selected_actions(profile_state)
    report: dict[str, Any] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "provider_mode": settings.provider_mode,
        "not_mock": settings.provider_mode in REAL_MODES,
        "active_profile": _active_profile_summary(profile_state),
        "selected_actions": [item["action_id"] for item in selected_actions],
        "skipped_actions": [item for item in selected_actions if item["status"] == "skipped"],
        "results": [],
    }

    if settings.provider_mode not in REAL_MODES:
        report["quality_gate"] = {
            "status": "failed",
            "message": "Operator read-only sweep requires PROVIDER_MODE=local-readonly or local-lab-readwrite.",
        }
        _write_report(report)
        print(json.dumps(redact_sensitive(report, _redaction_values()), indent=2))
        return 2

    for item in selected_actions:
        if item["status"] == "skipped":
            continue
        report["results"].append(_run_action(item["action_id"], item["label"], item["stage"], optional=bool(item.get("optional"))))

    report["quality_gate"] = _quality_gate(report)
    _write_report(report)
    print(json.dumps(redact_sensitive(report, _redaction_values()), indent=2))
    return 1 if report["quality_gate"]["status"] == "failed" else 0


def _profile_state() -> dict[str, Any]:
    try:
        state = list_lab_profiles()
    except Exception as exc:  # pragma: no cover - defensive real-lab path
        return {"load_error": f"{exc.__class__.__name__}: {exc}"}
    return state if isinstance(state, dict) else {}


def _active_profile_summary(state: dict[str, Any]) -> dict[str, Any]:
    profile = _dict(state.get("active_profile")) or _dict(state.get("runtime_profile"))
    features = _dict(profile.get("features"))
    return {
        "name": profile.get("name") or "unknown",
        "deployment_label": features.get("deployment_label") or "unknown",
        "netapp_enabled": features.get("netapp_enabled"),
        "vcenter_enabled": features.get("vcenter_enabled"),
        "storage_location": features.get("storage_location"),
        "storage_protocol": features.get("storage_protocol"),
    }


def _selected_actions(state: dict[str, Any]) -> list[dict[str, Any]]:
    profile = _dict(state.get("active_profile")) or _dict(state.get("runtime_profile"))
    features = _dict(profile.get("features"))
    netapp_enabled = features.get("netapp_enabled") is not False
    vcenter_enabled = features.get("vcenter_enabled") is True
    storage_protocol = str(features.get("storage_protocol") or "").strip().lower()

    selected: list[dict[str, Any]] = []
    for stage, action_id, label in ACTION_GROUPS:
        skip_reason = ""
        if action_id.startswith("netapp.") and not netapp_enabled:
            skip_reason = "NetApp is out of scope for the active lab profile."
        if action_id.startswith("esxi.iscsi-datastore") and not netapp_enabled:
            skip_reason = "NetApp shared storage is out of scope for the active lab profile."
        if action_id.startswith("vcenter") and not vcenter_enabled:
            skip_reason = "vCenter is out of scope for the active lab profile."
        optional = False
        optional_reason = ""
        if netapp_enabled and action_id == "netapp.nfs-setup-validate" and storage_protocol == "iscsi":
            optional = True
            optional_reason = "NFS is an alternate shared-storage protocol; active storage protocol is iSCSI."
        if netapp_enabled and action_id == "netapp.iscsi-setup-validate" and storage_protocol == "nfs":
            optional = True
            optional_reason = "iSCSI is an alternate shared-storage protocol; active storage protocol is NFS."
        if netapp_enabled and action_id == "esxi.iscsi-datastore-validate" and storage_protocol != "iscsi":
            optional = True
            optional_reason = "ESXi iSCSI datastore validation is an alternate shared-storage protocol check."
        selected.append(
            {
                "action_id": action_id,
                "label": label,
                "optional": optional,
                "optional_reason": optional_reason,
                "stage": stage,
                "status": "skipped" if skip_reason else "selected",
                "skip_reason": skip_reason,
            }
        )
    return selected


def _run_action(action_id: str, label: str, stage: str, *, optional: bool = False) -> dict[str, Any]:
    try:
        with SessionLocal() as session:
            result = run_workflow_action(
                action_id,
                session,
                payload={
                    "requested_by": "operator-readonly-sweep",
                    "reason": "Real lab read-only operator workflow sweep",
                    "dry_run": True,
                },
            )
    except Exception as exc:  # pragma: no cover - defensive real-lab path
        return {
            "action_id": action_id,
            "label": label,
            "optional": optional,
            "stage": stage,
            "status": "failed",
            "not_mock": False,
            "source_type": "exception",
            "blockers": [f"Workflow action raised {exc.__class__.__name__}."],
            "warnings": [],
            "stderr_summary": str(exc),
        }
    stdout_payload = _stdout_payload(result)
    payload_source = _payload_source(stdout_payload)
    payload_blockers = _strings(stdout_payload.get("blockers")) if stdout_payload else []
    payload_warnings = _strings(stdout_payload.get("warnings")) if stdout_payload else []
    return {
        "action_id": action_id,
        "label": label,
        "optional": optional,
        "stage": stage,
        "status": result.get("status"),
        "not_mock": result.get("not_mock"),
        "source_type": result.get("source_type"),
        "evidence_source_type": payload_source.get("source_type"),
        "evidence_freshness": payload_source.get("freshness"),
        "evidence_is_current": payload_source.get("is_current"),
        "executed": result.get("executed"),
        "return_code": result.get("return_code"),
        "summary": result.get("summary"),
        "blockers": _unique_strings([*_strings(result.get("blockers")), *payload_blockers]),
        "warnings": _unique_strings([*_strings(result.get("warnings")), *payload_warnings]),
        "stderr_summary": result.get("stderr_summary") or "",
        "trace_artifact": result.get("trace_artifact"),
        "evidence_summary": _action_evidence_summary(action_id, result),
    }


def _quality_gate(report: dict[str, Any]) -> dict[str, Any]:
    results = [_dict(item) for item in report.get("results", [])]
    required_results = [item for item in results if not item.get("optional")]
    optional_results = [item for item in results if item.get("optional")]
    failed = [
        item
        for item in required_results
        if item.get("status") == "failed"
        or item.get("not_mock") is False
        or _effective_source_type(item) not in REAL_SOURCE_TYPES
        or _evidence_is_stale(item)
    ]
    blocked = [item for item in required_results if item.get("status") == "blocked"]
    optional_blocked = [item for item in optional_results if item.get("status") in {"blocked", "failed"}]
    warnings = [item for item in results if item.get("warnings")]
    if failed:
        return {
            "status": "failed",
            "message": f"{len(failed)} read-only action(s) failed or did not produce live real-lab evidence.",
            "failed_actions": [item.get("action_id") for item in failed],
            "blocked_actions": [item.get("action_id") for item in blocked],
            "optional_blocked_actions": [item.get("action_id") for item in optional_blocked],
        }
    if blocked:
        return {
            "status": "blocked",
            "message": f"{len(blocked)} read-only action(s) completed safely and reported lab blockers.",
            "blocked_actions": [item.get("action_id") for item in blocked],
            "optional_blocked_actions": [item.get("action_id") for item in optional_blocked],
            "warning_actions": [item.get("action_id") for item in warnings],
        }
    if optional_blocked:
        return {
            "status": "completed",
            "message": (
                "All required read-only operator actions completed with real-lab evidence; "
                f"{len(optional_blocked)} optional parity check(s) reported blockers."
            ),
            "optional_blocked_actions": [item.get("action_id") for item in optional_blocked],
            "warning_actions": [item.get("action_id") for item in warnings],
        }
    return {
        "status": "completed",
        "message": "All selected read-only operator actions completed with real-lab evidence.",
        "optional_blocked_actions": [item.get("action_id") for item in optional_blocked],
        "warning_actions": [item.get("action_id") for item in warnings],
    }


def _stdout_payload(result: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(str(result.get("stdout_summary") or "{}"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _payload_source(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    return {
        "source_type": payload.get("source_type"),
        "freshness": payload.get("freshness"),
        "is_current": payload.get("is_current"),
    }


def _effective_source_type(item: dict[str, Any]) -> str | None:
    return str(item.get("evidence_source_type") or item.get("source_type") or "")


def _evidence_is_stale(item: dict[str, Any]) -> bool:
    freshness = str(item.get("evidence_freshness") or "")
    if freshness in {"stale", "historical"}:
        return True
    return item.get("evidence_is_current") is False


def _write_report(report: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe_report = redact_sensitive(report, _redaction_values())
    write_json_object(REPORT_DIR / "operator-readonly-sweep-latest.json", safe_report)
    write_text_value(REPORT_DIR / "operator-readonly-sweep-latest.md", _markdown(safe_report))


def _markdown(report: dict[str, Any]) -> str:
    profile = _dict(report.get("active_profile"))
    gate = _dict(report.get("quality_gate"))
    lines = [
        "# Operator Read-Only Sweep",
        "",
        f"- Checked at: `{report.get('checked_at')}`",
        f"- Provider mode: `{report.get('provider_mode')}`",
        f"- Not mock: `{report.get('not_mock')}`",
        f"- Active profile: `{profile.get('name')}`",
        f"- Scenario: `{profile.get('deployment_label')}`",
        f"- Quality gate: `{gate.get('status')}` - {gate.get('message')}",
        "",
        "## Results",
        "",
        "| Stage | Action | Scope | Status | Evidence | Blockers | Warnings |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report.get("results", []):
        row = _dict(item)
        lines.append(
            "| {stage} | `{action}` | {scope} | `{status}` | {evidence} | {blockers} | {warnings} |".format(
                stage=_cell(row.get("stage")),
                action=_cell(row.get("action_id")),
                scope=_cell("optional" if row.get("optional") else "required"),
                status=_cell(row.get("status")),
                evidence=_cell(_evidence_text(row)),
                blockers=_cell("; ".join(_strings(row.get("blockers"))) or "-"),
                warnings=_cell("; ".join(_strings(row.get("warnings"))) or "-"),
            )
        )
    optional_blocked = [
        _dict(item)
        for item in report.get("results", [])
        if _dict(item).get("optional") and _dict(item).get("status") == "blocked"
    ]
    if optional_blocked:
        lines.extend(["", "## Optional Blockers", ""])
        lines.append(
            "These checks are outside the active required path, but they identify what must be fixed before using that optional design."
        )
        lines.append("")
        for item in optional_blocked:
            blockers = "; ".join(_strings(item.get("blockers"))) or "No blocker details reported."
            lines.append(f"- `{item.get('action_id')}`: {blockers}")
    skipped = [_dict(item) for item in report.get("skipped_actions", [])]
    if skipped:
        lines.extend(["", "## Skipped By Scenario", ""])
        for item in skipped:
            lines.append(f"- `{item.get('action_id')}`: {item.get('skip_reason')}")
    lines.append("")
    return "\n".join(lines)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _action_evidence_summary(action_id: str, result: dict[str, Any]) -> str:
    try:
        stdout = json.loads(str(result.get("stdout_summary") or "{}"))
    except json.JSONDecodeError:
        return ""
    if action_id == "cisco.current-intent-diff":
        diff = _dict(stdout.get("diff"))
        counts = _dict(stdout.get("current_counts"))
        guardrails = _dict(diff.get("guardrails"))
        guardrail_summary = ", ".join(
            f"{area}:{_dict(evidence).get('status')}"
            for area, evidence in guardrails.items()
        )
        return (
            f"drift {diff.get('drift_count')}; "
            f"vlans parsed {counts.get('vlans')}; ports parsed {counts.get('ports')}; "
            f"missing VLANs {', '.join(_strings(diff.get('missing_vlans'))) or '-'}; "
            f"guardrails {guardrail_summary or '-'}"
        )
    if action_id != "cisco.ssh-readonly-probe":
        return ""
    evidence = _dict(stdout.get("command_evidence"))
    if not evidence:
        return ""
    parts = []
    for command in ("show version", "show interfaces status", "show vlan brief"):
        item = _dict(evidence.get(command))
        status = "captured" if item.get("captured") else "missing"
        detail = item.get("version_hint") or item.get("line_count")
        parts.append(f"{command}: {status}{f' ({detail})' if detail else ''}")
    return "; ".join(parts)


def _evidence_text(row: dict[str, Any]) -> str:
    trace = str(row.get("trace_artifact") or "")
    summary = str(row.get("evidence_summary") or "")
    if trace and summary:
        return f"{trace}; {summary}"
    return trace or summary or "-"


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if value:
        return [str(value)]
    return []


def _unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _cell(value: Any) -> str:
    text = str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")
    return text or "-"


def _redaction_values() -> list[str]:
    values: list[str] = []
    for key, value in os.environ.items():
        if any(fragment in key.lower() for fragment in ("password", "token", "secret", "credential", "authorization", "cookie")) and value:
            values.append(value)
    return values


if __name__ == "__main__":
    raise SystemExit(main())
