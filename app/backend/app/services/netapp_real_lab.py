from __future__ import annotations

import glob
import json
import os
import re
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from shutil import which
from typing import Any

from app.core.config import settings
from app.providers.action_policy import REAL_CONTACT_MODES, current_lab_action_policy
from app.providers.redaction import redact_sensitive
from app.services.serial_console_discovery import (
    SerialConsoleProbeOptions,
    discover_serial_console_candidates,
    probe_serial_candidates,
    selectable_serial_candidates,
    serial_baud_order,
)

PROVIDER_ID = "netapp-ontap"
REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"

CONSOLE_DISCOVERY_REPORT = CODEX_RUN_DIR / "netapp-console-autodiscovery-report.md"
CONSOLE_DISCOVERY_JSON = CODEX_RUN_DIR / "netapp-console-autodiscovery-redacted.json"
CONSOLE_STATE_REPORT = CODEX_RUN_DIR / "netapp-console-state-report.md"
CONSOLE_STATE_JSON = CODEX_RUN_DIR / "netapp-console-state-redacted.json"
NFS_VCENTER_READINESS_REPORT = CODEX_RUN_DIR / "netapp-nfs-vcenter-readiness-report.md"
NFS_VCENTER_READINESS_JSON = CODEX_RUN_DIR / "netapp-nfs-vcenter-readiness-redacted.json"

CONSOLE_GLOBS = (
    "/dev/serial/by-id/*",
    "/dev/ttyUSB*",
    "/dev/ttyACM*",
)
USB_SERIAL_NAME_HINTS = (
    "NetApp",
    "MCP2221",
    "Microchip",
    "FTDI",
    "Prolific",
    "Silicon_Labs",
    "CP210",
    "USB-Serial",
)
COMMON_NETAPP_CONSOLE_BAUDS = (115200, 9600, 19200, 38400, 57600)
VALID_NETAPP_STATES = {
    "loader_prompt",
    "boot_menu",
    "cluster_setup_prompt",
    "existing_cluster_shell",
    "login_required",
    "password_required",
    "booting",
    "sp_bmc_login",
}
NETAPP_SERIAL_WAKE_SEQUENCES = (
    ("newline", b"\n"),
    ("carriage-return", b"\r"),
)
NETAPP_MAX_PROBE_CANDIDATES = 4
NOT_ATTEMPTED = [
    "Ctrl+C, Ctrl+Z, break, boot menu selection, or any boot interruption",
    "username or password entry",
    "cluster setup commands",
    "SP, node, SVM, LIF, volume, export, or datastore creation",
    "ONTAP API write",
    "vCenter or ESXi datastore mount",
    "controller reboot, takeover/giveback, wipe, or upgrade",
]


@dataclass(frozen=True)
class NetAppConsoleCandidate:
    path: str
    stable_path: bool
    exists: bool
    readable: bool | None
    writable: bool | None
    label: str | None
    target_path: str | None
    in_use: bool
    rank: int
    recommendation: str


def get_latest_netapp_console_discovery() -> dict[str, Any]:
    return _latest_or_not_run(
        CONSOLE_DISCOVERY_JSON,
        action="console-discovery",
        message="NetApp console discovery has not run yet.",
        next_safe_action="Run `make provider-lab-netapp-console-autodiscovery`.",
    )


def get_latest_netapp_console_state() -> dict[str, Any]:
    return _latest_or_not_run(
        CONSOLE_STATE_JSON,
        action="console-read-state",
        message="NetApp console read-state has not run yet.",
        next_safe_action="Run `make provider-lab-netapp-console-read-state` after console cables are connected.",
    )


def run_netapp_console_discovery() -> dict[str, Any]:
    return _run_console_probe(
        action="console-discovery",
        report_path=CONSOLE_DISCOVERY_REPORT,
        json_path=CONSOLE_DISCOVERY_JSON,
        message="NetApp console discovery completed.",
    )


def run_netapp_console_read_state() -> dict[str, Any]:
    return _run_console_probe(
        action="console-read-state",
        report_path=CONSOLE_STATE_REPORT,
        json_path=CONSOLE_STATE_JSON,
        message="NetApp console state read completed.",
    )


def get_netapp_nfs_vcenter_readiness(*, check_ports: bool | None = None, write_report: bool = True) -> dict[str, Any]:
    if check_ports is None:
        check_ports = settings.provider_mode in REAL_CONTACT_MODES
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    checked_at = _now()
    nfs_lifs = list(settings.netapp_nfs_lifs)
    first_nfs_lif = nfs_lifs[0] if nfs_lifs else settings.netapp_svm_mgmt_ip
    connected_management_ports = list(settings.netapp_connected_management_ports)
    single_management_port = len(connected_management_ports) <= 1
    netapp_credentials_present = bool(settings.netapp_api_username and settings.netapp_api_password)
    vcenter_credentials_present = bool(settings.vcenter_username and settings.vcenter_password)
    govc_available = which("govc") is not None
    netapp_api_configured = bool(settings.netapp_configured and settings.netapp_cluster_mgmt_ip)
    vcenter_configured = bool(settings.vcenter_configured and settings.vcenter_host)
    esxi_configured = bool(settings.esxi_configured and settings.esxi_test_host)

    connectivity = {
        "netapp_cluster_rest_443": _tcp_check(
            settings.netapp_cluster_mgmt_ip,
            443,
            enabled=bool(check_ports and netapp_api_configured),
            disabled_reason=(
                "NETAPP_CONFIGURED=false; cluster management REST is planned but not live."
                if not settings.netapp_configured
                else "Port checks disabled for this run."
            ),
        ),
        "netapp_cluster_ssh_22": _tcp_check(
            settings.netapp_cluster_mgmt_ip,
            22,
            enabled=bool(check_ports and netapp_api_configured),
            disabled_reason=(
                "NETAPP_CONFIGURED=false; cluster management SSH is planned but not live."
                if not settings.netapp_configured
                else "Port checks disabled for this run."
            ),
        ),
        "vcenter_443": _tcp_check(
            _host_from_url(settings.vcenter_host),
            443,
            enabled=bool(check_ports and vcenter_configured),
            disabled_reason=(
                "VCENTER_CONFIGURED=false or VCENTER_HOST/GOVC_URL is missing."
                if not vcenter_configured
                else "Port checks disabled for this run."
            ),
        ),
        "esxi_api_443": _tcp_check(
            settings.esxi_test_host,
            443,
            enabled=bool(check_ports and esxi_configured),
            disabled_reason=(
                "ESXI_CONFIGURED=false or ESXI_TEST_HOST is missing."
                if not esxi_configured
                else "Port checks disabled for this run."
            ),
        ),
        "planned_nfs_lifs_2049": [
            _tcp_check(
                lif,
                2049,
                enabled=bool(check_ports and netapp_api_configured),
                disabled_reason=(
                    "NFS LIFs are planned only until NetApp setup creates/confirms data LIFs."
                    if not settings.netapp_configured
                    else "Port checks disabled for this run."
                ),
            )
            for lif in nfs_lifs
        ],
    }

    blockers = []
    if not settings.netapp_configured:
        blockers.append("NETAPP_CONFIGURED=false; ONTAP REST/NFS setup is not ready for live validation.")
    if not netapp_credentials_present:
        blockers.append("NetApp API credentials are missing; values must stay in .env.local.real-lab when ready.")
    if not esxi_configured:
        blockers.append("ESXi management is not configured yet; NFS datastore mount validation is blocked.")
    if not vcenter_configured:
        blockers.append("vCenter/govc target is not configured yet; vCenter datastore validation is blocked.")
    if vcenter_configured and not vcenter_credentials_present:
        blockers.append("vCenter credentials are missing; values must stay in .env.local.real-lab when ready.")
    if vcenter_configured and not govc_available:
        blockers.append("govc is not installed or not on PATH; vCenter validation cannot run.")

    warnings = [
        "Only one NetApp management path is connected; this is acceptable for initial console/API bring-up but not full HA validation."
        if single_management_port
        else "Multiple NetApp management paths are listed as connected.",
        "NFS/vCenter readiness is preview-only. No ONTAP, vCenter, ESXi, or storage apply action is run.",
    ]
    if settings.netapp_storage_protocol.lower() != "nfs":
        warnings.append(f"NETAPP_STORAGE_PROTOCOL={settings.netapp_storage_protocol} is set; this readiness pass is for NFS.")

    payload = {
        "provider_id": PROVIDER_ID,
        "action": "nfs-vcenter-readiness",
        "checked_at": checked_at,
        "status": "blocked" if blockers else "ready",
        "message": (
            "NetApp NFS/vCenter readiness generated. Preview only; no changes were made."
        ),
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "ontap_apply_enabled": False,
        "vcenter_apply_enabled": False,
        "esxi_apply_enabled": False,
        "single_management_port_mode": single_management_port,
        "management_topology": {
            "connected_management_ports": connected_management_ports,
            "note": settings.netapp_management_topology_note,
            "initial_bringup_ok": True,
            "full_ha_validation_ready": not single_management_port,
        },
        "planned_nfs": {
            "storage_protocol": settings.netapp_storage_protocol,
            "svm_management_ip": settings.netapp_svm_mgmt_ip,
            "nfs_lifs": nfs_lifs,
            "volume": settings.netapp_nfs_volume,
            "export_policy": settings.netapp_nfs_export_policy,
            "mount_path": settings.netapp_nfs_mount_path,
            "datastore_name": settings.netapp_nfs_datastore_name,
            "client_match": settings.netapp_nfs_client_match,
        },
        "targets": {
            "netapp_cluster_mgmt_ip": settings.netapp_cluster_mgmt_ip,
            "esxi_management_ip": settings.esxi_test_host,
            "vcenter_host_configured": bool(settings.vcenter_host),
            "vcenter_configured": settings.vcenter_configured,
            "govc_available": govc_available,
        },
        "connectivity": connectivity,
        "plan_preview": {
            "ontap_steps": [
                "Confirm cluster management REST is reachable.",
                "Confirm or create the target SVM.",
                "Confirm or create NFS data LIFs on the connected data path.",
                "Enable or confirm NFS service on the SVM.",
                "Confirm or create the ESXi datastore volume.",
                "Confirm or create export policy and rule for the ESXi management/client network.",
            ],
            "vcenter_steps": [
                "Use govc after vCenter is reachable and credentials are configured.",
                "Add or confirm the NFS datastore against the intended ESXi host or cluster.",
                "Validate datastore visibility from ESXi/vCenter.",
            ],
            "govc_preview": (
                "govc datastore.create -type nfs "
                f"-name {settings.netapp_nfs_datastore_name} "
                f"-remote-host {first_nfs_lif} "
                f"-remote-path {settings.netapp_nfs_mount_path}"
            ),
            "esxi_fallback_preview": (
                "esxcli storage nfs add "
                f"-H {first_nfs_lif} "
                f"-s {settings.netapp_nfs_mount_path} "
                f"-v {settings.netapp_nfs_datastore_name}"
            ),
        },
        "artifacts": {
            "report": _rel(NFS_VCENTER_READINESS_REPORT),
            "json": _rel(NFS_VCENTER_READINESS_JSON),
        },
        "warnings": warnings,
        "blockers": blockers,
        "not_attempted": NOT_ATTEMPTED,
        "next_safe_action": (
            "Use console/API read-only discovery to identify the NetApp state, then configure vCenter/govc before NFS datastore apply is implemented."
            if blockers
            else "Review the preview and keep apply disabled until an explicit NetApp NFS apply workflow is added."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_json(NFS_VCENTER_READINESS_JSON, sanitized)
        NFS_VCENTER_READINESS_REPORT.write_text(_nfs_vcenter_markdown(sanitized), encoding="utf-8")
    return sanitized


def _run_console_probe(
    *,
    action: str,
    report_path: Path,
    json_path: Path,
    message: str,
) -> dict[str, Any]:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    checked_at = _now()
    candidates = discover_serial_console_candidates(
        configured_hint=settings.netapp_console_port,
        collect_details=True,
        device_hint="netapp",
    )
    candidate_selection = _best_ranked_candidate(candidates)
    policy = current_lab_action_policy(settings.provider_mode)
    policy_blockers = policy.readonly_blockers() if settings.provider_mode in REAL_CONTACT_MODES else [
        "PROVIDER_MODE=local-readonly or PROVIDER_MODE=local-lab-readwrite is required before opening a real NetApp console."
    ]
    warnings = [
        "Only newline and carriage return wake bytes are allowed for this NetApp console probe.",
        "No NetApp credentials, commands, boot interrupts, or configuration actions are sent.",
        "Serial auto-discovery includes /dev/serial/by-id/*, /dev/ttyUSB*, /dev/ttyACM*, and /dev/ttyS*.",
    ]
    if settings.netapp_console_port and not any(
        candidate.get("display_path") == settings.netapp_console_port for candidate in candidates
    ):
        warnings.append("Configured NETAPP_CONSOLE_PORT was treated as a hint but is not present in discovered candidates.")
    if len(settings.netapp_connected_management_ports) <= 1:
        warnings.append(settings.netapp_management_topology_note)

    attempts: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    blockers = list(policy_blockers)
    serial_import_error: str | None = None
    serial_module: Any | None = None
    if not policy_blockers:
        try:
            import serial  # type: ignore[import-untyped]

            serial_module = serial
        except ImportError:
            serial_import_error = "pyserial is not installed; real NetApp console workflow cannot open serial."
            blockers.append(serial_import_error)

    baud_rates = serial_baud_order(settings.netapp_console_baud)
    if not blockers and serial_module is not None:
        selectable = selectable_serial_candidates(candidates)
        if not selectable:
            if candidates:
                blockers.append(
                    "NetApp console candidates were found, but none were selectable. Fix device permissions or close the process using the adapter."
                )
            else:
                blockers.append(
                    "No OS-visible serial console candidates were found at /dev/serial/by-id/*, /dev/ttyUSB*, /dev/ttyACM*, or /dev/ttyS*."
                )
        probe_result = probe_serial_candidates(
            serial_module,
            candidates,
            options=SerialConsoleProbeOptions(
                configured_baud=settings.netapp_console_baud,
                timeout_seconds=settings.netapp_console_timeout_seconds,
                device_hint="netapp",
                max_candidates=NETAPP_MAX_PROBE_CANDIDATES,
                wake_sequences=NETAPP_SERIAL_WAKE_SEQUENCES,
            ),
        )
        attempts = list(probe_result["attempts"])
        probed_candidate_count = int(probe_result.get("probed_candidate_count") or 0)
        skipped_candidate_count = int(probe_result.get("skipped_candidate_count") or 0)
        prompt_attempt = _netapp_prompt_attempt(probe_result.get("selected"), attempts)
        if prompt_attempt:
            candidate = _candidate_for_attempt(candidates, prompt_attempt)
            selected = _selection_from_prompt_attempt(candidate, prompt_attempt)
    else:
        probed_candidate_count = 0
        skipped_candidate_count = 0

    if selected is None and candidate_selection is not None:
        selected = _selection_from_candidate(candidate_selection, attempts)

    prompt_selected = bool(selected and selected.get("prompt_state") in VALID_NETAPP_STATES)
    if prompt_selected:
        status = "ready"
        blockers = []
        message = f"{message} NetApp console produced {selected['prompt_label']}."
    else:
        status = "blocked"
        if not blockers:
            blockers.append(
                "Serial candidates were discovered, but no valid NetApp prompt, boot state, or login flow was detected."
            )

    payload = {
        "provider_id": PROVIDER_ID,
        "action": action,
        "checked_at": checked_at,
        "status": status,
        "message": (
            message
            if prompt_selected
            else "NetApp console autodiscovery selected a serial candidate, but no usable NetApp prompt/state was detected."
            if selected
            else "NetApp console discovery did not identify a usable serial candidate or prompt/state."
        ),
        "mode": settings.provider_mode,
        "configured_port_hint": settings.netapp_console_port,
        "selected_port": selected["path"] if selected else None,
        "selected_baud": selected["baud"] if selected else None,
        "selected_prompt_state": selected["prompt_state"] if selected else None,
        "selected_prompt_label": selected["prompt_label"] if selected else None,
        "selection_source": selected["selection_source"] if selected else None,
        "selection_confidence": selected["confidence"] if selected else None,
        "selection_reason": selected["selection_reason"] if selected else None,
        "selected_device_type": selected["device_type"] if selected else None,
        "selected_classification": selected["classification"] if selected else None,
        "prompt_detected": prompt_selected,
        "candidate_count": len(candidates),
        "selectable_candidate_count": len(selectable_serial_candidates(candidates)),
        "probed_candidate_count": probed_candidate_count,
        "skipped_candidate_count": skipped_candidate_count,
        "candidate_counts": _candidate_counts(candidates),
        "candidates": candidates,
        "bauds_tried": list(baud_rates),
        "attempt_count": len(attempts),
        "attempts": attempts,
        "last_console_blocker": blockers[-1] if blockers else None,
        "serial_import_error": serial_import_error,
        "management_topology": {
            "connected_management_ports": list(settings.netapp_connected_management_ports),
            "note": settings.netapp_management_topology_note,
        },
        "artifacts": {"report": _rel(report_path), "json": _rel(json_path)},
        "warnings": warnings,
        "blockers": blockers,
        "not_attempted": NOT_ATTEMPTED,
        "next_safe_action": (
            "Use the selected console adapter/baud for read-only NetApp state capture."
            if prompt_selected
            else "Use the selected candidate as the next physical console check, then verify cable placement, adapter ownership, power state, and baud before rerunning discovery."
            if selected
            else "Check console cable, adapter ownership, backend device permissions, and baud, then rerun discovery."
        ),
    }
    sanitized = _sanitize(payload)
    _write_json(json_path, sanitized)
    report_path.write_text(_console_markdown(sanitized), encoding="utf-8")
    return sanitized


def _best_ranked_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    selectable = selectable_serial_candidates(candidates)
    if selectable:
        return selectable[0]
    existing = [candidate for candidate in candidates if candidate.get("exists")]
    return existing[0] if existing else (candidates[0] if candidates else None)


def _candidate_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    existing = [candidate for candidate in candidates if candidate.get("exists")]
    return {
        "total": len(candidates),
        "existing": len(existing),
        "selectable": len(selectable_serial_candidates(candidates)),
        "stable_existing": len([candidate for candidate in existing if candidate.get("stable_path")]),
        "usb_existing": len(
            [
                candidate
                for candidate in existing
                if candidate.get("path_type") in {"by-id", "ttyUSB", "ttyACM"}
            ]
        ),
        "ttys_existing": len([candidate for candidate in existing if candidate.get("path_type") == "ttyS"]),
        "in_use": len([candidate for candidate in existing if candidate.get("in_use")]),
        "inaccessible": len(
            [
                candidate
                for candidate in existing
                if not candidate.get("readable") or not candidate.get("writable")
            ]
        ),
    }


def _netapp_prompt_attempt(
    selected_attempt: object,
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if isinstance(selected_attempt, dict) and selected_attempt.get("prompt_state") in VALID_NETAPP_STATES:
        return selected_attempt
    return next(
        (
            attempt
            for attempt in attempts
            if attempt.get("prompt_state") in VALID_NETAPP_STATES
            and attempt.get("device_type") == "netapp"
        ),
        None,
    )


def _candidate_for_attempt(
    candidates: list[dict[str, Any]],
    attempt: dict[str, Any],
) -> dict[str, Any] | None:
    path = attempt.get("path")
    if not isinstance(path, str):
        return None
    return next(
        (
            candidate
            for candidate in candidates
            if candidate.get("display_path") == path or candidate.get("path") == path
        ),
        None,
    )


def _selection_from_prompt_attempt(
    candidate: dict[str, Any] | None,
    attempt: dict[str, Any],
) -> dict[str, Any]:
    detail = attempt.get("classification_detail") if isinstance(attempt.get("classification_detail"), dict) else {}
    signals = detail.get("signals") if isinstance(detail.get("signals"), list) else []
    return {
        "path": str((candidate or {}).get("display_path") or attempt.get("path")),
        "baud": attempt.get("baud"),
        "prompt_state": attempt.get("prompt_state"),
        "prompt_label": attempt.get("prompt_label"),
        "selection_source": "prompt-evidence",
        "output_excerpt": attempt.get("output_excerpt") or "",
        "confidence": detail.get("confidence") or (candidate or {}).get("confidence") or "medium",
        "selection_reason": "; ".join(str(signal) for signal in signals)
        or _candidate_reason(candidate)
        or "NetApp prompt evidence matched this serial candidate.",
        "device_type": attempt.get("device_type"),
        "classification": attempt.get("classification"),
    }


def _selection_from_candidate(
    candidate: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    attempt = _best_attempt_for_candidate(candidate, attempts)
    return {
        "path": str(candidate.get("display_path") or candidate.get("path")),
        "baud": attempt.get("baud") if attempt else None,
        "prompt_state": attempt.get("prompt_state") if attempt else None,
        "prompt_label": attempt.get("prompt_label") if attempt else "Candidate selected by OS evidence",
        "selection_source": _selection_source_from_candidate(candidate),
        "output_excerpt": attempt.get("output_excerpt") if attempt else "",
        "confidence": candidate.get("confidence") or "low",
        "selection_reason": _candidate_reason(candidate)
        or "Highest-ranked selectable serial candidate from OS discovery.",
        "device_type": attempt.get("device_type") if attempt else None,
        "classification": attempt.get("classification") if attempt else None,
    }


def _best_attempt_for_candidate(
    candidate: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    path = str(candidate.get("display_path") or candidate.get("path") or "")
    matching = [attempt for attempt in attempts if attempt.get("path") == path]
    captured = [attempt for attempt in matching if attempt.get("captured")]
    return (captured or matching or [None])[0]


def _selection_source_from_candidate(candidate: dict[str, Any]) -> str:
    if settings.netapp_console_port and candidate.get("display_path") == settings.netapp_console_port:
        return "configured-port-hint"
    if candidate.get("stable_path"):
        return "auto-stable-candidate"
    if candidate.get("path_type") == "ttyS":
        return "auto-ttys-candidate"
    return "auto-fallback-candidate"


def _candidate_reason(candidate: dict[str, Any] | None) -> str:
    if not candidate:
        return ""
    reasons = candidate.get("selection_reasons")
    if isinstance(reasons, list) and reasons:
        return "; ".join(str(reason) for reason in reasons)
    return str(candidate.get("recommendation") or "")


def _discover_console_candidates() -> list[NetAppConsoleCandidate]:
    paths: list[str] = []
    if settings.netapp_console_port:
        paths.append(settings.netapp_console_port)
    for pattern in CONSOLE_GLOBS:
        paths.extend(glob.glob(pattern))
    deduped = list(dict.fromkeys(paths))
    return [_candidate(path) for path in deduped]


def _candidate(path: str) -> NetAppConsoleCandidate:
    path_obj = Path(path)
    exists = path_obj.exists()
    stable_path = path.startswith("/dev/serial/by-id/")
    readable = os.access(path, os.R_OK) if exists else False
    writable = os.access(path, os.W_OK) if exists else False
    target_path = str(path_obj.resolve(strict=False)) if exists else None
    label = path_obj.name if path_obj.name else path
    in_use = _path_in_use(path) if exists else False
    rank = _candidate_rank(
        path=path,
        stable_path=stable_path,
        exists=exists,
        readable=readable,
        writable=writable,
        in_use=in_use,
    )
    return NetAppConsoleCandidate(
        path=path,
        stable_path=stable_path,
        exists=exists,
        readable=readable,
        writable=writable,
        label=label,
        target_path=target_path,
        in_use=in_use,
        rank=rank,
        recommendation=_candidate_recommendation(
            path=path,
            stable_path=stable_path,
            exists=exists,
            readable=readable,
            writable=writable,
            in_use=in_use,
        ),
    )


def _candidate_rank(
    *,
    path: str,
    stable_path: bool,
    exists: bool,
    readable: bool,
    writable: bool,
    in_use: bool,
) -> int:
    rank = 0
    if settings.netapp_console_port and path == settings.netapp_console_port:
        rank -= 1000
    if stable_path:
        rank -= 200
    if _name_has_usb_hint(path):
        rank -= 100
    if not exists:
        rank += 500
    if not readable or not writable:
        rank += 300
    if in_use:
        rank += 250
    return rank


def _rank_candidates(candidates: list[NetAppConsoleCandidate]) -> list[NetAppConsoleCandidate]:
    return sorted(candidates, key=lambda candidate: (candidate.rank, candidate.path))


def _candidate_recommendation(
    *,
    path: str,
    stable_path: bool,
    exists: bool,
    readable: bool,
    writable: bool,
    in_use: bool,
) -> str:
    if settings.netapp_console_port and path == settings.netapp_console_port:
        return "configured-port-hint"
    if not exists:
        return "missing"
    if not readable or not writable:
        return "permission-blocked"
    if in_use:
        return "in-use"
    if stable_path:
        return "preferred-stable-path"
    if _name_has_usb_hint(path):
        return "usb-serial-name-match"
    return "fallback-serial-candidate"


def _candidate_selectable(candidate: NetAppConsoleCandidate) -> bool:
    return bool(candidate.exists and candidate.readable and candidate.writable and not candidate.in_use)


def _selection_source(candidate: NetAppConsoleCandidate) -> str:
    if settings.netapp_console_port and candidate.path == settings.netapp_console_port:
        return "configured-port-hint"
    if candidate.stable_path:
        return "auto-stable-candidate"
    return "auto-fallback-candidate"


def _name_has_usb_hint(path: str) -> bool:
    lowered = path.lower()
    return any(hint.lower() in lowered for hint in USB_SERIAL_NAME_HINTS)


def _path_in_use(path: str) -> bool:
    for command in (["fuser", "-s", path], ["lsof", "-t", path]):
        executable = which(command[0])
        if executable is None:
            continue
        try:
            result = subprocess.run(
                [executable, *command[1:]],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=1.0,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            return True
    return False


def _baud_order(first_baud: int | None) -> tuple[int, ...]:
    values = [first_baud, *COMMON_NETAPP_CONSOLE_BAUDS] if first_baud else list(COMMON_NETAPP_CONSOLE_BAUDS)
    return tuple(dict.fromkeys(int(value) for value in values if value))


def _probe_candidate(serial_module: Any, candidate: NetAppConsoleCandidate, baud: int) -> dict[str, Any]:
    started_at = _now()
    try:
        with serial_module.Serial(
            port=candidate.path,
            baudrate=baud,
            timeout=0.35,
            write_timeout=0.5,
        ) as conn:
            _safe_reset_input(conn)
            conn.write(b"\r\n")
            _safe_flush(conn)
            text = _read_serial(conn, window=settings.netapp_console_timeout_seconds)
            classification = _classify_netapp_console(text)
            return {
                "path": candidate.path,
                "baud": baud,
                "started_at": started_at,
                "status": "ready" if classification["state"] in VALID_NETAPP_STATES else "unknown",
                "bytes": len(text.encode("utf-8", errors="replace")),
                "captured": bool(text),
                "prompt_state": classification["state"],
                "prompt_label": classification["label"],
                "output_excerpt": _printable_excerpt(text),
                "blocker": None
                if classification["state"] in VALID_NETAPP_STATES
                else "No valid NetApp prompt/state detected at this path and baud.",
            }
    except Exception as exc:  # pragma: no cover - hardware dependent
        return {
            "path": candidate.path,
            "baud": baud,
            "started_at": started_at,
            "status": "blocked",
            "bytes": 0,
            "captured": False,
            "prompt_state": _serial_error_state(exc),
            "prompt_label": _serial_error_label(exc),
            "output_excerpt": "",
            "blocker": _serial_error_summary(exc),
        }


def _safe_reset_input(conn: Any) -> None:
    try:
        conn.reset_input_buffer()
    except Exception:
        return


def _safe_flush(conn: Any) -> None:
    try:
        conn.flush()
    except Exception:
        return


def _read_serial(conn: Any, *, window: float) -> str:
    deadline = time.monotonic() + max(window, 0.25)
    chunks: list[bytes] = []
    while time.monotonic() < deadline:
        try:
            waiting = int(getattr(conn, "in_waiting", 0) or 0)
            chunk = conn.read(waiting or 1)
        except Exception:
            break
        if chunk:
            chunks.append(chunk)
            if sum(len(item) for item in chunks) >= 8192:
                break
        else:
            time.sleep(0.05)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _classify_netapp_console(text: str) -> dict[str, str]:
    if not text:
        return {"state": "no_output", "label": "No console output"}
    if text.count("\ufffd") > max(2, len(text) // 10):
        return {"state": "unreadable", "label": "Unreadable console text"}
    lower = text.lower()
    if re.search(r"(?im)(?:^|\n|\r)loader[-_a-z0-9]*>\s*$", text) or "loader>" in lower:
        return {"state": "loader_prompt", "label": "LOADER prompt"}
    if "boot menu" in lower or ("selection" in lower and "wipeconfig" in lower):
        return {"state": "boot_menu", "label": "Boot menu"}
    if "cluster setup" in lower or "initial configuration dialog" in lower:
        return {"state": "cluster_setup_prompt", "label": "Cluster setup prompt"}
    if re.search(r"(?m)[A-Za-z0-9_.:-]+::\*?>\s*$", text):
        return {"state": "existing_cluster_shell", "label": "Existing ONTAP cluster shell"}
    if "username:" in lower or "login:" in lower:
        return {"state": "login_required", "label": "Login prompt"}
    if "password:" in lower:
        return {"state": "password_required", "label": "Password prompt"}
    if "press ctrl-c" in lower or "booting" in lower or "starting ontap" in lower:
        return {"state": "booting", "label": "ONTAP booting"}
    return {"state": "unknown_output", "label": "Unclassified console output"}


def _printable_excerpt(text: str, *, max_chars: int = 1600) -> str:
    if not text:
        return ""
    printable = "".join(ch if ch in "\n\r\t" or 32 <= ord(ch) <= 126 else "." for ch in text)
    lines = [line.rstrip() for line in printable.replace("\r", "\n").splitlines()]
    compact = "\n".join(line for line in lines if line.strip())
    return compact[:max_chars]


def _serial_error_state(exc: Exception) -> str:
    message = str(exc).lower()
    if "permission" in message:
        return "permission_denied"
    if "resource busy" in message or "device or resource busy" in message:
        return "port_in_use"
    if "no such file" in message or "could not open port" in message:
        return "missing_port"
    return "serial_open_failed"


def _serial_error_label(exc: Exception) -> str:
    return {
        "permission_denied": "Permission denied",
        "port_in_use": "Port in use",
        "missing_port": "Missing serial port",
        "serial_open_failed": "Serial open failed",
    }[_serial_error_state(exc)]


def _serial_error_summary(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {str(exc)[:180]}"


def _tcp_check(host: str | None, port: int, *, enabled: bool, disabled_reason: str) -> dict[str, Any]:
    if not host:
        return {
            "host": host,
            "port": port,
            "enabled": False,
            "reachable": None,
            "status": "missing-host",
            "reason": "Host is not configured.",
        }
    if not enabled:
        return {
            "host": host,
            "port": port,
            "enabled": False,
            "reachable": None,
            "status": "not-probed",
            "reason": disabled_reason,
        }
    try:
        with socket.create_connection((host, port), timeout=2.5):
            return {"host": host, "port": port, "enabled": True, "reachable": True, "status": "ready"}
    except OSError as exc:
        return {
            "host": host,
            "port": port,
            "enabled": True,
            "reachable": False,
            "status": "blocked",
            "reason": f"{exc.__class__.__name__}: {str(exc)[:140]}",
        }


def _host_from_url(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    cleaned = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", cleaned)
    if "@" in cleaned:
        cleaned = cleaned.rsplit("@", 1)[-1]
    cleaned = cleaned.split("/", 1)[0]
    return cleaned.split(":", 1)[0] or None


def _latest_or_not_run(path: Path, *, action: str, message: str, next_safe_action: str) -> dict[str, Any]:
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except (OSError, ValueError):
            pass
    return {
        "provider_id": PROVIDER_ID,
        "action": action,
        "checked_at": None,
        "status": "not_run",
        "message": message,
        "mode": settings.provider_mode,
        "configured_port_hint": settings.netapp_console_port,
        "selected_port": None,
        "selected_baud": None,
        "candidate_count": 0,
        "last_console_blocker": "No report has been generated yet.",
        "artifacts": {"report": _rel(_report_for_action(action))},
        "warnings": [],
        "blockers": [message],
        "next_safe_action": next_safe_action,
    }


def _report_for_action(action: str) -> Path:
    if action == "console-read-state":
        return CONSOLE_STATE_REPORT
    return CONSOLE_DISCOVERY_REPORT


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive(payload, _redaction_values())


def _redaction_values() -> list[str]:
    values: list[str] = []
    for key, value in os.environ.items():
        if not value:
            continue
        if any(fragment in key.lower() for fragment in ("password", "token", "secret", "credential", "authorization", "cookie")):
            values.append(value)
    return values


def _console_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# NetApp Console Discovery",
        "",
        f"Checked at: {payload['checked_at']}",
        f"Action: `{payload['action']}`",
        f"Status: `{payload['status']}`",
        f"Provider mode: `{payload['mode']}`",
        "",
        "## Selection",
        f"- Configured port hint: `{payload.get('configured_port_hint') or 'not set'}`",
        f"- Selected port: `{payload.get('selected_port') or 'none'}`",
        f"- Selected baud: `{payload.get('selected_baud') or 'none'}`",
        f"- Prompt/state: `{payload.get('selected_prompt_label') or 'not detected'}`",
        f"- Prompt detected: `{payload.get('prompt_detected')}`",
        f"- Selection confidence: `{payload.get('selection_confidence') or 'none'}`",
        f"- Selection source: `{payload.get('selection_source') or 'none'}`",
        f"- Selection reason: {payload.get('selection_reason') or 'none'}",
        f"- Candidate count: `{payload.get('candidate_count', 0)}`",
        f"- Selectable candidates: `{payload.get('selectable_candidate_count', 0)}`",
        f"- Probed candidates: `{payload.get('probed_candidate_count', 0)}`",
        f"- Skipped candidates: `{payload.get('skipped_candidate_count', 0)}`",
        f"- Attempt count: `{payload.get('attempt_count', 0)}`",
        f"- Last console blocker: `{payload.get('last_console_blocker') or 'none'}`",
        "",
        "## Candidate Summary",
    ]
    candidates = payload.get("candidates") or []
    if candidates:
        for candidate in candidates[:40]:
            if not isinstance(candidate, dict):
                continue
            lines.append(
                "- "
                f"`{candidate.get('display_path') or candidate.get('path')}` | "
                f"type=`{candidate.get('path_type')}` | exists=`{candidate.get('exists')}` | "
                f"rw=`{candidate.get('readable')}/{candidate.get('writable')}` | "
                f"in_use=`{candidate.get('in_use')}` | mtime=`{candidate.get('modified_time') or 'unknown'}` | "
                f"rank=`{candidate.get('rank')}` | confidence=`{candidate.get('confidence')}` | "
                f"reason={'; '.join(str(item) for item in candidate.get('selection_reasons', [])[:3])}"
            )
    else:
        lines.append("- No serial candidates were discovered.")
    lines.extend(
        [
            "",
            "## Management Topology",
            f"- Connected management ports: `{', '.join(payload.get('management_topology', {}).get('connected_management_ports', [])) or 'none listed'}`",
            f"- Note: {payload.get('management_topology', {}).get('note') or 'none'}",
            "",
            "## Attempts",
        ]
    )
    attempts = payload.get("attempts") or []
    if attempts:
        for attempt in attempts:
            lines.append(
                f"- `{attempt.get('path')}` @ `{attempt.get('baud')}`: "
                f"{attempt.get('prompt_label')} ({attempt.get('status')})"
            )
    else:
        lines.append("- No serial open/read attempts were made.")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers", []) or ["None"])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in payload.get("warnings", []) or ["None"])
    lines.extend(["", "## Not Attempted"])
    lines.extend(f"- {item}" for item in payload.get("not_attempted", []))
    lines.append("")
    return "\n".join(lines)


def _nfs_vcenter_markdown(payload: dict[str, Any]) -> str:
    nfs = payload["planned_nfs"]
    targets = payload["targets"]
    lines = [
        "# NetApp NFS / vCenter Readiness",
        "",
        f"Checked at: {payload['checked_at']}",
        f"Status: `{payload['status']}`",
        f"Provider mode: `{payload['mode']}`",
        f"Apply enabled: `{payload['apply_enabled']}`",
        "",
        "## Management Topology",
        f"- Single management port mode: `{payload['single_management_port_mode']}`",
        f"- Connected management ports: `{', '.join(payload['management_topology']['connected_management_ports']) or 'none listed'}`",
        f"- Note: {payload['management_topology']['note']}",
        "",
        "## Planned NFS",
        f"- SVM management IP: `{nfs['svm_management_ip']}`",
        f"- NFS LIFs: `{', '.join(nfs['nfs_lifs'])}`",
        f"- Volume: `{nfs['volume']}`",
        f"- Export policy: `{nfs['export_policy']}`",
        f"- Mount path: `{nfs['mount_path']}`",
        f"- Datastore: `{nfs['datastore_name']}`",
        f"- Client match: `{nfs['client_match']}`",
        "",
        "## Tool / Target State",
        f"- NetApp cluster management: `{targets['netapp_cluster_mgmt_ip']}`",
        f"- ESXi management: `{targets.get('esxi_management_ip') or 'not configured'}`",
        f"- vCenter configured: `{targets['vcenter_configured']}`",
        f"- govc available: `{targets['govc_available']}`",
        "",
        "## Preview Commands",
        f"- `{payload['plan_preview']['govc_preview']}`",
        f"- `{payload['plan_preview']['esxi_fallback_preview']}`",
        "",
        "## Blockers",
    ]
    lines.extend(f"- {item}" for item in payload.get("blockers", []) or ["None"])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in payload.get("warnings", []) or ["None"])
    lines.extend(["", "## Not Attempted"])
    lines.extend(f"- {item}" for item in payload.get("not_attempted", []))
    lines.append("")
    return "\n".join(lines)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _now() -> str:
    return datetime.now(UTC).isoformat()
