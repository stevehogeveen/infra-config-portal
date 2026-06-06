from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.providers.action_policy import ActionCategory, current_lab_action_policy
from app.providers.redaction import redact_sensitive
from app.services.firmware_compliance import firmware_gate_blockers
from app.services.hpe_raid import (
    REPO_ROOT,
    SYSTEM_PATH,
    _base_url,
    _get_redfish_resource,
    _post_system_reset,
    _response_summary,
)

CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
MEDIA_URL_REPORT = CODEX_RUN_DIR / "esxi-media-url-report.md"
VIRTUAL_MEDIA_REPORT = CODEX_RUN_DIR / "esxi-virtual-media-report.md"
ONE_TIME_BOOT_REPORT = CODEX_RUN_DIR / "esxi-one-time-boot-report.md"
INSTALLER_BOOT_REPORT = CODEX_RUN_DIR / "esxi-installer-boot-report.md"
MEDIA_SERVER_PID = CODEX_RUN_DIR / "esxi-media-http-server.pid"
MEDIA_SERVER_LOG = CODEX_RUN_DIR / "esxi-media-http-server.log"
BOOT_SETTINGS_BEFORE = CODEX_RUN_DIR / "esxi-one-time-boot-before.json"
BOOT_SETTINGS_AFTER = CODEX_RUN_DIR / "esxi-one-time-boot-after.json"
VIRTUAL_MEDIA_STATE = CODEX_RUN_DIR / "esxi-virtual-media-state.json"

DEFAULT_MEDIA_PORT = 8088
PREFERRED_ISO_MARKERS = ("8.0.3", "803", "oct2025")
RESET_TYPE = "ForceRestart"


def prepare_esxi_media_url() -> dict[str, Any]:
    gate_blockers = firmware_gate_blockers("ESXi install media preparation")
    if gate_blockers:
        return _write_report(
            MEDIA_URL_REPORT,
            "ESXi Media URL Report",
            {
                "status": "blocked",
                "message": "ESXi media preparation is blocked by firmware compliance.",
                "checked_at": _now(),
                "blockers": gate_blockers,
                "warnings": [],
            },
        )
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    selected = _select_esxi_iso()
    bind_host = os.getenv("ESXI_MEDIA_HTTP_BIND", "0.0.0.0")
    port = int(os.getenv("ESXI_MEDIA_HTTP_PORT", str(DEFAULT_MEDIA_PORT)))
    advertised_host = os.getenv("ESXI_MEDIA_HTTP_HOST") or _source_ip_for_ilo()
    base_url = os.getenv("ESXI_MEDIA_BASE_URL")
    server = {"managed": False, "status": "not_required", "pid": None, "log": None}

    if base_url:
        url = f"{base_url.rstrip('/')}/{quote(selected['path'].name)}"
    else:
        server = _ensure_media_server(selected["directory"], bind_host, port)
        url = f"http://{advertised_host}:{port}/{quote(selected['path'].name)}"

    validation = _validate_media_url(url, selected["size_bytes"])
    status = "ready" if validation["reachable"] else "blocked"
    blockers = [] if status == "ready" else ["Selected ESXi ISO URL is not reachable from this host on the iLO-facing network."]
    report = _sanitize(
        {
            "status": status,
            "message": "Selected ESXi ISO media URL is ready." if status == "ready" else "Selected ESXi ISO media URL is blocked.",
            "checked_at": _now(),
            "selected_iso": _selected_iso_summary(selected),
            "media_url": url,
            "validation": validation,
            "server": server,
            "blockers": blockers,
            "warnings": _media_url_warnings(base_url),
            "report": str(MEDIA_URL_REPORT.relative_to(REPO_ROOT)),
            "next_safe_action": "Insert the selected ISO through iLO VirtualMedia." if status == "ready" else "Fix media URL reachability before virtual media insert.",
        }
    )
    MEDIA_URL_REPORT.write_text(_markdown("ESXi Media URL Report", report), encoding="utf-8")
    return report


def insert_esxi_virtual_media() -> dict[str, Any]:
    policy_blockers = _action_blockers("ilo.virtual-media", ActionCategory.VIRTUAL_MEDIA)
    policy_blockers.extend(firmware_gate_blockers("ESXi virtual media insert"))
    if policy_blockers:
        return _write_report(
            VIRTUAL_MEDIA_REPORT,
            "ESXi Virtual Media Report",
            {
                "status": "blocked",
                "message": "Virtual media insert is blocked by lab action policy.",
                "checked_at": _now(),
                "blockers": policy_blockers,
                "warnings": [],
            },
        )

    media = prepare_esxi_media_url()
    if media["status"] != "ready":
        return _write_report(
            VIRTUAL_MEDIA_REPORT,
            "ESXi Virtual Media Report",
            {
                "status": "blocked",
                "message": "Virtual media insert requires a reachable media URL.",
                "checked_at": _now(),
                "media_url_status": media,
                "blockers": media.get("blockers") or [],
                "warnings": media.get("warnings") or [],
            },
        )

    device = _select_virtual_media_device()
    before = _get_redfish_resource(device["path"])
    insert = _post_virtual_media_action(device, str(media["media_url"]))
    after = _get_redfish_resource(device["path"])
    after_body = _body(after)
    inserted = bool(after_body.get("Inserted"))
    connected = after_body.get("ConnectedVia")
    image_matches = bool(after_body.get("Image"))
    status = "inserted" if inserted and image_matches else "blocked"
    result = {
        "status": status,
        "message": "ESXi ISO is inserted through iLO VirtualMedia." if status == "inserted" else "iLO VirtualMedia insert did not report inserted media.",
        "checked_at": _now(),
        "selected_iso": media.get("selected_iso"),
        "media_url": media.get("media_url"),
        "device": device,
        "before": _virtual_media_summary(before),
        "insert_request": insert,
        "after": _virtual_media_summary(after),
        "connected_via": connected,
        "inserted": inserted,
        "blockers": [] if status == "inserted" else ["Virtual media state does not show inserted ISO after insert action."],
        "warnings": [],
        "report": str(VIRTUAL_MEDIA_REPORT.relative_to(REPO_ROOT)),
        "next_safe_action": "Set one-time boot target to virtual CD/DVD." if status == "inserted" else "Resolve VirtualMedia insert state before boot override.",
    }
    VIRTUAL_MEDIA_STATE.write_text(json.dumps(_sanitize(result), indent=2), encoding="utf-8")
    return _write_report(VIRTUAL_MEDIA_REPORT, "ESXi Virtual Media Report", result)


def set_esxi_one_time_boot() -> dict[str, Any]:
    policy_blockers = _action_blockers("ilo.boot-settings", ActionCategory.BOOT_CONFIG)
    policy_blockers.extend(firmware_gate_blockers("ESXi one-time boot"))
    if policy_blockers:
        return _write_report(
            ONE_TIME_BOOT_REPORT,
            "ESXi One-Time Boot Report",
            {
                "status": "blocked",
                "message": "One-time boot is blocked by lab action policy.",
                "checked_at": _now(),
                "blockers": policy_blockers,
                "warnings": [],
            },
        )

    before = _get_redfish_resource(SYSTEM_PATH)
    before_summary = _boot_summary(before)
    BOOT_SETTINGS_BEFORE.write_text(json.dumps(_sanitize(before_summary), indent=2), encoding="utf-8")
    target = _preferred_boot_target(before_summary.get("target_allowable_values") or [])
    if not target:
        return _write_report(
            ONE_TIME_BOOT_REPORT,
            "ESXi One-Time Boot Report",
            {
                "status": "blocked",
                "message": "No CD/DVD/virtual media boot target is available.",
                "checked_at": _now(),
                "before": before_summary,
                "blockers": ["BootSourceOverrideTarget does not advertise a virtual CD/DVD target."],
                "warnings": [],
            },
        )

    patch = _patch_system_boot({"Boot": {"BootSourceOverrideEnabled": "Once", "BootSourceOverrideTarget": target}})
    after = _get_redfish_resource(SYSTEM_PATH)
    after_summary = _boot_summary(after)
    BOOT_SETTINGS_AFTER.write_text(json.dumps(_sanitize(after_summary), indent=2), encoding="utf-8")
    status = "set" if after_summary.get("boot_source_override_enabled") == "Once" and after_summary.get("boot_source_override_target") == target else "blocked"
    return _write_report(
        ONE_TIME_BOOT_REPORT,
        "ESXi One-Time Boot Report",
        {
            "status": status,
            "message": f"One-time boot target set to {target}." if status == "set" else "One-time boot target was not confirmed after PATCH.",
            "checked_at": _now(),
            "target": target,
            "before": before_summary,
            "patch": patch,
            "after": after_summary,
            "blockers": [] if status == "set" else ["Boot override after state does not match requested one-time CD/DVD boot."],
            "warnings": [],
            "report": str(ONE_TIME_BOOT_REPORT.relative_to(REPO_ROOT)),
            "next_safe_action": "Run controlled server reset to boot the ESXi installer." if status == "set" else "Resolve boot override state before reset.",
        },
    )


def reset_for_esxi_installer_boot() -> dict[str, Any]:
    policy_blockers = _action_blockers("ilo.power-action", ActionCategory.POWER_ACTION)
    policy_blockers.extend(firmware_gate_blockers("ESXi installer reset"))
    if policy_blockers:
        return _write_report(
            INSTALLER_BOOT_REPORT,
            "ESXi Installer Boot Report",
            {
                "status": "blocked",
                "message": "Server reset is blocked by lab action policy.",
                "checked_at": _now(),
                "blockers": policy_blockers,
                "warnings": [],
            },
        )

    media = insert_esxi_virtual_media()
    boot = set_esxi_one_time_boot()
    blockers = []
    if media.get("status") != "inserted":
        blockers.append("Virtual media is not confirmed inserted.")
    if boot.get("status") != "set":
        blockers.append("One-time boot is not confirmed set.")
    if blockers:
        return _write_report(
            INSTALLER_BOOT_REPORT,
            "ESXi Installer Boot Report",
            {
                "status": "blocked",
                "message": "Reset was not attempted because prerequisites are blocked.",
                "checked_at": _now(),
                "virtual_media": media,
                "one_time_boot": boot,
                "blockers": blockers,
                "warnings": [],
            },
        )

    reset = _post_system_reset(RESET_TYPE)
    wait = _wait_for_ilo()
    post_system = _safe_get(SYSTEM_PATH)
    vm_state = _safe_get(str((media.get("device") or {}).get("path") or ""))
    detection = _installer_detection(post_system, vm_state)
    status = "boot_requested" if wait["reachable"] else "blocked"
    warnings = detection.get("warnings") or []
    if detection.get("status") == "indeterminate":
        warnings.append("iLO Redfish did not expose a definitive ESXi installer console/boot signal.")
    return _write_report(
        INSTALLER_BOOT_REPORT,
        "ESXi Installer Boot Report",
        {
            "status": status,
            "message": "Server reset completed and ESXi installer boot was requested." if status == "boot_requested" else "Server did not return to iLO reachability after reset wait.",
            "checked_at": _now(),
            "reset": reset,
            "wait": wait,
            "post_system": _boot_summary(post_system) if post_system.get("status_code") else post_system,
            "virtual_media_after_reset": _virtual_media_summary(vm_state) if vm_state.get("status_code") else vm_state,
            "installer_detection": detection,
            "blockers": [] if status == "boot_requested" else ["iLO/server did not return during reset wait."],
            "warnings": warnings,
            "report": str(INSTALLER_BOOT_REPORT.relative_to(REPO_ROOT)),
            "next_safe_action": "Use console or manual KVM observation to continue ESXi installer if Redfish detection is indeterminate.",
        },
    )


def detect_esxi_installer_boot_status() -> dict[str, Any]:
    post_system = _safe_get(SYSTEM_PATH)
    media_path = _latest_virtual_media_path()
    vm_state = _safe_get(media_path or "")
    detection = _installer_detection(post_system, vm_state)
    status = "detected" if detection.get("status") == "detected" else "indeterminate"
    warnings = detection.get("warnings") or []
    if status == "indeterminate":
        warnings.append("iLO Redfish did not expose a definitive ESXi installer console/boot signal.")
    return _write_report(
        INSTALLER_BOOT_REPORT,
        "ESXi Installer Boot Report",
        {
            "status": "boot_requested" if status == "detected" else "indeterminate",
            "message": "ESXi installer or installed ESXi boot state is visible through iLO Redfish." if status == "detected" else "ESXi boot was requested, but installer state is not definitive through Redfish.",
            "checked_at": _now(),
            "post_system": _boot_summary(post_system) if post_system.get("status_code") else post_system,
            "virtual_media_after_reset": _virtual_media_summary(vm_state) if vm_state.get("status_code") else vm_state,
            "installer_detection": detection,
            "blockers": [],
            "warnings": warnings,
            "report": str(INSTALLER_BOOT_REPORT.relative_to(REPO_ROOT)),
            "next_safe_action": "Continue with Cisco console and Ethernet bootstrap readiness.",
        },
    )


def esxi_boot_workflow_summary() -> dict[str, Any]:
    return {
        "media_url": _report_summary(MEDIA_URL_REPORT),
        "virtual_media": _report_summary(VIRTUAL_MEDIA_REPORT),
        "one_time_boot": _report_summary(ONE_TIME_BOOT_REPORT),
        "reset_boot": _report_summary(INSTALLER_BOOT_REPORT),
    }


def _select_esxi_iso() -> dict[str, Any]:
    explicit = os.getenv("ESXI_INSTALL_ISO") or os.getenv("ESXI_ISO_PATH")
    directories = [Path(item).expanduser().resolve() for item in settings.media_inventory_dirs]
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not _is_under_any(path, directories):
            raise RuntimeError("Selected ESXi ISO must be under MEDIA_INVENTORY_DIRS.")
        if not path.is_file() or path.suffix.lower() != ".iso":
            raise RuntimeError("Selected ESXi ISO path is not an ISO file.")
        return {"path": path, "directory": path.parent, "size_bytes": path.stat().st_size, "selection": "explicit-env"}

    candidates: list[Path] = []
    for directory in directories:
        if not directory.is_dir():
            continue
        candidates.extend(path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".iso" and "esxi" in path.name.lower())
    if not candidates:
        raise RuntimeError("No ESXi ISO was found under MEDIA_INVENTORY_DIRS.")

    def score(path: Path) -> tuple[int, str]:
        lowered = path.name.lower()
        preferred = sum(1 for marker in PREFERRED_ISO_MARKERS if marker in lowered)
        hpe = 1 if "hpe" in lowered else 0
        return (preferred + hpe, path.name.lower())

    selected = sorted(candidates, key=score, reverse=True)[0]
    return {"path": selected, "directory": selected.parent, "size_bytes": selected.stat().st_size, "selection": "preferred-esxi-8"}


def _ensure_media_server(directory: Path, bind_host: str, port: int) -> dict[str, Any]:
    if _port_open("127.0.0.1", port):
        return {"managed": False, "status": "existing-listener", "pid": None, "log": None, "bind": bind_host, "port": port}
    command = [
        os.getenv("PYTHON", "python3"),
        "-m",
        "http.server",
        str(port),
        "--bind",
        bind_host,
        "--directory",
        str(directory),
    ]
    log = MEDIA_SERVER_LOG.open("ab")
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    MEDIA_SERVER_PID.write_text(str(process.pid), encoding="utf-8")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if _port_open("127.0.0.1", port):
            return {"managed": True, "status": "started", "pid": process.pid, "log": str(MEDIA_SERVER_LOG.relative_to(REPO_ROOT)), "bind": bind_host, "port": port}
        time.sleep(0.2)
    return {"managed": True, "status": "start-pending", "pid": process.pid, "log": str(MEDIA_SERVER_LOG.relative_to(REPO_ROOT)), "bind": bind_host, "port": port}


def _validate_media_url(url: str, expected_size: int) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=httpx.Timeout(10.0), follow_redirects=True, trust_env=False) as client:
            head = client.head(url)
            if head.status_code in {405, 501}:
                head = client.get(url, headers={"Range": "bytes=0-0"})
        size_header = head.headers.get("content-length")
        return {
            "reachable": 200 <= head.status_code < 400,
            "status_code": head.status_code,
            "content_length": int(size_header) if size_header and size_header.isdigit() else None,
            "expected_size_bytes": expected_size,
            "same_size": int(size_header) == expected_size if size_header and size_header.isdigit() else None,
        }
    except httpx.HTTPError as exc:
        return {"reachable": False, "error_class": type(exc).__name__, "error": str(exc), "expected_size_bytes": expected_size}


def _select_virtual_media_device() -> dict[str, Any]:
    managers = _get_redfish_resource("/redfish/v1/Managers/")
    manager_path = "/redfish/v1/Managers/1/"
    members = _body(managers).get("Members")
    if isinstance(members, list) and members:
        manager_path = _odata_id(members[0]) or manager_path
    manager = _get_redfish_resource(manager_path)
    vm_path = _odata_id(_body(manager).get("VirtualMedia")) or f"{manager_path.rstrip('/')}/VirtualMedia/"
    collection = _get_redfish_resource(vm_path)
    for member in _body(collection).get("Members") or []:
        path = _odata_id(member)
        if not path:
            continue
        item = _get_redfish_resource(path)
        body = _body(item)
        media_types = [str(value) for value in body.get("MediaTypes") or []]
        if "CD" in media_types or "DVD" in media_types:
            actions = body.get("Actions") if isinstance(body.get("Actions"), dict) else {}
            action = actions.get("#VirtualMedia.InsertMedia") or actions.get("VirtualMedia.InsertMedia") or {}
            return {"path": path, "id": body.get("Id"), "name": body.get("Name"), "media_types": media_types, "insert_target": action.get("target") or f"{path.rstrip('/')}/Actions/VirtualMedia.InsertMedia/"}
    raise RuntimeError("No CD/DVD-capable iLO VirtualMedia device was found.")


def _post_virtual_media_action(device: dict[str, Any], url: str) -> dict[str, Any]:
    payload = {"Image": url, "Inserted": True, "TransferProtocolType": "HTTP"}
    return _post_redfish(str(device["insert_target"]), payload)


def _post_redfish(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    base_url = _base_url(settings.ilo_test_host or "")
    with httpx.Client(
        auth=(settings.ilo_test_username, settings.ilo_test_password),
        follow_redirects=False,
        timeout=httpx.Timeout(settings.ilo_test_timeout_seconds),
        trust_env=False,
        verify=settings.ilo_test_verify_tls,
    ) as client:
        response = client.post(base_url + path, json=payload)
        try:
            body: Any = response.json()
        except ValueError:
            body = {"text": response.text[:1000]}
    return _sanitize({"method": "POST", "path": path, "status_code": response.status_code, "request": payload, "response": body})


def _patch_system_boot(payload: dict[str, Any]) -> dict[str, Any]:
    system = _get_redfish_resource(SYSTEM_PATH)
    etag = system.get("etag") or "*"
    base_url = _base_url(settings.ilo_test_host or "")
    with httpx.Client(
        auth=(settings.ilo_test_username, settings.ilo_test_password),
        follow_redirects=False,
        timeout=httpx.Timeout(settings.ilo_test_timeout_seconds),
        trust_env=False,
        verify=settings.ilo_test_verify_tls,
    ) as client:
        response = client.patch(base_url + SYSTEM_PATH, headers={"If-Match": str(etag)}, json=payload)
        try:
            body: Any = response.json()
        except ValueError:
            body = {"text": response.text[:1000]}
    return _sanitize({"method": "PATCH", "path": SYSTEM_PATH, "status_code": response.status_code, "request": payload, "response": body})


def _wait_for_ilo() -> dict[str, Any]:
    timeout_seconds = int(os.getenv("ESXI_INSTALL_BOOT_WAIT_SECONDS", "900"))
    poll_seconds = int(os.getenv("ESXI_INSTALL_BOOT_POLL_SECONDS", "20"))
    started = time.monotonic()
    attempts = 0
    last_error: dict[str, Any] | None = None
    while time.monotonic() - started <= timeout_seconds:
        attempts += 1
        result = _safe_get(SYSTEM_PATH)
        if result.get("status_code"):
            return {
                "reachable": True,
                "attempts": attempts,
                "elapsed_seconds": int(time.monotonic() - started),
                "power_state": _body(result).get("PowerState"),
            }
        last_error = result
        time.sleep(max(poll_seconds, 1))
    return {"reachable": False, "attempts": attempts, "elapsed_seconds": int(time.monotonic() - started), "last_error": last_error}


def _installer_detection(system: dict[str, Any], virtual_media: dict[str, Any]) -> dict[str, Any]:
    system_body = _body(system)
    vm_body = _body(virtual_media)
    oem_hpe = (system_body.get("Oem") or {}).get("Hpe") if isinstance(system_body.get("Oem"), dict) else {}
    host_os = oem_hpe.get("HostOS") if isinstance(oem_hpe, dict) and isinstance(oem_hpe.get("HostOS"), dict) else {}
    evidence = {
        "power_state": system_body.get("PowerState"),
        "boot": _boot_summary(system),
        "boot_progress": system_body.get("BootProgress"),
        "hpe_post_state": oem_hpe.get("PostState") if isinstance(oem_hpe, dict) else None,
        "hpe_device_discovery": oem_hpe.get("DeviceDiscoveryComplete") if isinstance(oem_hpe, dict) else None,
        "host_os": {
            "name": host_os.get("OsName"),
            "version": host_os.get("OsVersion"),
            "type": host_os.get("OsType"),
            "description_hint": _safe_host_os_description(host_os.get("OsSysDescription")),
        },
        "virtual_media_inserted": vm_body.get("Inserted"),
        "virtual_media_connected_via": vm_body.get("ConnectedVia"),
        "virtual_media_image_present": bool(vm_body.get("Image")),
    }
    text = json.dumps(evidence, default=str).lower()
    detected = any(marker in text for marker in ("esxi", "vmware", "installer"))
    if detected:
        return {"status": "detected", "method": "redfish-state", "evidence": _sanitize(evidence), "warnings": []}
    return {"status": "indeterminate", "method": "redfish-state", "evidence": _sanitize(evidence), "warnings": []}


def _safe_host_os_description(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    lowered = value.lower()
    if "vmware" not in lowered and "esxi" not in lowered:
        return None
    return "VMware ESXi description present"


def _boot_summary(response: dict[str, Any]) -> dict[str, Any]:
    body = _body(response)
    boot = body.get("Boot") if isinstance(body.get("Boot"), dict) else {}
    return {
        "status_code": response.get("status_code"),
        "power_state": body.get("PowerState"),
        "boot_source_override_enabled": boot.get("BootSourceOverrideEnabled"),
        "boot_source_override_mode": boot.get("BootSourceOverrideMode"),
        "boot_source_override_target": boot.get("BootSourceOverrideTarget"),
        "target_allowable_values": boot.get("BootSourceOverrideTarget@Redfish.AllowableValues") or [],
        "enabled_allowable_values": boot.get("BootSourceOverrideEnabled@Redfish.AllowableValues") or [],
    }


def _virtual_media_summary(response: dict[str, Any]) -> dict[str, Any]:
    body = _body(response)
    return {
        "status_code": response.get("status_code"),
        "id": body.get("Id"),
        "name": body.get("Name"),
        "media_types": body.get("MediaTypes"),
        "connected_via": body.get("ConnectedVia"),
        "inserted": body.get("Inserted"),
        "image_present": bool(body.get("Image")),
        "actions": sorted((body.get("Actions") or {}).keys()) if isinstance(body.get("Actions"), dict) else [],
    }


def _preferred_boot_target(values: list[Any]) -> str | None:
    normalized = [str(value) for value in values]
    for candidate in ("Cd", "DVD", "Usb", "UefiTarget"):
        if candidate in normalized:
            return candidate
    return None


def _report_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "not_run", "report": str(path.relative_to(REPO_ROOT))}
    text = path.read_text(encoding="utf-8", errors="replace")
    status = "unknown"
    message = ""
    for line in text.splitlines():
        if line.startswith("- status:"):
            status = line.split(":", 1)[1].strip()
        if line.startswith("- message:"):
            message = line.split(":", 1)[1].strip()
    return {"status": status, "message": message, "report": str(path.relative_to(REPO_ROOT))}


def _latest_virtual_media_path() -> str | None:
    if not VIRTUAL_MEDIA_STATE.exists():
        return None
    try:
        payload = json.loads(VIRTUAL_MEDIA_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    device = payload.get("device") if isinstance(payload, dict) else None
    path = device.get("path") if isinstance(device, dict) else None
    return path if isinstance(path, str) else None


def _write_report(path: Path, title: str, payload: dict[str, Any]) -> dict[str, Any]:
    payload = {**payload, "report": str(path.relative_to(REPO_ROOT))}
    sanitized = _sanitize(payload)
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(_markdown(title, sanitized), encoding="utf-8")
    return sanitized


def _markdown(title: str, payload: dict[str, Any]) -> str:
    lines = [f"# {title}", "", "## Summary", ""]
    for key in ("checked_at", "status", "message", "report", "next_safe_action"):
        if key in payload:
            lines.append(f"- {key}: {payload.get(key)}")
    lines.extend(["", "## Blockers", ""])
    lines.extend([f"- {item}" for item in payload.get("blockers") or []] or ["- none"])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {item}" for item in payload.get("warnings") or []] or ["- none"])
    lines.extend(["", "## Details", "", "```json", json.dumps(payload, indent=2, sort_keys=True), "```", ""])
    return "\n".join(lines)


def _action_blockers(action_id: str, category: ActionCategory) -> list[str]:
    return current_lab_action_policy(settings.provider_mode).action_blockers(action_id, category)


def _selected_iso_summary(selected: dict[str, Any]) -> dict[str, Any]:
    path = selected["path"]
    return {
        "name": path.name,
        "directory": str(path.parent),
        "size_bytes": selected["size_bytes"],
        "selection": selected["selection"],
    }


def _media_url_warnings(base_url: str | None) -> list[str]:
    if base_url:
        return ["Using configured ESXI_MEDIA_BASE_URL; local managed media server was not started."]
    return ["URL reachability is validated from this host using the iLO-facing source address; final proof is iLO VirtualMedia insert state."]


def _safe_get(path: str) -> dict[str, Any]:
    if not path:
        return {"status_code": None, "error": "missing path"}
    try:
        return _get_redfish_resource(path)
    except Exception as exc:
        return {"status_code": None, "error_class": type(exc).__name__, "error": str(exc)}


def _body(response: dict[str, Any]) -> dict[str, Any]:
    body = response.get("body")
    return body if isinstance(body, dict) else {}


def _odata_id(value: Any) -> str | None:
    if isinstance(value, dict) and isinstance(value.get("@odata.id"), str):
        return value["@odata.id"]
    return None


def _source_ip_for_ilo() -> str:
    host = settings.ilo_test_host or "192.168.1.201"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect((host, 443))
        return str(sock.getsockname()[0])


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _is_under_any(path: Path, directories: list[Path]) -> bool:
    return any(path == directory or directory in path.parents for directory in directories)


def _sanitize(payload: Any) -> Any:
    return redact_sensitive(payload, [settings.ilo_test_host, settings.ilo_test_username, settings.ilo_test_password])


def _now() -> str:
    return datetime.now(UTC).isoformat()
