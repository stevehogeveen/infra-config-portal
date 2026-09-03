from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.providers.cisco_ansible import CiscoAnsibleAdapter
from app.providers.redaction import redact_sensitive
from app.services.json_file_store import write_json_object, write_text_value
from app.services.path_utils import repo_relative_path
from app.services.provider_profile_defaults import active_cisco_network_defaults

REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
CISCO_INTENT_DIFF_JSON = CODEX_RUN_DIR / "cisco-current-intent-diff-redacted.json"
CISCO_INTENT_DIFF_REPORT = CODEX_RUN_DIR / "cisco-current-intent-diff-report.md"


def get_cisco_current_intent_diff(*, write_report: bool = True) -> dict[str, Any]:
    probe = CiscoAnsibleAdapter().probe()
    command_results = probe.get("command_results") if isinstance(probe.get("command_results"), dict) else {}
    version = _dict(command_results.get("show version"))
    vlan_result = _dict(command_results.get("show vlan brief"))
    interface_result = _dict(command_results.get("show interfaces status"))
    current_vlans = _parse_vlans(_string_list(vlan_result.get("stdout_summary")))
    current_ports = _parse_interfaces(_string_list(interface_result.get("stdout_summary")))
    intent = _intent()
    vlan_diff = _vlan_diff(intent["vlans"], current_vlans)
    port_diff = _port_diff(intent["ports"], current_ports)
    guardrails = _guardrail_evidence(intent["guardrails"], command_results)
    not_checked = _not_checked_guardrails(guardrails)
    blockers = _probe_blockers(probe)
    candidate_config_preview = _candidate_config_preview(
        intent=intent,
        vlan_diff=vlan_diff,
        port_diff=port_diff,
        guardrails=guardrails,
        blockers=blockers,
    )
    guardrail_drift_count = sum(1 for item in guardrails.values() if item.get("status") == "warning")
    drift_count = len(vlan_diff["missing"]) + len(vlan_diff["unexpected"]) + len(port_diff) + guardrail_drift_count
    status = "blocked" if blockers else "warning" if drift_count else "ready"
    payload = {
        "provider_id": "cisco-ansible",
        "action": "cisco-current-intent-diff",
        "checked_at": _now(),
        "status": status,
        "message": (
            "Cisco current-to-intent diff is blocked by live probe readiness."
            if blockers
            else f"Cisco current-to-intent diff parsed {len(current_vlans)} VLAN rows and {len(current_ports)} interface rows."
        ),
        "source_type": "live_probe" if not blockers else "not_checked",
        "freshness": "current" if not blockers else "not_checked",
        "probe_status": probe.get("status"),
        "version_hint": version.get("version_hint"),
        "intent": intent,
        "current": {
            "vlans": current_vlans,
            "ports": current_ports,
        },
        "diff": {
            "vlan": vlan_diff,
            "ports": port_diff,
            "guardrails": guardrails,
            "not_checked": not_checked,
            "drift_count": drift_count,
        },
        "candidate_config_preview": candidate_config_preview,
        "remediation_plan": _remediation_plan(
            vlan_diff=vlan_diff,
            port_diff=port_diff,
            guardrails=guardrails,
            candidate_config_preview=candidate_config_preview,
            blockers=blockers,
        ),
        "blockers": blockers,
        "warnings": _warnings(probe, not_checked),
        "not_attempted": [
            "configure terminal",
            "write memory",
            "reload",
            "raw running-config backup",
            "ACL or BPDU remediation",
        ],
        "artifacts": {
            "json": _rel(CISCO_INTENT_DIFF_JSON),
            "report": _rel(CISCO_INTENT_DIFF_REPORT),
        },
        "next_safe_action": (
            blockers[0]
            if blockers
            else "Review VLAN/interface/guardrail drift before guarded config apply."
        ),
    }
    sanitized = redact_sensitive(payload, [])
    if write_report:
        CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
        write_json_object(CISCO_INTENT_DIFF_JSON, sanitized)
        write_text_value(CISCO_INTENT_DIFF_REPORT, _markdown(sanitized))
    return sanitized


def _remediation_plan(
    *,
    vlan_diff: dict[str, Any],
    port_diff: list[dict[str, Any]],
    guardrails: dict[str, Any],
    candidate_config_preview: dict[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    if blockers:
        return {
            "status": "blocked",
            "summary": "Run the Cisco read-only probe until VLAN and interface evidence is available.",
            "safe_to_render_commands": False,
            "command_count": 0,
            "steps": [
                {
                    "label": "Restore read-only evidence",
                    "status": "blocked",
                    "detail": blockers[0],
                    "next_action": "Fix Cisco SSH/read-only probe access, then rerun current-to-intent diff.",
                }
            ],
        }

    missing_vlans = _string_list(vlan_diff.get("missing"))
    unexpected_vlans = _string_list(vlan_diff.get("unexpected"))
    missing_guardrails = _guardrail_missing_items(guardrails)
    command_count = len(_string_list(candidate_config_preview.get("commands")))
    steps = [
        {
            "label": "Create missing VLANs",
            "status": "warning" if missing_vlans else "ready",
            "detail": ", ".join(missing_vlans) if missing_vlans else "No intended VLANs are missing.",
            "next_action": "Review generated VLAN commands before any guarded apply.",
        },
        {
            "label": "Align intended ports",
            "status": "warning" if port_diff else "ready",
            "detail": f"{len(port_diff)} port drift item(s)." if port_diff else "No intended port drift was parsed.",
            "next_action": "Review access/trunk mode changes against the physical cabling plan.",
        },
        {
            "label": "Review guardrails",
            "status": "warning" if missing_guardrails else "ready",
            "detail": ", ".join(missing_guardrails) if missing_guardrails else "Parsed guardrail evidence matches intent.",
            "next_action": "Treat ACL lanes as review-only until exact source/destination policy is approved.",
        },
        {
            "label": "Preserve unexpected VLANs",
            "status": "warning" if unexpected_vlans else "ready",
            "detail": ", ".join(unexpected_vlans) if unexpected_vlans else "No unexpected VLANs were parsed.",
            "next_action": "Do not delete unexpected VLANs from this preview; investigate ownership first.",
        },
    ]
    warning_count = sum(1 for step in steps if step["status"] == "warning")
    return {
        "status": "warning" if warning_count else "ready",
        "summary": (
            f"{warning_count} remediation area(s) need review; {command_count} candidate command line(s) are renderable."
            if warning_count
            else "Cisco current state matches the parsed intent areas."
        ),
        "safe_to_render_commands": candidate_config_preview.get("status") in {"ready", "ready_no_changes"},
        "command_count": command_count,
        "steps": steps,
    }


def _guardrail_missing_items(guardrails: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for area, evidence in guardrails.items():
        row = _dict(evidence)
        if row.get("status") not in {"warning", "not_checked"}:
            continue
        values = _string_list(row.get("missing"))
        if values:
            missing.extend(f"{area}: {value}" for value in values)
        else:
            missing.append(str(area))
    return missing


def _intent() -> dict[str, Any]:
    defaults = active_cisco_network_defaults()
    management_vlan = _string(defaults.get("management_vlan")) or "10"
    esxi_vlan = "30" if management_vlan == "20" else "20"
    storage_vlan = "40" if management_vlan == "30" else "30"
    blackhole_vlan = "999"
    return {
        "vlans": [
            {"id": management_vlan, "name": f"LAB-MGMT-{management_vlan}", "role": "management"},
            {"id": esxi_vlan, "name": "ESXI-HOSTS", "role": "compute"},
            {"id": storage_vlan, "name": "STORAGE-NFS", "role": "storage"},
            {"id": blackhole_vlan, "name": "BLACKHOLE-PARKING", "role": "parking"},
        ],
        "ports": [
            {"port": "Gi1/0/1", "mode": "access", "access_vlan": management_vlan, "role": "operator"},
            {"port": "Gi1/0/2", "mode": "access", "access_vlan": management_vlan, "role": "ilo"},
            {"port": "Gi1/0/3", "mode": "trunk", "trunk_vlans": [management_vlan, esxi_vlan, storage_vlan], "role": "esxi-a"},
            {"port": "Gi1/0/4", "mode": "trunk", "trunk_vlans": [management_vlan, esxi_vlan, storage_vlan], "role": "esxi-b"},
            {"port": "Gi1/0/5", "mode": "access", "access_vlan": storage_vlan, "role": "netapp-a"},
            {"port": "Gi1/0/6", "mode": "access", "access_vlan": storage_vlan, "role": "netapp-b"},
        ],
        "guardrails": {
            "blackhole_vlan": blackhole_vlan,
            "native_vlan": "4094",
            "bpdu_guard_expected": True,
            "acl_lanes": ["MGMT-IN", "STORAGE-NFS-IN", "DROP-ALL"],
        },
    }


def _parse_vlans(lines: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in lines:
        match = re.match(r"^\s*(\d{1,4})\s+([A-Za-z0-9_.:-]+)\s+(\S+)", line)
        if not match:
            continue
        rows.append({"id": match.group(1), "name": match.group(2), "status": match.group(3)})
    return rows


def _parse_interfaces(lines: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in lines:
        parts = line.strip().split()
        if not parts or not re.match(r"^(?:Gi|Te|Tw|Fo|Hu|Eth|Po)\S+", parts[0]):
            continue
        status_index = next(
            (index for index, item in enumerate(parts) if item in {"connected", "notconnect", "disabled", "err-disabled"}),
            -1,
        )
        if status_index < 0:
            continue
        rows.append(
            {
                "port": _normalize_port(parts[0]),
                "status": parts[status_index],
                "vlan": parts[status_index + 1] if len(parts) > status_index + 1 else "unknown",
                "duplex": parts[status_index + 2] if len(parts) > status_index + 2 else "unknown",
                "speed": parts[status_index + 3] if len(parts) > status_index + 3 else "unknown",
                "type": parts[status_index + 4] if len(parts) > status_index + 4 else "unknown",
            }
        )
    return rows


def _vlan_diff(intent: list[dict[str, Any]], current: list[dict[str, Any]]) -> dict[str, Any]:
    desired_ids = {str(item.get("id")) for item in intent}
    current_ids = {str(item.get("id")) for item in current}
    return {
        "missing": sorted(desired_ids - current_ids, key=_sort_vlan),
        "unexpected": sorted(current_ids - desired_ids, key=_sort_vlan),
        "matched": sorted(desired_ids & current_ids, key=_sort_vlan),
    }


def _port_diff(intent: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_by_port = {str(item.get("port")): item for item in current}
    drift: list[dict[str, Any]] = []
    for desired in intent:
        port = str(desired.get("port"))
        actual = current_by_port.get(port)
        if not actual:
            drift.append({"port": port, "status": "not_checked", "reason": "Port not present in show interfaces status."})
            continue
        if desired.get("mode") == "access" and str(actual.get("vlan")) != str(desired.get("access_vlan")):
            drift.append(
                {
                    "port": port,
                    "status": "drift",
                    "reason": f"Expected access VLAN {desired.get('access_vlan')}, saw {actual.get('vlan')}.",
                    "current": actual,
                }
            )
        if desired.get("mode") == "trunk" and str(actual.get("vlan")).lower() != "trunk":
            drift.append(
                {
                    "port": port,
                    "status": "drift",
                    "reason": f"Expected trunk, saw VLAN {actual.get('vlan')}.",
                    "current": actual,
                }
            )
    return drift


def _guardrail_evidence(intent: dict[str, Any], command_results: dict[str, Any]) -> dict[str, Any]:
    bpdu = _bpdu_guard_evidence(command_results)
    acl = _acl_lane_evidence(_string_list(intent.get("acl_lanes")), command_results)
    blackhole = _blackhole_vlan_evidence(str(intent.get("blackhole_vlan") or ""), command_results)
    return {
        "bpdu_guard": bpdu,
        "acl_lanes": acl,
        "blackhole_vlan": blackhole,
    }


def _bpdu_guard_evidence(command_results: dict[str, Any]) -> dict[str, Any]:
    commands = [
        "show running-config | include spanning-tree portfast",
        "show running-config | include spanning-tree bpduguard",
    ]
    lines = _command_lines(command_results, commands)
    captured = _commands_captured(command_results, commands)
    evidence = [line for line in lines if "bpduguard" in line.lower()]
    portfast_lines = [line for line in lines if "portfast" in line.lower()]
    if not captured:
        return {
            "status": "not_checked",
            "matched": [],
            "missing": ["spanning-tree portfast bpduguard default or equivalent"],
            "reason": "Safe Cisco probe did not collect BPDU guard running-config lines.",
        }
    if evidence:
        return {
            "status": "ready",
            "matched": evidence,
            "missing": [],
            "reason": "Read-only running-config include output shows BPDU guard configuration.",
        }
    return {
        "status": "warning",
        "matched": portfast_lines,
        "missing": ["spanning-tree portfast bpduguard default or port-level bpduguard enable"],
        "reason": (
            "Portfast lines were parsed, but BPDU guard was not found."
            if portfast_lines
            else "BPDU guard was not found in read-only include output."
        ),
    }


def _acl_lane_evidence(expected_lanes: list[str], command_results: dict[str, Any]) -> dict[str, Any]:
    command = "show running-config | include ip access-list|ip access-group"
    lines = _command_lines(command_results, [command])
    captured = _commands_captured(command_results, [command])
    if not captured:
        return {
            "status": "not_checked",
            "matched": [],
            "missing": expected_lanes,
            "reason": "Safe Cisco probe did not collect ACL include output.",
        }
    text = "\n".join(lines).lower()
    matched = [lane for lane in expected_lanes if lane.lower() in text]
    missing = [lane for lane in expected_lanes if lane not in matched]
    return {
        "status": "ready" if not missing else "warning",
        "matched": matched,
        "missing": missing,
        "reason": (
            "Read-only running-config include output shows expected ACL lanes."
            if not missing
            else "One or more intended ACL lanes were not found in read-only include output."
        ),
        "lines": lines[:12],
    }


def _blackhole_vlan_evidence(expected_vlan: str, command_results: dict[str, Any]) -> dict[str, Any]:
    vlan_result = _dict(command_results.get("show vlan brief"))
    current_vlans = _parse_vlans(_string_list(vlan_result.get("stdout_summary")))
    matched = [vlan for vlan in current_vlans if str(vlan.get("id")) == expected_vlan]
    if not vlan_result.get("captured"):
        return {
            "status": "not_checked",
            "matched": [],
            "missing": [expected_vlan],
            "reason": "Safe Cisco probe did not collect VLAN output.",
        }
    return {
        "status": "ready" if matched else "warning",
        "matched": matched,
        "missing": [] if matched else [expected_vlan],
        "reason": "Black-hole parking VLAN was found." if matched else "Black-hole parking VLAN is missing.",
    }


def _not_checked_guardrails(guardrails: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for area, evidence in guardrails.items():
        if not isinstance(evidence, dict) or evidence.get("status") != "not_checked":
            continue
        rows.append(
            {
                "area": area,
                "reason": str(evidence.get("reason") or "Guardrail evidence was not checked."),
                "next_safe_action": "Run the fixed read-only Cisco probe before treating this guardrail as proven.",
            }
        )
    return rows


def _candidate_config_preview(
    *,
    intent: dict[str, Any],
    vlan_diff: dict[str, Any],
    port_diff: list[dict[str, Any]],
    guardrails: dict[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    if blockers:
        return {
            "status": "blocked",
            "summary": "Candidate config is blocked until the read-only Cisco probe returns required live output.",
            "commands": [],
            "not_attempted": ["configuration mode", "write memory", "reload", "deletions"],
            "requires_operator_review": True,
        }

    commands: list[str] = []
    notes: list[str] = []
    intent_vlans = {str(item.get("id")): item for item in intent.get("vlans") or [] if isinstance(item, dict)}
    for vlan_id in _string_list(vlan_diff.get("missing")):
        vlan = intent_vlans.get(vlan_id, {})
        commands.extend([f"vlan {vlan_id}", f" name {vlan.get('name') or f'VLAN-{vlan_id}'}", " exit"])

    intent_ports = {str(item.get("port")): item for item in intent.get("ports") or [] if isinstance(item, dict)}
    for item in port_diff:
        row = _dict(item)
        port = str(row.get("port") or "")
        desired = intent_ports.get(port)
        if not desired:
            notes.append(f"{port or 'unknown port'} drift needs manual mapping before a candidate command can be rendered.")
            continue
        commands.extend(_port_candidate_commands(desired))

    bpdu = _dict(guardrails.get("bpdu_guard"))
    if bpdu.get("status") == "warning":
        commands.append("spanning-tree portfast bpduguard default")
    blackhole = _dict(guardrails.get("blackhole_vlan"))
    for vlan_id in _string_list(blackhole.get("missing")):
        vlan = intent_vlans.get(vlan_id, {})
        if not any(command == f"vlan {vlan_id}" for command in commands):
            commands.extend([f"vlan {vlan_id}", f" name {vlan.get('name') or 'BLACKHOLE-PARKING'}", " exit"])
    acl = _dict(guardrails.get("acl_lanes"))
    for lane in _string_list(acl.get("missing")):
        notes.append(f"ACL lane `{lane}` is missing; render exact rules only after source/destination policy is reviewed.")

    unexpected = _string_list(vlan_diff.get("unexpected"))
    if unexpected:
        notes.append(f"Unexpected VLANs are not removed by the candidate preview: {', '.join(unexpected)}.")

    deduped_commands = _dedupe_adjacent_commands(commands)
    return {
        "status": "ready" if deduped_commands else "ready_no_changes",
        "summary": (
            f"{len(deduped_commands)} candidate command lines generated from parsed drift."
            if deduped_commands
            else "No candidate command lines are needed from parsed drift."
        ),
        "commands": deduped_commands,
        "notes": notes,
        "not_attempted": ["configuration mode execution", "write memory", "reload", "VLAN deletion", "ACL rule synthesis"],
        "requires_operator_review": True,
    }


def _port_candidate_commands(desired: dict[str, Any]) -> list[str]:
    port = str(desired.get("port") or "")
    if not port:
        return []
    mode = str(desired.get("mode") or "")
    commands = [f"interface {port}"]
    if mode == "trunk":
        trunk_vlans = ",".join(_string_list(desired.get("trunk_vlans")))
        commands.extend([" switchport mode trunk"])
        if trunk_vlans:
            commands.append(f" switchport trunk allowed vlan {trunk_vlans}")
    elif mode == "access":
        commands.extend([
            " switchport mode access",
            f" switchport access vlan {desired.get('access_vlan')}",
            " spanning-tree portfast",
            " spanning-tree bpduguard enable",
        ])
    elif mode == "disabled":
        commands.extend([
            " switchport mode access",
            f" switchport access vlan {desired.get('access_vlan')}",
            " shutdown",
        ])
    commands.append(" exit")
    return commands


def _dedupe_adjacent_commands(commands: list[str]) -> list[str]:
    deduped: list[str] = []
    for command in commands:
        if not command:
            continue
        if deduped and deduped[-1] == command:
            continue
        deduped.append(command)
    return deduped


def _command_lines(command_results: dict[str, Any], commands: list[str]) -> list[str]:
    lines: list[str] = []
    for command in commands:
        result = _dict(command_results.get(command))
        for line in _string_list(result.get("stdout_summary")):
            if _is_command_echo_or_prompt(line, command):
                continue
            lines.append(line)
    return lines


def _commands_captured(command_results: dict[str, Any], commands: list[str]) -> bool:
    return all(bool(_dict(command_results.get(command)).get("captured")) for command in commands)


def _is_command_echo_or_prompt(line: str, command: str) -> bool:
    text = line.strip()
    if not text:
        return True
    if text.lower() == command.lower():
        return True
    if re.match(r"^[A-Za-z0-9_.()/:-]+[>#]$", text):
        return True
    if text.lower() in {"building configuration...", "current configuration :"}:
        return True
    return False


def _probe_blockers(probe: dict[str, Any]) -> list[str]:
    blockers = [str(item) for item in probe.get("blockers") or [] if str(item)]
    if probe.get("status") != "ok" and not blockers:
        blockers.append("Cisco read-only SSH probe did not complete.")
    command_results = probe.get("command_results") if isinstance(probe.get("command_results"), dict) else {}
    for command in ("show vlan brief", "show interfaces status"):
        result = command_results.get(command) if isinstance(command_results.get(command), dict) else {}
        if not result.get("captured"):
            blockers.append(f"Cisco read-only output missing: {command}.")
    return blockers


def _warnings(probe: dict[str, Any], not_checked: list[dict[str, Any]]) -> list[str]:
    warnings = [str(item) for item in probe.get("warnings") or [] if str(item)]
    warnings.extend(f"{item['area']} not checked: {item['reason']}" for item in not_checked)
    return warnings


def _markdown(payload: dict[str, Any]) -> str:
    diff = _dict(payload.get("diff"))
    lines = [
        "# Cisco Current To Intent Diff",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Source: `{payload.get('source_type')}` / `{payload.get('freshness')}`",
        f"- IOS XE: `{payload.get('version_hint') or 'unknown'}`",
        f"- Drift count: `{diff.get('drift_count')}`",
        "",
        "## VLAN Drift",
        "",
        f"- Missing: `{', '.join(_string_list(_dict(diff.get('vlan')).get('missing'))) or '-'}`",
        f"- Unexpected: `{', '.join(_string_list(_dict(diff.get('vlan')).get('unexpected'))) or '-'}`",
        "",
        "## Port Drift",
        "",
    ]
    port_diff = diff.get("ports") if isinstance(diff.get("ports"), list) else []
    if port_diff:
        for item in port_diff:
            row = _dict(item)
            lines.append(f"- `{row.get('port')}`: {row.get('reason')}")
    else:
        lines.append("- No parsed interface drift found for intended ports.")
    lines.extend(["", "## Guardrails", ""])
    guardrails = _dict(diff.get("guardrails"))
    for area, evidence in guardrails.items():
        row = _dict(evidence)
        missing = ", ".join(_string_list(row.get("missing"))) or "-"
        matched = ", ".join(_string_list(row.get("matched"))) or "-"
        lines.append(f"- `{area}`: `{row.get('status')}`; matched `{matched}`; missing `{missing}`")
    lines.extend(["", "## Not Checked", ""])
    for item in diff.get("not_checked") or []:
        row = _dict(item)
        lines.append(f"- `{row.get('area')}`: {row.get('reason')}")
    candidate = _dict(payload.get("candidate_config_preview"))
    lines.extend(["", "## Candidate Config Preview", ""])
    lines.append(f"- Status: `{candidate.get('status') or 'not_checked'}`")
    lines.append(f"- Summary: {candidate.get('summary') or 'No candidate preview generated.'}")
    commands = _string_list(candidate.get("commands"))
    if commands:
        lines.extend(["", "```text", *commands, "```"])
    notes = _string_list(candidate.get("notes"))
    if notes:
        lines.extend(["", "### Notes"])
        for note in notes:
            lines.append(f"- {note}")
    not_attempted = _string_list(candidate.get("not_attempted"))
    if not_attempted:
        lines.extend(["", "### Not Attempted"])
        for item in not_attempted:
            lines.append(f"- {item}")
    remediation = _dict(payload.get("remediation_plan"))
    lines.extend(["", "## Remediation Plan", ""])
    lines.append(f"- Status: `{remediation.get('status') or 'not_checked'}`")
    lines.append(f"- Summary: {remediation.get('summary') or 'No remediation summary generated.'}")
    steps = remediation.get("steps") if isinstance(remediation.get("steps"), list) else []
    for item in steps:
        row = _dict(item)
        lines.append(
            f"- `{row.get('label')}`: `{row.get('status')}` - {row.get('detail')} Next: {row.get('next_action')}"
        )
    lines.append("")
    return "\n".join(lines)


def _normalize_port(value: str) -> str:
    replacements = {
        "GigabitEthernet": "Gi",
        "TenGigabitEthernet": "Te",
        "TwentyFiveGigE": "Tw",
        "FortyGigabitEthernet": "Fo",
        "HundredGigE": "Hu",
        "Ethernet": "Eth",
        "Port-channel": "Po",
    }
    for long, short in replacements.items():
        if value.startswith(long):
            return value.replace(long, short, 1)
    return value


def _sort_vlan(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 99999


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item)]
    if value:
        return [str(value)]
    return []


def _rel(path: Path) -> str:
    try:
        return repo_relative_path(path, REPO_ROOT)
    except ValueError:
        return str(path)


def _now() -> str:
    return datetime.now(UTC).isoformat()
