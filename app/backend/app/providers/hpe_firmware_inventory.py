"""Explicit read-only firmware discovery; never invoked by status or preview."""

import hashlib
import json
import re
from datetime import UTC, datetime

from app.providers.action_policy import current_lab_action_policy
from app.providers.hpe_storage_rebuild import client_for
from app.providers.ilo_redfish import IloRedfishAdapter, _base_url, _hardware_identity_fingerprints
from app.services.ilo_access_settings import ilo_config_for_device
from app.services.ilo_write_target import resolve_ilo_write_target_context
from app.services.hardware_health import health_issues
from app.services.ilo_firmware_health import assess_ilo_firmware_health


class FirmwareInventoryError(ValueError):
    pass


def _resource_path(value):
    if (
        not isinstance(value, str)
        or not re.fullmatch(
            r"/redfish/v1/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]*/?",
            value,
        )
        or any(part in {".", ".."} for part in value.split("/"))
    ):
        raise FirmwareInventoryError(
            "Firmware resource link is not a safe same-target Redfish path."
        )
    return value


def discover_update_service(client, base_url: str) -> dict:
    def read(path):
        response = client.get(base_url + _resource_path(path), follow_redirects=False)
        if response.status_code != 200:
            raise FirmwareInventoryError("Firmware discovery did not return a successful read.")
        value = response.json()
        if not isinstance(value, dict) or "error" in value:
            raise FirmwareInventoryError("Firmware discovery returned an invalid resource.")
        return value

    root = read("/redfish/v1/")
    service_path = _resource_path(root.get("UpdateService", {}).get("@odata.id"))
    service = read(service_path)
    if service.get("ServiceEnabled") is not True:
        raise FirmwareInventoryError("Firmware update service is not explicitly enabled.")
    inventory_path = _resource_path(service.get("FirmwareInventory", {}).get("@odata.id"))
    if not inventory_path.startswith(service_path.rstrip("/") + "/"):
        raise FirmwareInventoryError("Firmware inventory is outside the discovered update service.")
    collection = read(inventory_path)
    members = collection.get("Members")
    count = collection.get("Members@odata.count")
    if (
        not isinstance(members, list)
        or len(members) > 64
        or type(count) is not int
        or count != len(members)
        or collection.get("Members@odata.nextLink")
    ):
        raise FirmwareInventoryError(
            "Firmware inventory is incomplete or exceeds supported limits."
        )
    items = []
    paths = set()
    for member in members:
        path = _resource_path(member.get("@odata.id"))
        if not path.startswith(inventory_path.rstrip("/") + "/"):
            raise FirmwareInventoryError("Firmware member is outside its inventory collection.")
        if path in paths:
            raise FirmwareInventoryError("Firmware inventory contains duplicate resource links.")
        paths.add(path)
        item = read(path)
        items.append(
            {
                "resource_path": path,
                "name": item.get("Name"),
                "version": item.get("Version"),
                "updateable": item.get("Updateable"),
                "status": item.get("Status"),
                "targets": item.get("Oem", {}).get("Hpe", {}).get("Targets"),
                "device_class": item.get("DeviceClass"),
            }
        )
    hpe = service.get("Oem", {}).get("Hpe", {})
    return {
        "update_service_path": service_path,
        "http_push_uri": service.get("HttpPushUri"),
        "state": hpe.get("State"),
        "capabilities": hpe.get("Capabilities", {}),
        "max_image_size_bytes": service.get("MaxImageSizeBytes"),
        "inventory": items,
        "errors": ["Update service reports a result or message requiring review."]
        if hpe.get("Result") or hpe.get("Messages")
        else [],
    }


def _hardware_identity(probe) -> str | None:
    prints = _hardware_identity_fingerprints(probe.get("systems") or [])
    if not prints:
        return None
    return hashlib.sha256(json.dumps(prints, separators=(",", ":")).encode("utf-8")).hexdigest()


def collect_firmware_capabilities(session, device_id: str) -> dict:
    blockers = current_lab_action_policy().readonly_blockers()
    if blockers:
        raise FirmwareInventoryError(" ".join(blockers))
    config = ilo_config_for_device(session, device_id)
    if not config.configured or config.fallback_hosts:
        raise FirmwareInventoryError("A configured, exact-device iLO connection is required.")
    probe = IloRedfishAdapter(config=config).probe()
    context, blockers = resolve_ilo_write_target_context(config.host, scope=device_id)
    if context is None or blockers or probe.get("status") != "ok":
        raise FirmwareInventoryError("Fresh authenticated exact-target identity is required.")
    managers = probe.get("managers") or []
    if len(managers) != 1:
        raise FirmwareInventoryError("Exactly one identified iLO manager is required.")
    try:
        with client_for(config) as client:
            result = discover_update_service(client, _base_url(config.host))
    except FirmwareInventoryError:
        raise
    except Exception:
        raise FirmwareInventoryError(
            "Firmware capability read failed; no update was sent."
        ) from None
    return {
        **result,
        "device_id": device_id,
        "checked_at": datetime.now(UTC).isoformat(),
        "target_identity_sha256": context.identity_fingerprint_sha256,
        # Server hardware only (system UUID + serial). An iLO firmware update can change the
        # manager's own identity fields (observed 1.48 -> 3.19), so completion compares this.
        "target_hardware_identity_sha256": _hardware_identity(probe),
        "target_fingerprint": context.target_fingerprint,
        "manager_firmware_version": managers[0].get("FirmwareVersion"),
        "manager_model": managers[0].get("Model"),
        "server_model": (probe.get("systems") or [{}])[0].get("Model")
        if len(probe.get("systems") or []) == 1
        else None,
        "ilo_update_health": assess_ilo_firmware_health(probe),
        "system_health": ((probe.get("systems") or [{}])[0].get("Status") or {}).get("Health")
        if len(probe.get("systems") or []) == 1
        else None,
        "health_issues": [
            {"group": issue["group"], "health": issue["health"]} for issue in health_issues(probe)
        ],
        "source": "live-ilo-firmware-capabilities",
        "authenticated": True,
        "exact_target_only": True,
        "identity_verified": True,
        "can_apply": False,
        "message": "Read-only capabilities recorded; package prerequisites and approval remain separate.",
    }
