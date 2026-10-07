"""Supported SPP iLO installation adapter. Construction never contacts hardware."""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zipfile import ZipFile

import pycdlib
from sqlalchemy import select

from app.models import AuditEvent
from app.providers.action_policy import ActionCategory, current_lab_action_policy
from app.providers.hpe_firmware_inventory import collect_firmware_capabilities, _resource_path
from app.providers.hpe_ilo_firmware import FirmwareUploadError, upload_ilo_binary
from app.services.firmware_transport import FirmwareDispatchError, exception_kind, response_facts
from app.providers.hpe_storage_rebuild import client_for
from app.providers.ilo_redfish import _base_url, ilo_target_fingerprint
from app.services.firmware_packages import media_path, package_unchanged
from app.services.firmware_catalog import ilo_component, next_ilo_version
from app.services.spp_assessment import numeric_version
from app.services.firmware_trust import inspect_spp_bridge, verify_bridge_from_spp
from app.services.firmware_worker import FirmwareReviewError, PreparedFirmware, canonical_intent
from app.services.ilo_access_settings import ilo_config_for_device
from app.services.ilo_upgrade_path import ilo_upgrade_blockers
from app.services.runtime_write_scope import dispatch_lease, firmware_only


def bridge_intent(profile_id, device_id, selection_id, bridge, authentication, capabilities):
    """Build intent only from server-collected records, never from request JSON."""
    for text in (capabilities.get("manager_model"), capabilities.get("manager_firmware_version")):
        generation = re.search(r"\biLO\s*(\d+)\b", str(text or ""), re.I)
        if generation and generation[1] != "5":
            raise FirmwareReviewError(
                "This SPP installation adapter is for iLO 5, not the detected iLO generation."
            )
    checked = datetime.fromisoformat(capabilities["checked_at"].replace("Z", "+00:00"))
    now = datetime.now(UTC)
    if checked.tzinfo is None or not now - timedelta(minutes=5) <= checked <= now:
        raise FirmwareReviewError("A fresh explicit firmware capability check is required.")
    if (
        capabilities.get("source") != "live-ilo-firmware-capabilities"
        or capabilities.get("device_id") != device_id
        or any(
            capabilities.get(k) is not True
            for k in ("authenticated", "exact_target_only", "identity_verified")
        )
        or capabilities.get("state") != "Idle"
        or capabilities.get("errors") != []
        or capabilities.get("http_push_uri") not in {"/cgi-bin/uploadFile", "/cgi-bin/uploadFile/"}
    ):
        raise FirmwareReviewError("Fresh authenticated idle iLO update capability is required.")
    assessment = capabilities.get("ilo_update_health") or {}
    if assessment.get("scope") != "ilo-only-v1" or assessment.get("blockers") != []:
        raise FirmwareReviewError(
            " ".join(
                assessment.get("blockers")
                or ["Run a fresh iLO-specific power, cooling and controller health check."]
            )
        )
    declaration = authentication.get("authenticated_declaration", {})
    binary = authentication.get("binary", {})
    target = next_ilo_version(capabilities.get("manager_firmware_version"))
    if (
        authentication.get("binary_authenticated") is not True
        or authentication.get("component_sha256") != bridge.get("sha256")
        or declaration.get("version") != target
        or declaration.get("direct_flash") is not True
        or declaration.get("host_power_change_required") is not False
        or not declaration.get("targets")
        or binary.get("sha256") != bridge["payload"]["binary"]["sha256"]
    ):
        raise FirmwareReviewError(
            "Authenticated firmware bytes and declarations for the next update are required."
        )
    matching = [
        item
        for item in capabilities.get("inventory", [])
        if isinstance(item.get("targets"), list)
        and set(declaration["targets"]).intersection(item["targets"])
    ]
    if len(matching) != 1:
        raise FirmwareReviewError(
            "HPE's signed file does not name this iLO."
            if not matching
            else "HPE's signed file matches more than one installed item, so the target is unclear."
        )
    item = matching[0]
    # iLO 5 1.x inventory omits Updateable (null); only an explicit refusal blocks. The exact
    # signed-target match above is still required. Observed on iLO 5 1.37, 2026-09-29.
    if item.get("updateable") is False:
        raise FirmwareReviewError("The iLO reports that its firmware can't be updated right now.")
    if item.get("updateable") is not None and item.get("updateable") is not True:
        raise FirmwareReviewError("The iLO reported an invalid Updateable value. Read it again.")
    if item.get("device_class") is not None and item["device_class"] != declaration.get(
        "device_class"
    ):
        raise FirmwareReviewError(
            "HPE's signed file is for a different kind of device than this iLO."
        )
    # Inventory says "1.37 Oct 25 2018" where the manager says "iLO 5 v1.37": compare the numbers.
    inventory_version = numeric_version(str(item.get("version") or ""), "ilo")
    manager_version = numeric_version(
        str(capabilities.get("manager_firmware_version") or ""), "ilo"
    )
    if inventory_version is None or inventory_version != manager_version:
        raise FirmwareReviewError(
            f"The iLO's firmware list ({item.get('version') or 'no version'}) and its own version "
            f"({capabilities.get('manager_firmware_version') or 'no version'}) disagree. Check again."
        )
    installed = capabilities["manager_firmware_version"]
    blockers = ilo_upgrade_blockers(installed, target, binary.get("size_bytes"))
    if blockers:
        raise FirmwareReviewError(" ".join(blockers))
    return {
        "profile_id": profile_id,
        "device_id": device_id,
        "package_selection_id": selection_id,
        "operation": "ilo-firmware-update",
        "target_identity_sha256": capabilities["target_identity_sha256"],
        "target_hardware_identity_sha256": capabilities.get("target_hardware_identity_sha256"),
        "target_fingerprint": capabilities["target_fingerprint"],
        "http_push_uri": capabilities["http_push_uri"],
        "component_sha256": bridge["sha256"],
        "binary_sha256": binary["sha256"],
        "binary_size_bytes": binary["size_bytes"],
        "target_version": target,
        "installed_version": installed,
        "manager_model": capabilities.get("manager_model"),
        "server_model": capabilities.get("server_model"),
        "ilo_reset_expected": True,
        "host_reboot_authorized": False,
        "ilo_update_health": assessment,
    }


@dataclass(frozen=True)
class UploadHandle:
    config: object = field(repr=False)
    binary: bytes = field(repr=False)


class HpeFirmwareAdapter:
    def __init__(self, session):
        self.session = session

    def prepare(self, review):
        blockers = current_lab_action_policy().action_blockers(
            "ilo.firmware-update", ActionCategory.FIRMWARE_UPDATE
        )
        if blockers:
            raise FirmwareReviewError(" ".join(blockers))
        if not firmware_only():
            raise FirmwareReviewError(
                "An exclusive firmware maintenance runtime is required; competing hardware writes must be disabled."
            )
        intent = json.loads(review.intent_json)
        selected = self.session.scalar(
            select(AuditEvent)
            .where(
                AuditEvent.event_type == "kit.firmware_package_selected",
                AuditEvent.data_json["profile_id"].as_string() == review.profile_id,
            )
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(1)
        )
        if selected is None or selected.id != intent.get("package_selection_id"):
            raise FirmwareReviewError("The selected SPP changed since review.")
        package = selected.data_json["package"]
        component = ilo_component(intent.get("target_version"))
        bridge = (
            inspect_spp_bridge(package)
            if component.version == "1.48"
            else inspect_spp_bridge(package, component.version)
        )
        authentication = verify_bridge_from_spp(package, bridge)
        capabilities = collect_firmware_capabilities(self.session, review.device_id)
        current = bridge_intent(
            review.profile_id, review.device_id, selected.id, bridge, authentication, capabilities
        )
        if canonical_intent(current) != review.intent_json:
            raise FirmwareReviewError("Firmware target, version, package or prerequisite changed.")
        config = ilo_config_for_device(self.session, review.device_id)
        if (
            not config.configured
            or config.fallback_hosts
            or ilo_target_fingerprint(config.host) != current["target_fingerprint"]
        ):
            raise FirmwareReviewError(
                "An exact configured iLO target without fallbacks is required."
            )
        iso = pycdlib.PyCdlib()
        try:
            iso.open(str(media_path(package["path"])))
            with (
                iso.open_file_from_iso(rr_path=bridge["path"]) as stream,
                ZipFile(stream) as archive,
            ):
                member = archive.getinfo(component.filename)
                if (
                    member.file_size != current["binary_size_bytes"]
                    or member.file_size > 64 * 1024**2
                ):
                    raise FirmwareReviewError("Reviewed binary size changed.")
                with archive.open(member) as source:
                    binary = source.read(member.file_size + 1)
            if (
                len(binary) != current["binary_size_bytes"]
                or hashlib.sha256(binary).hexdigest() != current["binary_sha256"]
                or not package_unchanged(package)
            ):
                raise FirmwareReviewError("Reviewed firmware bytes changed.")
        finally:
            iso.close()
        return PreparedFirmware(canonical_intent(current), (), UploadHandle(config, binary))

    def send(self, prepared):
        """Called only after the committed dispatch claim; session creation is not a flash."""
        progress = {"stage": "authorization", "upload_started": False}
        try:
            self._send(prepared, progress)
        except Exception as exc:
            facts = (
                exc.facts if isinstance(exc, FirmwareUploadError) else progress.get("response", {})
            )
            facts = dict(facts)
            reason = facts.pop("reason", exception_kind(exc))
            raise FirmwareDispatchError(
                stage=progress["stage"],
                upload_started=progress["upload_started"],
                facts=facts,
                reason=reason,
            ) from None

    def _send(self, prepared, progress):
        blockers = current_lab_action_policy().action_blockers(
            "ilo.firmware-update", ActionCategory.FIRMWARE_UPDATE
        )
        if blockers or not firmware_only():
            raise FirmwareReviewError("Firmware maintenance authorization changed; no upload sent.")
        intent = json.loads(prepared.intent_json)
        config = prepared.handle.config
        base = _base_url(config.host)
        with dispatch_lease("ilo.firmware-update"), client_for(config) as client:
            progress["stage"] = "session_discovery"
            root = client.get(base + "/redfish/v1/", follow_redirects=False, timeout=30.0)
            progress["response"] = response_facts(root)
            root.raise_for_status()
            service = _resource_path(root.json()["SessionService"]["@odata.id"])
            response = client.get(base + service, follow_redirects=False, timeout=30.0)
            progress["response"] = response_facts(response)
            response.raise_for_status()
            sessions = _resource_path(response.json()["Sessions"]["@odata.id"])
            if not sessions.startswith(service.rstrip("/") + "/"):
                raise FirmwareReviewError("Session collection is outside the discovered service.")
            progress.update(stage="session_creation", response={})
            login = client.post(
                base + sessions,
                json={"UserName": config.username, "Password": config.password},
                follow_redirects=False,
                timeout=30.0,
            )
            progress["response"] = response_facts(login)
            if login.status_code != 201:
                raise FirmwareReviewError("iLO session creation was not confirmed; no upload sent.")
            token = login.headers.get("X-Auth-Token", "")
            location = login.headers.get("Location", "")
            try:
                # A usable fresh token is required before crossing the upload boundary.
                import re

                if not re.fullmatch(r"[A-Za-z0-9._~-]{1,1024}", token):
                    raise FirmwareReviewError(
                        "Session token is missing or invalid; no upload sent."
                    )
                progress.update(stage="upload", upload_started=True, response={})
                upload_ilo_binary(
                    client,
                    host=config.host,
                    http_push_uri=intent["http_push_uri"],
                    session_token=token,
                    filename=ilo_component(intent["target_version"]).filename,
                    binary=prepared.handle.binary,
                    expected_sha256=intent["binary_sha256"],
                    installed_version=intent["installed_version"],
                    target_version=intent["target_version"],
                )
            finally:
                # Never follow a session Location off-target, even during cleanup.
                try:
                    path = _resource_path(location)
                    if token and path.startswith(sessions.rstrip("/") + "/"):
                        client.delete(
                            base + path, headers={"X-Auth-Token": token}, follow_redirects=False
                        )
                except Exception:
                    pass
