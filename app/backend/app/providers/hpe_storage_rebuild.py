"""HPE Gen10 SR pending configuration and guarded power-on. No forced restart."""
import re

import httpx

from app.providers.action_policy import current_lab_action_policy
from app.services.runtime_write_scope import dispatch_lease
from app.providers.ilo_redfish import IloRedfishAdapter, _base_url
from app.services.hardware_health import digest
from app.services.hpe_raid import _get_with_retries
from app.services.ilo_access_settings import ilo_config_for_device
from app.services.ilo_write_target import resolve_ilo_write_target_context


class StorageRebuildError(ValueError):
    pass


def client_for(config):
    return httpx.Client(auth=(config.username, config.password), verify=config.verify_tls,
                        timeout=config.timeout_seconds, follow_redirects=False, trust_env=False,
                        limits=httpx.Limits(max_keepalive_connections=0))


def logical_signature(config):
    drives = config.get("LogicalDrives")
    if not isinstance(drives, list):
        raise StorageRebuildError("HPE did not return a complete logical-drive configuration.")
    result = []
    for drive in drives:
        bays = drive.get("DataDrives")
        if not isinstance(bays, list) or not all(isinstance(b, str) for b in bays):
            raise StorageRebuildError("Exact logical-drive membership was not reported. Use HPE SSA.")
        result.append({"name": drive.get("LogicalDriveName"), "raid": str(drive.get("Raid", "")).lower(),
                       "bays": sorted(bays), "spares": sorted(drive.get("SpareDrives") or []),
                       "spare_mode": drive.get("SpareRebuildMode") if drive.get("SpareDrives") else None,
                       "capacity": drive.get("CapacityGiB"), "id": drive.get("VolumeUniqueIdentifier")})
    return sorted(result, key=lambda d: digest(d))


def pending_signature(config):
    # An action-only reset has no requested drive layout, not an empty applied layout.
    if ("LogicalDrives" not in config
            and config.get("Actions") == [{"Action": "FactoryReset"}]
            and config.get("DataGuard") == "Disabled"):
        return None
    return logical_signature(config)


def requested_layout_matches(current, payload):
    actual = logical_signature(current)
    desired = logical_signature({"LogicalDrives": []} if payload == {
        "Actions": [{"Action": "FactoryReset"}], "DataGuard": "Disabled"
    } else payload)
    # New volumes receive firmware-assigned capacity and identifiers after POST.
    project = lambda rows: sorted((r["name"] or "", r["raid"], tuple(r["bays"]), tuple(r["spares"]), r["spare_mode"] or "") for r in rows)
    return project(actual) == project(desired)


def read_snapshot(session, device_id):
    blockers = current_lab_action_policy().readonly_blockers()
    if blockers:
        raise StorageRebuildError(" ".join(blockers))
    config = ilo_config_for_device(session, device_id)
    if not config.configured or config.fallback_hosts:
        raise StorageRebuildError("A complete, exact-device iLO connection is required.")
    probe = IloRedfishAdapter(config=config).probe()
    context, blockers = resolve_ilo_write_target_context(config.host, scope=device_id)
    if blockers or context is None:
        raise StorageRebuildError(" ".join(blockers) or "Fresh target identity could not be verified.")
    controllers = [c for c in probe.get("storage", {}).get("controllers", []) if c.get("Model")]
    systems = probe.get("systems") or []
    if len(controllers) != 1 or len(systems) != 1:
        raise StorageRebuildError("Automatic rebuild currently supports one system and one identified HPE SR controller. Use HPE SSA for other layouts.")
    system_path = systems[0].get("@odata.id", "").rstrip("/") + "/"
    if not re.fullmatch(r"/redfish/v1/systems/[A-Za-z0-9_-]+/", system_path, re.I):
        raise StorageRebuildError("The server did not report a supported system resource path.")
    current_path = system_path + "SmartStorageConfig/"
    try:
        with client_for(config) as client:
            response = _get_with_retries(client, _base_url(config.host) + current_path, require_success=True)
            current = response.json()
            if not re.match(r"#SmartStorageConfig\.v2_", current.get("@odata.type", "")):
                raise StorageRebuildError("This controller does not expose the supported HPE SmartStorageConfig v2 API. Use HPE SSA; Gen11/RDE is not supported by this executor.")
            if not controllers[0].get("Location") or current.get("Location") != controllers[0]["Location"]:
                raise StorageRebuildError("The configuration endpoint could not be matched to the inventoried controller location.")
            path = current.get("@Redfish.Settings", {}).get("SettingsObject", {}).get("@odata.id", "")
            if path.rstrip("/").lower() != (current_path + "Settings").lower():
                raise StorageRebuildError("HPE did not advertise a supported, same-system pending settings endpoint.")
            response = _get_with_retries(client, _base_url(config.host) + path, require_success=True)
            pending, etag = response.json(), response.headers.get("etag")
            if not etag or etag == "*":
                raise StorageRebuildError("HPE did not supply an exact pending-settings ETag. Refusing an unconditional storage write.")
    except httpx.HTTPStatusError as exc:
        raise StorageRebuildError(f"HPE storage read returned HTTP {exc.response.status_code} at {exc.request.url.path}. Check controller support and account permissions; no write was sent.") from exc
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        if isinstance(exc, StorageRebuildError):
            raise
        raise StorageRebuildError("Could not read the supported HPE storage configuration. No storage write was sent; check iLO permissions and controller support.") from exc
    current_layout, pending_layout = logical_signature(current), pending_signature(pending)
    pending_differs = current_layout != pending_layout or bool(pending.get("Actions"))
    state = {"identity": context.identity_fingerprint_sha256, "host": config.host,
             "storage": probe.get("storage"), "power": systems[0].get("PowerState"),
             "health": [{k: r.get(k) for k in ("Status", "Model")} for r in systems + (probe.get("chassis") or [])],
             "current": current_layout, "pending": pending_layout,
             "pending_actions": pending.get("Actions"), "pending_data_guard": pending.get("DataGuard"),
             "etag": etag, "path": path}
    return {"config": config, "probe": probe, "current": current, "pending": pending, "etag": etag,
            "path": path, "state_digest": digest(state), "pending_differs": pending_differs,
            "identity": context.identity_fingerprint_sha256, "power": systems[0].get("PowerState")}


def stage_configuration(snapshot, payload, *, sanitize=False):
    """One conditional PUT; a timeout is uncertain and MUST NOT be retried."""
    config = snapshot["config"]
    try:
        with dispatch_lease("ilo-redfish.hpe-raid-apply"), client_for(config) as client:
            send = client.patch if sanitize else client.put
            response = send(_base_url(config.host) + snapshot["path"],
                                  headers={"If-Match": snapshot["etag"]}, json=payload)
            try:
                body = response.json()
            except ValueError:
                body = {}
            ids = [str(i.get("MessageId", "")) for i in body.get("error", {}).get("@Message.ExtendedInfo", []) if isinstance(i, dict)]
            acceptable = all(i.endswith((".Success", ".SystemResetRequired")) for i in ids)
            accepted = response.status_code in {200, 202, 204} and acceptable and ("error" not in body or bool(ids))
            return {"status": "pending" if accepted else "uncertain", "http_status": response.status_code,
                    "message": "Configuration staged. It takes effect at the next server boot. Verify in HPE SSA and refresh inventory afterward." if accepted else
                    "HPE did not confirm acceptance. Do not retry or boot blindly. Inspect pending configuration in iLO/HPE SSA first."}
    except httpx.HTTPError:
        return {"status": "uncertain", "message": "Connection lost during the storage request. It may have been accepted. Do not retry or boot blindly; inspect pending configuration in iLO/HPE SSA."}


def read_boot_action(snapshot):
    """Use the advertised same-system action, never a caller-supplied URL."""
    config = snapshot["config"]
    # Firmware may advertise lowercase resource paths.
    system_path = re.split(r"/smartstorageconfig/", snapshot["path"], flags=re.I)[0]
    try:
        with client_for(config) as client:
            response = _get_with_retries(client, _base_url(config.host) + system_path + "/", require_success=True)
            system = response.json()
        action = system.get("Actions", {}).get("#ComputerSystem.Reset", {})
        path = action.get("target", "")
        if (path.rstrip("/").lower() != (system_path + "/Actions/ComputerSystem.Reset").lower()
                or "On" not in action.get("ResetType@Redfish.AllowableValues", [])):
            raise StorageRebuildError("This iLO does not advertise a supported power-on action. No power request was sent.")
        if system.get("PowerState") != "Off":
            raise StorageRebuildError("The server must be shut down cleanly before starting this RAID operation. The app will not force a running server off.")
        return path
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        if isinstance(exc, StorageRebuildError):
            raise
        raise StorageRebuildError("Could not verify the server power-on action. No power request was sent.") from exc


def start_server(snapshot, path):
    """One power-on POST; claim is committed by the caller before this call."""
    try:
        with dispatch_lease("ilo-redfish.raid-boot"), client_for(snapshot["config"]) as client:
            response = client.post(_base_url(snapshot["config"].host) + path, json={"ResetType": "On"})
        accepted = response.status_code in {200, 202, 204}
        return {"status": "waiting" if accepted else "uncertain",
                "http_status": response.status_code,
                "message": "Power-on accepted. Waiting for HPE POST and RAID verification." if accepted else
                "Power-on was not confirmed. Do not retry; check the server and read back the RAID result."}
    except httpx.HTTPError:
        return {"status": "uncertain", "message": "Power-on response was lost. It may have started. Do not retry; verification can still run."}


def shutdown_action(snapshot, force=False):
    config = snapshot['config']
    system_path = re.split(r'/smartstorageconfig/', snapshot['path'], flags=re.I)[0]
    try:
        with client_for(config) as client:
            response = client.get(_base_url(config.host) + system_path + '/')
            response.raise_for_status()
            system = response.json()
        action = system.get('Actions', {}).get('#ComputerSystem.Reset', {})
        path = action.get('target', '')
        allowed = action.get('ResetType@Redfish.AllowableValues', [])
        method = 'ForceOff' if force else 'GracefulShutdown' if 'GracefulShutdown' in allowed else 'PushPowerButton'
        if system.get('PowerState') != 'On' or method not in allowed or path.rstrip('/').lower() != (system_path + '/Actions/ComputerSystem.Reset').lower():
            raise StorageRebuildError('No supported shutdown action is advertised for the current power state. No request was sent.')
        return path, {'ResetType': method}
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        if isinstance(exc, StorageRebuildError):
            raise
        raise StorageRebuildError('Could not read the server shutdown capability. No request was sent.') from exc


def request_shutdown(snapshot, path, payload):
    try:
        with dispatch_lease("ilo-redfish.raid-shutdown"), client_for(snapshot['config']) as client:
            response = client.post(_base_url(snapshot['config'].host) + path, json=payload)
        accepted = response.status_code in {200, 202, 204}
        return {'status': 'requested' if accepted else 'uncertain',
                'message': 'Shutdown requested. Read the power state before resetting storage.' if accepted else
                'Shutdown acceptance was not confirmed. Read the power state; do not repeat the request blindly.'}
    except httpx.HTTPError:
        return {'status': 'uncertain', 'message': 'Shutdown response was lost. Read the power state; the request will not be retried.'}
