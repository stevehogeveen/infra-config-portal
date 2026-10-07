"""Read-only qualification of the supplied HPE automatic-boot environments.

This inspects bytes, never boots media. Recognized boot configuration is not a
vendor signature or a declaration that every bundled component fits the target.
"""

import hashlib
import re
import os
import json
from datetime import UTC, datetime
from functools import lru_cache
from urllib.parse import quote, urlparse
from dataclasses import dataclass

import pycdlib

from app.services.firmware_packages import FirmwarePackageError, media_path, package_unchanged

BOOT_PROFILES = {
    "/efi/boot/grub.cfg": "228b5cd9456ee8d44efcfac021612542ad8d4d7dc83d3e26186eff99f2881300",
    "/boot/grub/grub.cfg": "228b5cd9456ee8d44efcfac021612542ad8d4d7dc83d3e26186eff99f2881300",
    "/system/isolinux.cfg": "f5447c3c6dbf8187f8da8c6d0d3c26992794c4a8de79cdf2da7813e8cc5c9908",
}


@dataclass(frozen=True)
class BootProfile:
    release: str
    manager_generation: int
    timeout_seconds: int
    automatic: bool
    reboot_on_success: bool
    configuration_sha256: str
    files: tuple[tuple[str, str], ...]


def qualify_configs(configs: dict[str, bytes], manager_generation: int) -> BootProfile:
    if manager_generation not in {5, 6}:
        raise FirmwarePackageError(
            "This manager requires a separately supported SPP execution route."
        )
    if set(configs) != set(BOOT_PROFILES):
        raise FirmwarePackageError(
            "The package does not contain the qualified automatic boot paths."
        )
    releases = set()
    files = []
    for path, data in sorted(configs.items()):
        if not 0 < len(data) <= 65536:
            raise FirmwarePackageError("SPP boot configuration exceeds the inspection limit.")
        try:
            text = data.decode("utf-8")
        except UnicodeError:
            raise FirmwarePackageError("SPP boot configuration is not recognized text.") from None
        versions = re.findall(r"Firmware Update Version (\d{4}\.\d{2}\.\d{2}\.\d{2})", text)
        if not versions:
            raise FirmwarePackageError("SPP boot release is not identified.")
        releases.update(versions)
        normalized = re.sub(r"Version [0-9.]+", "Version RELEASE", text)
        if hashlib.sha256(normalized.encode()).hexdigest() != BOOT_PROFILES[path]:
            raise FirmwarePackageError(
                "SPP automatic boot configuration differs from the qualified vendor profile."
            )
        files.append((path, hashlib.sha256(data).hexdigest()))
    if len(releases) != 1:
        raise FirmwarePackageError("SPP boot paths disagree on the release.")
    combined = hashlib.sha256(
        "\n".join(f"{path}:{digest}" for path, digest in files).encode()
    ).hexdigest()
    return BootProfile(
        next(iter(releases)), manager_generation, 10, True, True, combined, tuple(files)
    )


def inspect_boot_profile(package: dict, manager_generation: int) -> BootProfile:
    if not package_unchanged(package):
        raise FirmwarePackageError("Selected SPP changed; select the package again.")
    iso = pycdlib.PyCdlib()
    try:
        iso.open(str(media_path(package["path"])))
        configs = {}
        for path in BOOT_PROFILES:
            record = iso.get_record(rr_path=path)
            if record.is_symlink() or not 0 < record.data_length <= 65536:
                raise FirmwarePackageError("SPP boot configuration is not a bounded regular file.")
            with iso.open_file_from_iso(rr_path=path) as source:
                configs[path] = source.read(65537)
        for path in ("/system/vmlinuz", "/system/initrd.img", "/efi/boot/bootx64.efi"):
            record = iso.get_record(rr_path=path)
            if record.is_symlink() or record.data_length <= 0:
                raise FirmwarePackageError("SPP boot payload is missing or redirected.")
        result = qualify_configs(configs, manager_generation)
        if not package_unchanged(package):
            raise FirmwarePackageError("Selected SPP changed during boot inspection.")
        return result
    except FirmwarePackageError:
        raise
    except Exception:
        raise FirmwarePackageError(
            "Selected SPP has no qualified automatic boot environment."
        ) from None
    finally:
        try:
            iso.close()
        except Exception:
            pass


@lru_cache(maxsize=4)
def _iso_hash(path, identity):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def package_hash(package):
    path = media_path(package["path"])
    before = path.stat()
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    result = _iso_hash(str(path), identity)
    after = path.stat()
    if identity != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise FirmwarePackageError("SPP changed while its identity was being read.")
    return result


def _components(probe):
    drives = probe.get("storage", {}).get("physical_drives") or []
    identities = [
        {k: drive.get(k) for k in ("Id", "Model", "SerialNumber", "Location")}
        for drive in drives
        if drive.get("Model")
    ]
    return hashlib.sha256(
        json.dumps(
            sorted(identities, key=lambda d: json.dumps(d, sort_keys=True)),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


class CommandNotSent(FirmwarePackageError):
    """Transport failed before entering any hardware write call."""


class OfflineTransport:
    """Explicitly approved lab boot commands, using saved exact-device credentials."""

    def available(self, session, profile_id, device_id):
        from app.core.config import settings
        from app.services.firmware_flow import _latest
        from app.services.ilo_access_settings import ilo_config_for_device

        row = _latest(session, "kit.firmware_package_selected", profile_id)
        return bool(
            settings.provider_mode == "local-lab-readwrite"
            and row
            and package_unchanged(row.data_json["package"])
            and ilo_config_for_device(session, device_id).configured
        )

    def _config(self, session, device_id):
        from app.core.config import settings
        from app.providers.action_policy import current_lab_action_policy
        from app.services.ilo_access_settings import ilo_config_for_device
        from app.services.runtime_write_scope import runtime_override

        if (
            settings.provider_mode != "local-lab-readwrite"
            or current_lab_action_policy().readonly_blockers()
        ):
            raise FirmwarePackageError(
                "Offline SPP requires the explicitly configured local lab provider."
            )
        if runtime_override() not in {"read_only", "firmware_only"}:
            raise FirmwarePackageError(
                "Finish other hardware work and return to read-only before SPP maintenance."
            )
        config = ilo_config_for_device(session, device_id)
        if not config.configured or config.fallback_hosts:
            raise FirmwarePackageError("An exact saved iLO target is required.")
        return config

    def capture(self, session, profile_id, device_id):
        try:
            return self._capture(session, profile_id, device_id)
        except FirmwarePackageError:
            raise
        except Exception:
            raise FirmwarePackageError(
                "The app could not read the selected server and SPP completely. Check the saved connection and media, then review again."
            ) from None

    def _capture(self, session, profile_id, device_id):
        from app.api.firmware_review import server_in_kit
        from app.providers.ilo_redfish import (
            IloRedfishAdapter,
            ilo_target_fingerprint,
            _resource_summary,
        )
        from app.providers.hpe_firmware_inventory import _hardware_identity, discover_update_service
        from app.providers.hpe_storage_rebuild import client_for
        from app.services import esxi_boot_workflow as boot
        from app.services.firmware_flow import _latest
        from app.services.spp_assessment import load_catalog, assess

        server = server_in_kit(profile_id, device_id, session)
        config = self._config(session, device_id)
        selected = _latest(session, "kit.firmware_package_selected", profile_id)
        if not selected or not package_unchanged(selected.data_json["package"]):
            raise FirmwarePackageError("Select a complete SPP ISO before reviewing the update.")
        package = selected.data_json["package"]
        probe = IloRedfishAdapter(config=config).probe()
        if (
            probe.get("status") != "ok"
            or len(probe.get("systems") or []) != 1
            or len(probe.get("managers") or []) != 1
        ):
            raise FirmwarePackageError("A complete exact-server inventory is required.")
        hardware_identity = _hardware_identity(probe)
        if not hardware_identity:
            raise FirmwarePackageError(
                "The server did not return a stable UUID and serial identity."
            )
        manager = probe["managers"][0]
        generation = re.search(
            r"\biLO\s*(\d+)\b",
            str(manager.get("Model", "")) + " " + str(manager.get("FirmwareVersion", "")),
            re.I,
        )
        if not generation:
            raise FirmwarePackageError("The detected iLO generation is not identified.")
        generation = int(generation[1])
        profile = inspect_boot_profile(package, generation)
        comparison = assess(load_catalog(package), probe, server.model)
        if not comparison.get("rom_family"):
            raise FirmwarePackageError(
                "This detected server is not supported by the selected SPP manifest."
            )
        system = boot._body(boot._get_redfish_resource(boot.SYSTEM_PATH, config=config))
        if _hardware_identity({"systems": [_resource_summary(system)]}) != hardware_identity:
            raise FirmwarePackageError("The system identity changed during inventory.")
        if system.get("PowerState") not in {"On", "Off"}:
            raise FirmwarePackageError("Server power state is not established.")
        with client_for(config) as client:
            update = discover_update_service(client, boot._base_url(config.host))
        media = boot._select_virtual_media_device(config=config)
        media_body = boot._body(boot._get_redfish_resource(media["path"], config=config))
        path = media_path(package["path"])
        base = os.getenv("SPP_MEDIA_BASE_URL") or os.getenv("ESXI_MEDIA_BASE_URL")
        if not base:
            host = os.getenv("ESXI_MEDIA_HTTP_HOST") or boot._source_ip_for_ilo(config)
            base = f"http://{host}:{os.getenv('ESXI_MEDIA_HTTP_PORT', '8088')}"
        parsed = urlparse(base)
        if (
            parsed.scheme != "http"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise FirmwarePackageError(
                "The lab media service must have a plain HTTP base URL without credentials."
            )
        rows = comparison["rows"]
        expected = [
            {
                "component": row["component"],
                "installed": row["installed"],
                "target": row["target"],
                "kind": "drive"
                if row.get("group") == "Drive"
                else "ilo"
                if row["component"] == "iLO"
                else "numeric",
            }
            for row in rows
            if row["status"] == "Update available"
        ]
        if len({row["component"] for row in rows}) != len(rows):
            raise FirmwarePackageError("Firmware component identities are ambiguous.")
        return dict(
            profile_id=profile_id,
            device_id=device_id,
            hardware_identity=hardware_identity,
            endpoint_identity=ilo_target_fingerprint(config.host),
            component_identity=_components(probe),
            package_sha256=package_hash(package),
            boot_profile=profile.configuration_sha256,
            media_path=package["path"],
            selected_package=package,
            media_url=base.rstrip("/") + "/" + quote(path.name),
            media_device=media,
            media_inserted=media_body.get("Inserted"),
            media_image=media_body.get("Image"),
            post_timestamp=system.get("Oem", {})
            .get("Hpe", {})
            .get("PostDiscoveryCompleteTimeStamp"),
            post_state=system.get("Oem", {}).get("Hpe", {}).get("PostState"),
            boot_override=system.get("Boot", {}),
            power_state=system["PowerState"],
            expected=expected,
            rows=rows,
            update_idle=update.get("state") in {"Idle", "Complete"} and update.get("errors") == [],
            update_state=update.get("state"),
            update_errors=bool(update.get("errors")),
            server={
                "name": server.name,
                "model": comparison["detected_model"],
                "manager_generation": generation,
            },
            package={"file": package["file_name"], "release": profile.release},
            unassessed=[
                {"component": row["component"], "reason": row["reason"]}
                for row in rows
                if row["status"] == "Cannot determine"
            ],
        )

    def preflight(self, session, device_id, facts, phase):
        fresh = self.capture(session, facts["profile_id"], device_id)
        for key in (
            "hardware_identity",
            "endpoint_identity",
            "component_identity",
            "package_sha256",
            "boot_profile",
            "media_url",
            "media_device",
        ):
            if fresh[key] != facts[key]:
                raise FirmwarePackageError("The reviewed target or media changed before dispatch.")
        if fresh["media_inserted"] is True and fresh["media_image"] != facts["media_url"]:
            raise FirmwarePackageError(
                "Another virtual-media image is connected; it will not be replaced."
            )
        if phase in {"boot", "reset"} and (
            fresh["media_inserted"] is not True or fresh["media_image"] != facts["media_url"]
        ):
            raise FirmwarePackageError(
                "The selected SPP is no longer mounted; no boot command was sent."
            )
        if phase == "reset" and (
            fresh["boot_override"].get("BootSourceOverrideEnabled") != "Once"
            or fresh["boot_override"].get("BootSourceOverrideTarget") != "Cd"
        ):
            raise FirmwarePackageError(
                "One-time SPP boot is no longer selected; no restart was sent."
            )
        if phase in {"media", "boot", "reset"} and fresh["expected"] != facts["expected"]:
            raise FirmwarePackageError(
                "The reviewed firmware targets changed before the updater started."
            )
        if phase != "eject" and not fresh["update_idle"]:
            raise FirmwarePackageError("An existing firmware update is still active.")
        if phase == "eject" and (
            not fresh["update_idle"] or not self._versions_match(facts, fresh)
        ):
            raise FirmwarePackageError(
                "The listed firmware versions are not currently verified; media remains connected."
            )

    def dispatch(self, session, device_id, facts, phase):
        sent = False

        def send(function, *args, **kwargs):
            nonlocal sent
            sent = True
            return function(*args, **kwargs)

        try:
            return self._dispatch(session, device_id, facts, phase, send)
        except Exception:
            if not sent:
                raise CommandNotSent(
                    "Preparation could not finish; no hardware command was sent for this phase. Check the saved connection and ISO media service."
                ) from None
            raise

    def _dispatch(self, session, device_id, facts, phase, send):
        import httpx
        from app.services import esxi_boot_workflow as boot
        from app.providers.hpe_firmware_inventory import _resource_path, _hardware_identity
        from app.providers.ilo_redfish import ilo_target_fingerprint, _resource_summary

        config = self._config(session, device_id)
        if ilo_target_fingerprint(config.host) != facts["endpoint_identity"]:
            raise FirmwarePackageError("The saved endpoint changed.")
        system = boot._body(boot._get_redfish_resource(boot.SYSTEM_PATH, config=config))
        if (
            _hardware_identity({"systems": [_resource_summary(system)]})
            != facts["hardware_identity"]
        ):
            raise FirmwarePackageError("The server identity changed before dispatch.")
        media = facts["media_device"]
        _resource_path(media["path"])
        _resource_path(media["insert_target"])
        checked = datetime.now(UTC).isoformat()
        if phase == "media":
            package = facts["selected_package"]
            path = media_path(facts["media_path"])
            if package_hash(package) != facts["package_sha256"]:
                raise FirmwarePackageError("The selected ISO changed.")
            if not (os.getenv("SPP_MEDIA_BASE_URL") or os.getenv("ESXI_MEDIA_BASE_URL")):
                from app.providers.spp_media_server import ensure_media_server

                ensure_media_server(path.parent, int(os.getenv("ESXI_MEDIA_HTTP_PORT", "8088")))
            validation = boot._validate_media_url(facts["media_url"], package["size_bytes"])
            if not validation.get("reachable") or validation.get("same_size") is not True:
                raise FirmwarePackageError(
                    "The selected SPP is not reachable from the media service."
                )
            # Check the served bytes, not merely a same-sized file or an existing listener.
            digest = hashlib.sha256()
            size = 0
            with httpx.stream(
                "GET", facts["media_url"], timeout=60, follow_redirects=False, trust_env=False
            ) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(1024**2):
                    size += len(chunk)
                    if size > package["size_bytes"]:
                        raise FirmwarePackageError("The media service returned a different ISO.")
                    digest.update(chunk)
            if size != package["size_bytes"] or digest.hexdigest() != facts["package_sha256"]:
                raise FirmwarePackageError("The served ISO does not match the approved bytes.")
            result = send(boot._post_virtual_media_action, media, facts["media_url"], config=config)
        elif phase == "boot":
            result = send(
                boot._patch_system_boot,
                {"Boot": {"BootSourceOverrideEnabled": "Once", "BootSourceOverrideTarget": "Cd"}},
                config=config,
            )
        elif phase == "reset":
            result = send(
                boot._post_system_reset,
                "On" if system.get("PowerState") == "Off" else "ForceRestart",
                config=config,
            )
        elif phase == "eject":
            body = boot._body(boot._get_redfish_resource(media["path"], config=config))
            if body.get("Inserted") is False:
                return {"checked_at": checked, "already_disconnected": True}
            if body.get("Image") != facts["media_url"]:
                raise FirmwarePackageError("Different media is connected; it will not be ejected.")
            target = (body.get("Actions", {}).get("#VirtualMedia.EjectMedia") or {}).get("target")
            result = send(boot._post_redfish, _resource_path(target), {}, config=config)
        else:
            raise FirmwarePackageError("Unknown offline-SPP command.")
        if result.get("status_code") not in {200, 202, 204}:
            raise FirmwarePackageError("The server did not accept the reviewed SPP action.")
        if phase in {"media", "eject"}:
            body = boot._body(boot._get_redfish_resource(media["path"], config=config))
            if phase == "media" and (
                body.get("Inserted") is not True or body.get("Image") != facts["media_url"]
            ):
                raise FirmwarePackageError("Virtual-media insertion is not yet confirmed.")
            if phase == "eject" and body.get("Inserted") is not False:
                raise FirmwarePackageError("Virtual-media removal is not yet confirmed.")
        if phase == "boot":
            state = boot._body(boot._get_redfish_resource(boot.SYSTEM_PATH, config=config)).get(
                "Boot", {}
            )
            if (
                state.get("BootSourceOverrideEnabled") != "Once"
                or state.get("BootSourceOverrideTarget") != "Cd"
            ):
                raise FirmwarePackageError("One-time SPP boot is not yet confirmed.")
        return {"checked_at": checked, "status_code": result["status_code"]}

    def _versions_match(self, facts, fresh):
        from app.services.spp_assessment import numeric_version

        rows = {row["component"]: row for row in fresh["rows"]}
        matches = all(
            expected["component"] in rows
            and numeric_version(
                str(rows[expected["component"]].get("installed") or ""), expected["kind"]
            )
            is not None
            and numeric_version(
                str(rows[expected["component"]].get("installed") or ""), expected["kind"]
            )
            == numeric_version(expected["target"], expected["kind"])
            for expected in facts["expected"]
        )
        return bool(facts["expected"]) and matches

    def _parts(self, facts, fresh):
        from app.services.spp_assessment import numeric_version

        rows = {row["component"]: row for row in fresh["rows"]}
        parts = []
        for expected in facts["expected"]:
            installed = str((rows.get(expected["component"]) or {}).get("installed") or "") or None
            found = numeric_version(installed or "", expected["kind"])
            parts.append({
                "component": expected["component"],
                "installed": installed,
                "target": expected["target"],
                "at_target": found is not None
                and found == numeric_version(expected["target"], expected["kind"]),
            })
        return parts

    def _queued(self, session, device_id):
        """Names of firmware tasks the iLO holds for the next restart. Best effort, read-only."""
        from app.services import esxi_boot_workflow as boot

        try:
            config = self._config(session, device_id)
            listing = boot._body(boot._get_redfish_resource("/redfish/v1/UpdateService/UpdateTaskQueue/", config=config))
            names = []
            for member in (listing.get("Members") or [])[:64]:
                task = boot._body(boot._get_redfish_resource(member["@odata.id"], config=config))
                if str(task.get("State") or "") in {"Pending", "InProgress", "Running"}:
                    name = re.sub(r"\s+", " ", str(task.get("Name") or "")).strip()
                    name = re.sub(r"^(ROM Flash )?Firmware Package\s*-\s*", "", name)
                    if name and not name.lower().startswith("wait task"):
                        names.append(name[:120])
            return names
        except Exception:
            return []

    def observe(self, session, device_id, facts):
        fresh = self.capture(session, facts["profile_id"], device_id)
        return {
            "checked_at": datetime.now(UTC).isoformat(),
            "hardware_identity": fresh["hardware_identity"],
            "component_identity": fresh["component_identity"],
            "post_timestamp": fresh["post_timestamp"],
            "update_idle": fresh["update_idle"],
            "versions_match": self._versions_match(facts, fresh),
            "power": fresh.get("power_state"),
            "post_state": fresh.get("post_state"),
            "update_state": fresh.get("update_state"),
            "update_errors": fresh.get("update_errors", False),
            "parts": self._parts(facts, fresh),
            "media_inserted": fresh["media_inserted"],
            "queued": self._queued(session, device_id),
        }

    def reconcile_phase(self, session, device_id, facts, phase):
        fresh = self.capture(session, facts["profile_id"], device_id)
        identity = all(
            fresh[key] == facts[key]
            for key in (
                "hardware_identity",
                "endpoint_identity",
                "component_identity",
                "package_sha256",
                "boot_profile",
                "media_url",
                "media_device",
            )
        )
        applied = False
        mounted = fresh["media_inserted"] is True and fresh["media_image"] == facts["media_url"]
        if identity:
            if phase == "media":
                applied = mounted
            elif phase == "boot":
                applied = (
                    mounted
                    and fresh["boot_override"].get("BootSourceOverrideEnabled") == "Once"
                    and fresh["boot_override"].get("BootSourceOverrideTarget") == "Cd"
                )
            elif phase == "reset":
                try:
                    latest = datetime.fromisoformat(fresh["post_timestamp"].replace("Z", "+00:00"))
                    original = datetime.fromisoformat(
                        facts["post_timestamp"].replace("Z", "+00:00")
                    )
                    applied = bool(
                        mounted
                        and latest.tzinfo
                        and original.tzinfo
                        and latest > original
                        and fresh["boot_override"].get("BootSourceOverrideEnabled") == "Disabled"
                    )
                except (AttributeError, TypeError, ValueError):
                    applied = False
            elif phase == "eject":
                applied = fresh["media_inserted"] is False and fresh["update_idle"]
        return {
            "applied": applied,
            "checked_at": datetime.now(UTC).isoformat(),
            "post_timestamp": fresh["post_timestamp"],
            "versions_match": self._versions_match(facts, fresh),
        }
