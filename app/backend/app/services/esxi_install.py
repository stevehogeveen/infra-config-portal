"""Per-server ESXi install: choose the ISO, save the host settings, build the unattended
installer, then attach, boot and watch until ESXi answers on its planned address.

Every hardware step uses the server's own saved iLO login, is recorded before it is sent,
is confirmed by reading the server back, and is never sent twice by the app on its own.
The root password is accepted once, kept only as a salted SHA-512 crypt hash in an ignored
local file, and embedded only in the built ISO.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import time
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuditEvent, GuardedOperation, utcnow
from app.services.audit import record_audit_event

ACTION_MEDIA = "ilo-redfish.esxi-virtual-media"
ACTION_BOOT = "ilo-redfish.esxi-boot-once"
ACTION_POWER = "ilo-redfish.esxi-power"
ACTION_DATASTORE = "esxi.datastore-create"
PHASES = ("media", "boot", "power", "eject", "datastore")
DATASTORE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,41}$")
DATASTORE_SETTLE = timedelta(minutes=2)
DEFAULT_DATASTORE = "VMdata"
DERIVED_PREFIX = "esxi-installer-"
HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
NIC = re.compile(r"^vmnic[0-9]{1,2}$")
MAC = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")
VERSION = re.compile(r"ESXi[-_](\d+\.\d+(?:\.\d+)?)(?:[-_.](?:U\d+[a-z]?[-_.])?(\d{6,9}))?", re.I)
# Seconds the installer has to bring ESXi up before the run asks for a look at the console.
INSTALL_WINDOW = timedelta(minutes=60)


class EsxiInstallError(ValueError):
    """A plain, operator-facing reason the request cannot proceed. Nothing was sent."""


# ---------------------------------------------------------------- records


def _latest(session: Session, event_type: str, **match: str) -> AuditEvent | None:
    query = select(AuditEvent).where(AuditEvent.event_type == event_type)
    for key, value in match.items():
        query = query.where(AuditEvent.data_json[key].as_string() == value)
    return session.scalar(
        query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(1)
    )


def _events(session: Session, event_type: str, **match: str) -> list[AuditEvent]:
    query = select(AuditEvent).where(AuditEvent.event_type == event_type)
    for key, value in match.items():
        query = query.where(AuditEvent.data_json[key].as_string() == value)
    return list(session.scalars(query.order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())))


def _record(
    session: Session, actor: str, event_type: str, message: str, data: dict[str, Any]
) -> AuditEvent:
    if event_type == "kit.esxi_install.result":
        phase = data["phase"]
        previous = {
            "media": "accepted",
            "boot": "esxi-ok-media",
            "power": "esxi-ok-boot",
            "eject": "esxi-ok-power",
            "datastore": "esxi-ok-eject",
        }[phase]
        session.execute(
            update(GuardedOperation)
            .where(
                GuardedOperation.id == data["run_id"],
                GuardedOperation.active_device.is_not(None),
                GuardedOperation.status.in_(
                    [
                        previous,
                        f"esxi-sent-{phase}",
                        f"esxi-uncertain-{phase}",
                        f"esxi-failed-{phase}",
                    ]
                ),
            )
            .values(status=f"esxi-{data['outcome']}-{data['phase']}", updated_at=utcnow())
        )
    elif event_type == "kit.esxi_install.done":
        session.execute(
            update(GuardedOperation)
            .where(
                GuardedOperation.id == data["run_id"],
            )
            .values(
                status="closed-unverified"
                if data.get("closed")
                else "verified"
                if data.get("verified_at")
                else "reachable-unverified",
                active_device=None,
                updated_at=utcnow(),
            )
        )
    event = record_audit_event(
        session, actor=actor, event_type=event_type, message=message, data=data
    )
    session.commit()
    return event


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------- media


def _media_root() -> Path:
    from app.services.firmware_packages import media_root

    return media_root()


def _esxi_iso_facts(path: Path) -> dict[str, Any] | None:
    """Read only the ISO directory: an ESXi installer carries /BOOT.CFG and the /B.B00 kernel."""
    import pycdlib

    iso = pycdlib.PyCdlib()
    try:
        iso.open(str(path))
        names: set[str] = set()
        for _, _, files in iso.walk(iso_path="/"):
            names.update(name.split(";")[0].upper() for name in files)
            break
        kernel = ""
        if "BOOT.CFG" in names:
            from io import BytesIO

            buffer = BytesIO()
            iso.get_file_from_iso_fp(buffer, iso_path="/BOOT.CFG;1")
            text = buffer.getvalue().decode("ascii", "replace")
            kernel = next(
                (
                    line.split("=", 1)[1].strip()
                    for line in text.splitlines()
                    if line.startswith("kernel=")
                ),
                "",
            )
        return {
            "esxi": "BOOT.CFG" in names and "B.B00" in names and "b.b00" in kernel.lower(),
            "volume": iso.pvd.volume_identifier.decode("ascii", "replace").strip(),
        }
    except Exception:
        return None
    finally:
        try:
            iso.close()
        except Exception:
            pass


def _version_hint(name: str) -> str | None:
    match = VERSION.search(name)
    if not match:
        return None
    return match.group(1) + (f" build {match.group(2)}" if match.group(2) else "")


_iso_cache: dict[tuple[str, int, int], dict[str, Any] | None] = {}


def list_media(session: Session, profile_id: str, device_id: str) -> dict[str, Any]:
    root = _media_root()
    result: dict[str, Any] = {
        "root_ready": root.is_dir(),
        "isos": [],
        "selected": None,
        "folder": "",
    }
    if root.is_dir():
        candidates = list(root.glob("*.iso")) + list(root.glob("*/*.iso"))
        for path in sorted(candidates, key=lambda item: item.name.lower()):
            if (
                path.name.startswith((DERIVED_PREFIX, "."))
                or path.is_symlink()
                or not path.is_file()
            ):
                continue
            stat = path.stat()
            key = (str(path), stat.st_size, int(stat.st_mtime))
            if key not in _iso_cache:
                _iso_cache[key] = _esxi_iso_facts(path)
            facts = _iso_cache[key]
            if not facts or not facts["esxi"]:
                continue
            result["isos"].append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "name": path.name,
                    "size_bytes": stat.st_size,
                    "version": _version_hint(path.name),
                    "hpe_image": "hpe" in path.name.lower(),
                }
            )
    row = _latest(session, "kit.esxi_media_selected", profile_id=profile_id, device_id=device_id)
    if row:
        selected = row.data_json
        result["selected"] = {
            "path": selected["path"],
            "name": selected["name"],
            "size_bytes": selected["size_bytes"],
            "selected_at": row.created_at.replace(tzinfo=UTC).isoformat(),
            "present": any(
                item["path"] == selected["path"] and item["size_bytes"] == selected["size_bytes"]
                for item in result["isos"]
            ),
        }
    return result


def select_media(
    session: Session, profile_id: str, device_id: str, relative: str, actor: str
) -> dict[str, Any]:
    from app.services.firmware_packages import FirmwarePackageError, media_path

    try:
        path = media_path(relative)
    except FirmwarePackageError as exc:
        raise EsxiInstallError(str(exc)) from None
    if path.name.startswith(DERIVED_PREFIX) or not path.is_file() or path.suffix.lower() != ".iso":
        raise EsxiInstallError("Choose an ESXi installer ISO from the media folder.")
    facts = _esxi_iso_facts(path)
    if not facts or not facts["esxi"]:
        raise EsxiInstallError("That ISO is not an ESXi installer (no ESXi boot files were found).")
    stat = path.stat()
    _record(
        session,
        actor,
        "kit.esxi_media_selected",
        "ESXi installer ISO selected; nothing sent to hardware.",
        {
            "profile_id": profile_id,
            "device_id": device_id,
            "path": path.relative_to(_media_root()).as_posix(),
            "name": path.name,
            "size_bytes": stat.st_size,
            "mtime": int(stat.st_mtime),
        },
    )
    return list_media(session, profile_id, device_id)


# ---------------------------------------------------------------- settings


def _secret_path(device_id: str) -> Path:
    from app.services.hpe_raid import REPO_ROOT

    safe = re.sub(r"[^A-Za-z0-9._-]", "_", device_id)
    return REPO_ROOT / ".local" / "esxi" / f"{safe}.sha512crypt"


def _root_password_path(device_id: str) -> Path:
    return _secret_path(device_id).with_suffix(".root")


def _root_password(device_id: str) -> str | None:
    path = _root_password_path(device_id)
    return path.read_text(encoding="utf-8").rstrip("\n") if path.is_file() else None


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(text, encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _hash_password(password: str) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import crypt

        return crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512))


def _password_problem(password: str) -> str | None:
    classes = sum(
        bool(re.search(pattern, password))
        for pattern in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]")
    )
    if len(password) < 8 or classes < 3:
        return "Use at least 8 characters with three of: lowercase, uppercase, digits, symbols (ESXi's password rule)."
    if len(password) > 64 or any(ord(char) < 32 for char in password):
        return "Use at most 64 printable characters."
    return None


def _kit(context: dict[str, Any]) -> dict[str, Any]:
    active = context.get("active_profile") or {}
    plan = context.get("resolved_address_plan") or {}
    settings = active.get("global_settings") or {}
    features = context.get("enabled_features") or active.get("features") or {}
    ntp_enabled = features.get("enable_ntp") is not False
    return {
        "profile_id": active.get("id"),
        "profile_version": active.get("version"),
        "saved_profile": active.get("source") == "saved" and active.get("id") != "runtime",
        "subnet": plan.get("subnet") or active.get("subnet_cidr"),
        "gateway": settings.get("gateway") or active.get("gateway"),
        "dns": [str(item) for item in (settings.get("dns_servers") or active.get("dns") or [])],
        "ntp_enabled": ntp_enabled,
        "ntp": [str(item) for item in (settings.get("ntp_servers") or active.get("ntp") or [])]
        if ntp_enabled
        else [],
        "domain_name": str(settings.get("domain_name") or "").strip().strip(".") or None,
        "esxi_management": plan.get("esxi_management"),
        "single_server_local": features.get("deployment_mode") == "single_server_local_storage"
        and features.get("storage_location") == "server_local",
    }


def _boot_volume(session: Session, device_id: str, *, probe_result=None) -> dict[str, Any] | None:
    """The saved plan's RAID 1 boot mirror, from the last recorded iLO read of this server."""
    from app.providers.probe_cache import get_probe_result
    from app.services.hpe_raid import get_hpe_raid_intent

    probe, checked = get_probe_result("ilo-redfish", scope=device_id)
    if probe_result is not None:
        probe, checked = probe_result, probe_result.get("checked_at")
    storage = (probe or {}).get("storage") or {}
    intent = get_hpe_raid_intent(session, device_id)
    boot = next((volume for volume in intent.volumes if volume.bootable), None)
    if not boot:
        return None
    by_path = {
        str(drive.get("@odata.id") or "").rstrip("/"): str(drive.get("Location") or "")
        for drive in storage.get("physical_drives", [])
    }
    for volume in storage.get("logical_drives", []):
        bays = sorted(
            filter(
                None,
                (
                    by_path.get(str(path).rstrip("/"))
                    for path in volume.get("physical_drive_paths") or []
                ),
            )
        )
        raid = str(volume.get("RAIDType") or "").upper()
        if raid == "RAID1" and bays == sorted(boot.drive_bays):
            uid = str(volume.get("VolumeUniqueIdentifier") or "").strip().lower()
            return {
                "name": volume.get("LogicalDriveName") or f"Logical drive {volume.get('Id')}",
                "bays": bays,
                "capacity_bytes": volume.get("CapacityBytes") or 0,
                "disk_id": f"naa.{uid}" if re.fullmatch(r"[0-9a-f]{16,40}", uid) else None,
                "read_at": checked,
            }
    return None


def _data_volume(session: Session, device_id: str, *, probe_result=None) -> dict[str, Any] | None:
    """The saved plan's datastore volume (RAID 5/6/10/1), from the last recorded iLO read."""
    from app.providers.probe_cache import get_probe_result
    from app.services.hpe_raid import get_hpe_raid_intent

    probe, checked = get_probe_result("ilo-redfish", scope=device_id)
    if probe_result is not None:
        probe, checked = probe_result, probe_result.get("checked_at")
    storage = (probe or {}).get("storage") or {}
    intent = get_hpe_raid_intent(session, device_id)
    data = next((volume for volume in intent.volumes if not volume.bootable), None)
    if not data:
        return None
    by_path = {
        str(drive.get("@odata.id") or "").rstrip("/"): str(drive.get("Location") or "")
        for drive in storage.get("physical_drives", [])
    }
    for volume in storage.get("logical_drives", []):
        bays = sorted(filter(None, (by_path.get(str(path).rstrip("/")) for path in volume.get("physical_drive_paths") or [])))
        if bays == sorted(data.drive_bays):
            uid = str(volume.get("VolumeUniqueIdentifier") or "").strip().lower()
            return {
                "name": volume.get("LogicalDriveName") or f"Logical drive {volume.get('Id')}",
                "raid": str(volume.get("RAIDType") or data.raid_level),
                "bays": bays,
                "capacity_bytes": volume.get("CapacityBytes") or 0,
                "disk_id": f"naa.{uid}" if re.fullmatch(r"[0-9a-f]{16,40}", uid) else None,
                "read_at": checked,
            }
    return None


def get_settings(session: Session, profile_id: str, device_id: str) -> dict[str, Any]:
    from app.services.lab_profiles import active_lab_profile_context

    kit = _kit(active_lab_profile_context())
    row = _latest(session, "kit.esxi_settings_saved", profile_id=profile_id, device_id=device_id)
    saved = dict(row.data_json) if row else {}
    volume = _boot_volume(session, device_id)
    return {
        "hostname": saved.get("hostname"),
        "addressing": saved.get("addressing", "static"),
        "management_ip": saved.get("management_ip"),
        "vlan_id": saved.get("vlan_id", 0),
        "management_nic": saved.get("management_nic"),
        "datastore_name": saved.get("datastore_name", DEFAULT_DATASTORE),
        "password_set": _secret_path(device_id).is_file(),
        "signin_ready": _root_password_path(device_id).is_file(),
        "data_volume": _data_volume(session, device_id),
        "saved_at": row.created_at.replace(tzinfo=UTC).isoformat() if row else None,
        "kit": kit,
        "boot_volume": volume,
    }


def save_settings(
    session: Session, profile_id: str, device_id: str, payload: dict[str, Any], actor: str
) -> dict[str, Any]:
    from app.services.lab_profiles import active_lab_profile_context

    kit = _kit(active_lab_profile_context())
    if kit["profile_id"] != profile_id:
        raise EsxiInstallError(
            "Open this kit first; ESXi settings are saved against the active kit."
        )
    hostname = str(payload.get("hostname") or "").strip().strip(".").lower()
    labels = hostname.split(".")
    if (
        len(labels) < 2
        or any(not HOST_LABEL.fullmatch(label) for label in labels)
        or len(hostname) > 253
    ):
        raise EsxiInstallError("Enter the full host name, for example esxi01.lab.example.")
    if kit["domain_name"] and not hostname.endswith("." + kit["domain_name"].lower()):
        raise EsxiInstallError(
            f"The host name must end in the kit's domain, .{kit['domain_name']}."
        )
    addressing = payload.get("addressing") or "static"
    if addressing not in {"static", "dhcp"}:
        raise EsxiInstallError("Addressing is static or DHCP.")
    address = None
    if addressing == "static":
        try:
            subnet = ipaddress.ip_network(str(kit["subnet"]), strict=False)
            address = ipaddress.ip_address(str(payload.get("management_ip") or "").strip())
        except ValueError:
            raise EsxiInstallError(
                "Enter a valid IPv4 management address inside the kit's subnet."
            ) from None
        if (
            address not in subnet
            or address in {subnet.network_address, subnet.broadcast_address}
            or str(address) == str(kit["gateway"])
        ):
            raise EsxiInstallError(
                f"The management address must be a free host address in {subnet}, not the gateway."
            )
    datastore = str(payload.get("datastore_name") or DEFAULT_DATASTORE).strip()
    if not DATASTORE_NAME.fullmatch(datastore):
        raise EsxiInstallError("Name the datastore with up to 42 letters, digits, spaces, dots, dashes or underscores.")
    vlan = payload.get("vlan_id", 0)
    if not isinstance(vlan, int) or isinstance(vlan, bool) or not 0 <= vlan <= 4094:
        raise EsxiInstallError("VLAN must be 0 (untagged) or 1-4094.")
    nic = str(payload.get("management_nic") or "vmnic0").strip().lower().replace("-", ":")
    if not (NIC.fullmatch(nic) or MAC.fullmatch(nic)):
        raise EsxiInstallError("Choose the network port ESXi manages the host through.")
    password = payload.get("root_password")
    secret = _secret_path(device_id)
    if password:
        problem = _password_problem(str(password))
        if problem:
            raise EsxiInstallError(problem)
        _write_private(secret, _hash_password(str(password)) + "\n")
        # Kept owner-only beside the hash so the app can sign in after install (verification,
        # datastore, later steps). Never returned, logged or put on a command line.
        _write_private(_root_password_path(device_id), str(password) + "\n")
    elif not secret.is_file():
        raise EsxiInstallError("Set the ESXi root password.")
    _record(
        session,
        actor,
        "kit.esxi_settings_saved",
        "ESXi host settings saved; nothing sent to hardware.",
        {
            "profile_id": profile_id,
            "device_id": device_id,
            "hostname": hostname,
            "addressing": addressing,
            "management_ip": str(address) if address else None,
            "vlan_id": vlan,
            "management_nic": nic,
            "datastore_name": datastore,
            "password_changed": bool(password),
        },
    )
    return get_settings(session, profile_id, device_id)


# ---------------------------------------------------------------- build


def _settings_digest(saved: dict[str, Any], password_hash: str) -> str:
    material = {
        key: saved.get(key) for key in ("hostname", "management_ip", "vlan_id", "management_nic")
    }
    if saved.get("addressing", "static") != "static":
        material["addressing"] = saved.get("addressing")
    material["password"] = hashlib.sha256(password_hash.encode()).hexdigest()
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


def _build_inputs(session: Session, profile_id: str, device_id: str) -> dict[str, Any]:
    """Everything a build needs, or the plain list of what is missing."""
    from app.services.lab_profiles import active_lab_profile_context

    context = active_lab_profile_context()
    kit = _kit(context)
    settings = get_settings(session, profile_id, device_id)
    media = list_media(session, profile_id, device_id)["selected"]
    row = _latest(session, "kit.esxi_settings_saved", profile_id=profile_id, device_id=device_id)
    missing = []
    if not media or not media["present"]:
        missing.append("Choose the ESXi installer ISO.")
    if not row or not settings["password_set"]:
        missing.append("Save the ESXi host settings and root password.")
    if not kit["saved_profile"] or kit["profile_id"] != profile_id:
        missing.append("Open this kit as the active saved kit.")
    if not kit["single_server_local"]:
        missing.append(
            "This kit must be a single server with local storage to install ESXi from here."
        )
    if row and kit["esxi_management"] != row.data_json.get("management_ip") and (
        row.data_json.get("addressing", "static") == "static" or kit["esxi_management"]
    ):
        missing.append(
            "Save the ESXi settings again so the kit and the server agree on the management address."
        )
    if row and not _root_password_path(device_id).is_file():
        missing.append("Enter the root password again so the app can sign in to check the install.")
    if not kit["dns"]:
        missing.append("Add at least one DNS server in Network settings.")
    volume = settings["boot_volume"]
    if not volume:
        missing.append("Build the RAID boot mirror first (Disks & RAID).")
    elif not volume["disk_id"]:
        missing.append(
            "Read the disks again on Disks & RAID so the boot mirror's disk ID is known."
        )
    return {
        "context": context,
        "kit": kit,
        "settings": settings,
        "media": media,
        "row": row,
        "missing": missing,
    }


def build_installer(
    session: Session, profile_id: str, device_id: str, actor: str
) -> dict[str, Any]:
    from app.services import esxi_installer_artifact as artifact
    from app.services.lab_profiles import lab_profile_context_fingerprint

    inputs = _build_inputs(session, profile_id, device_id)
    if inputs["missing"]:
        return {"status": "blocked", "blockers": inputs["missing"]}
    kit, saved, media = inputs["kit"], inputs["row"].data_json, inputs["media"]
    password_hash = _secret_path(device_id).read_text(encoding="ascii").strip()
    source = (_media_root() / media["path"]).resolve()
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    context = dict(inputs["context"])
    context["esxi_management_vlan_id"] = saved["vlan_id"]
    request = {
        "profile_id": profile_id,
        "profile_version": int(kit["profile_version"]),
        "profile_fingerprint": lab_profile_context_fingerprint(inputs["context"]),
        "source_iso_path": str(source),
        "expected_source_iso_sha256": digest.hexdigest(),
        "hostname": saved["hostname"],
        "bootproto": saved.get("addressing", "static"),
        "management_ip": saved["management_ip"],
        "subnet_cidr": str(ipaddress.ip_network(str(kit["subnet"]), strict=False)),
        "gateway": kit["gateway"] if saved.get("addressing", "static") == "static" else None,
        "dns_servers": kit["dns"][:4],
        "ntp_servers": kit["ntp"][:4],
        "management_nic": saved["management_nic"],
        "management_vlan_id": saved["vlan_id"],
        "install_disk_id": inputs["settings"]["boot_volume"]["disk_id"],
        "system_media_size": "default",
        "root_password_sha512_crypt": password_hash,
        "secure_boot_expected": False,
        "allow_firstboot_network_services": True,
        "local_datastore_expected": True,
        "acknowledge_install_disk_overwrite": True,
    }
    report = artifact.prepare_esxi_installer_artifact(
        request, profile_context=context, allowed_media_roots=[_media_root()]
    )
    if report.get("status") != "ready":
        return {
            "status": "blocked",
            "blockers": list(report.get("blockers") or ["The installer could not be built."]),
            "failure": report.get("failure_code"),
        }
    derived = report["derived_artifact"]
    built = (
        Path(derived["iso"])
        if Path(derived["iso"]).is_absolute()
        else (artifact.REPO_ROOT / derived["iso"]).resolve()
    )
    name = f"{DERIVED_PREFIX}{derived['iso_sha256'][:16]}.iso"
    served = _media_root() / name
    if not served.is_file() or served.stat().st_size != derived["iso_size_bytes"]:
        partial = served.with_name(f".{name}.{secrets.token_hex(4)}.partial")
        shutil.copyfile(built, partial)
        os.replace(partial, served)
    _record(
        session,
        actor,
        "kit.esxi_installer_built",
        "Unattended ESXi installer built offline; nothing sent to hardware.",
        {
            "profile_id": profile_id,
            "device_id": device_id,
            "profile_version": int(kit["profile_version"]),
            "settings_digest": _settings_digest(saved, password_hash),
            "media_path": media["path"],
            "source_sha256": digest.hexdigest(),
            "iso_name": name,
            "iso_sha256": derived["iso_sha256"],
            "iso_size_bytes": derived["iso_size_bytes"],
            "kickstart_sha256": derived["kickstart_sha256"],
            "install_disk_id": request["install_disk_id"],
            "hostname": saved["hostname"],
            "management_ip": saved["management_ip"],
        },
    )
    return build_status(session, profile_id, device_id)


def build_status(session: Session, profile_id: str, device_id: str) -> dict[str, Any]:
    inputs = _build_inputs(session, profile_id, device_id)
    row = _latest(session, "kit.esxi_installer_built", profile_id=profile_id, device_id=device_id)
    if inputs["missing"]:
        return {"status": "blocked", "blockers": inputs["missing"], "built": None}
    if not row:
        return {"status": "not_built", "blockers": [], "built": None}
    data = row.data_json
    saved = inputs["row"].data_json
    password_hash = _secret_path(device_id).read_text(encoding="ascii").strip()
    current = (
        data["settings_digest"] == _settings_digest(saved, password_hash)
        and data["media_path"] == inputs["media"]["path"]
        and data["profile_version"] == int(inputs["kit"]["profile_version"])
        and data["install_disk_id"] == inputs["settings"]["boot_volume"]["disk_id"]
        and (_media_root() / data["iso_name"]).is_file()
    )
    return {
        "status": "ready" if current else "stale",
        "blockers": []
        if current
        else ["Settings, media or disks changed since the installer was built. Build it again."],
        "built": {
            "iso_name": data["iso_name"],
            "iso_sha256": data["iso_sha256"],
            "size_bytes": data["iso_size_bytes"],
            "built_at": row.created_at.replace(tzinfo=UTC).isoformat(),
            "install_disk_id": data["install_disk_id"],
            "hostname": data["hostname"],
            "management_ip": data["management_ip"],
        },
    }


# ---------------------------------------------------------------- install run


def _config(session: Session, device_id: str):
    from app.core.config import settings
    from app.services.ilo_access_settings import ilo_config_for_device

    if settings.provider_mode != "local-lab-readwrite":
        raise EsxiInstallError(
            "ESXi install needs the local lab provider (read-write) to be configured."
        )
    config = ilo_config_for_device(session, device_id)
    if not config.configured or config.fallback_hosts:
        raise EsxiInstallError("Save this server's exact iLO address and sign-in on Connect first.")
    return config


def _policy_blockers() -> list[str]:
    from app.providers.action_policy import ActionCategory, current_lab_action_policy

    policy = current_lab_action_policy()
    found: list[str] = []
    for action, category in (
        (ACTION_MEDIA, ActionCategory.VIRTUAL_MEDIA),
        (ACTION_BOOT, ActionCategory.BOOT_CONFIG),
        (ACTION_POWER, ActionCategory.POWER_ACTION),
        (ACTION_DATASTORE, ActionCategory.STORAGE_CONFIG),
    ):
        for blocker in policy.action_blockers(action, category):
            if blocker not in found:
                found.append(blocker)
    return found


def _media_url(config, name: str) -> str:
    from app.services import esxi_boot_workflow as boot

    base = os.getenv("ESXI_MEDIA_BASE_URL")
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
        raise EsxiInstallError("The lab media service must have a plain HTTP address.")
    return base.rstrip("/") + "/" + quote(name)


def _read_server(config) -> dict[str, Any]:
    from app.services import esxi_boot_workflow as boot
    from app.providers.ilo_redfish import _resource_summary
    from app.providers.hpe_firmware_inventory import _hardware_identity

    system = boot._body(boot._get_redfish_resource(boot.SYSTEM_PATH, config=config))
    media = boot._select_virtual_media_device(config=config)
    media_body = boot._body(boot._get_redfish_resource(media["path"], config=config))
    return {
        "hardware_identity": _hardware_identity({"systems": [_resource_summary(system)]}),
        "power": system.get("PowerState"),
        "boot": system.get("Boot") or {},
        "post": ((system.get("Oem") or {}).get("Hpe") or {}).get("PostState"),
        "media": media,
        "inserted": media_body.get("Inserted"),
        "image": media_body.get("Image"),
        "eject_target": (
            (media_body.get("Actions") or {}).get("#VirtualMedia.EjectMedia") or {}
        ).get("target"),
    }


def _current_boot_disk(session, device_id, config):
    from app.providers.ilo_redfish import IloRedfishAdapter

    probe = IloRedfishAdapter(config=config).probe()
    if probe.get("status") != "ok":
        raise EsxiInstallError("The current boot mirror could not be read. Nothing was restarted.")
    volume = _boot_volume(session, device_id, probe_result=probe)
    return volume.get("disk_id") if volume else None


def _assert_target(data, config, server):
    from app.providers.ilo_redfish import ilo_target_fingerprint

    if (
        not data.get("hardware_identity")
        or data["hardware_identity"] != server.get("hardware_identity")
        or data.get("endpoint_identity") != ilo_target_fingerprint(config.host)
    ):
        raise EsxiInstallError(
            "The saved connection or server identity changed. No command was sent."
        )


def _esxi_answers(ip: str) -> dict[str, Any]:
    """Read-only: ESXi's API answers on its planned address."""
    try:
        with socket.create_connection((ip, 443), timeout=3):
            pass
    except OSError:
        return {"answering": False, "detail": "Nothing answers on port 443 yet."}
    try:
        with httpx.Client(verify=False, timeout=8, trust_env=False) as client:
            response = client.get(f"https://{ip}/sdk/vimServiceVersions.xml")
        if response.status_code == 200 and "urn:vim25" in response.text:
            return {"answering": True, "detail": "ESXi's API answers on its management address."}
        return {
            "answering": False,
            "detail": f"Port 443 answers, but not as ESXi yet (HTTP {response.status_code}).",
        }
    except httpx.HTTPError:
        return {
            "answering": False,
            "detail": "Port 443 is open but ESXi's API is not answering yet.",
        }


def _run(session: Session, device_id: str) -> AuditEvent | None:
    return _latest(session, "kit.esxi_install.run", device_id=device_id)


def install_status(session: Session, profile_id: str, device_id: str) -> dict[str, Any]:
    run = _run(session, device_id)
    orphan = session.scalar(
        select(GuardedOperation).where(
            GuardedOperation.resource == "esxi-install",
            GuardedOperation.profile_id == profile_id,
            GuardedOperation.active_device == device_id,
        )
    )
    if orphan and (not run or run.data_json.get("run_id") != orphan.id):
        return {
            "state": "needs_attention",
            "active": True,
            "run_id": orphan.id,
            "phases": {},
            "phase": "admission",
            "message": "The request was reserved but preparation was interrupted before dispatch. Close this run and review again.",
        }
    if not run or run.data_json.get("profile_id") != profile_id:
        return {
            "state": "not_started",
            "active": False,
            "phases": {},
            "message": "ESXi has not been installed from the app on this server.",
        }
    data = run.data_json
    run_id = data["run_id"]
    phases: dict[str, str] = {}
    for event in _events(session, "kit.esxi_install.attempt", run_id=run_id):
        phases[event.data_json["phase"]] = "sent"
    for event in _events(session, "kit.esxi_install.result", run_id=run_id):
        phases[event.data_json["phase"]] = event.data_json["outcome"]
    observed = _latest(session, "kit.esxi_install.observed", run_id=run_id)
    verification = _latest(session, "kit.esxi_install.verification", run_id=run_id)
    done = _latest(session, "kit.esxi_install.done", run_id=run_id)
    problem = next(
        (phase for phase in PHASES if phases.get(phase) in {"failed", "uncertain", "sent"}), None
    )
    started = run.created_at.replace(tzinfo=UTC)
    base = {
        "run_id": run_id,
        "phases": phases,
        "started_at": started.isoformat(),
        "management_ip": data["management_ip"]
        or (verification.data_json.get("address") if verification else None)
        or (observed.data_json.get("address") if observed else None),
        "addressing": data.get("addressing", "static"),
        "hostname": data["hostname"],
        "iso_name": data["iso_name"],
        "datastore_name": data.get("datastore_name"),
        "last_check": observed.data_json if observed else None,
        "verification": verification.data_json if verification else None,
    }
    if done and done.data_json.get("closed"):
        return {
            **base,
            "state": "closed",
            "active": False,
            "message": "The last ESXi install run was closed without being verified.",
        }
    if done and done.data_json.get("verified_at"):
        return {
            **base,
            "state": "verified",
            "active": False,
            "verified_at": done.data_json["verified_at"],
            "ejected": done.data_json.get("ejected"),
            "datastore": done.data_json.get("datastore"),
            "message": f"ESXi is installed and verified at {base['management_ip']}.",
        }
    if done:
        return {
            **base,
            "state": "reachable",
            "active": False,
            "verified_at": None,
            "ejected": done.data_json.get("ejected"),
            "message": f"An ESXi API answers at {data['management_ip']}. Host identity, installed disk and root sign-in are not yet verified.",
        }
    if problem:
        result = _latest(session, "kit.esxi_install.result", run_id=run_id, phase=problem)
        message = (
            result.data_json.get("message")
            if result
            else "This step was sent but its outcome was not recorded."
        )
        refused = bool(result) and _refused(session, run_id, problem)
        return {
            **base,
            "state": "needs_attention",
            "active": True,
            "phase": problem,
            # The app never restarted the server, but it may have booted the attached
            # installer by itself; a signed-in check can still prove the install.
            "can_check_installed": problem in {"boot", "power"}
            and phases.get(problem) == "failed"
            and "power" not in {p for p, outcome in phases.items() if outcome in {"sent", "uncertain", "ok"}},
            "message": message if refused else f"{message} Nothing was retried.",
        }
    if phases.get("power") == "ok":
        late = datetime.now(UTC) - started > INSTALL_WINDOW
        return {
            **base,
            "state": "installing",
            "active": True,
            "late": late,
            "message": "The installer is running on the server. It installs, restarts and then answers on the management address; this usually takes 10-20 minutes."
            if not late
            else "ESXi has not answered within an hour. Look at the iLO remote console for an installer message.",
        }
    return {**base, "state": "starting", "active": True, "message": "Preparing the install."}


def _send(
    session: Session, actor: str, run_id: str, phase: str, action: str, function
) -> dict[str, Any]:
    """Record the attempt, send once inside the action's dispatch lease, record the outcome."""
    from app.services.runtime_write_scope import dispatch_lease

    expected = {
        "media": "accepted",
        "boot": "esxi-ok-media",
        "power": "esxi-ok-boot",
        "eject": "esxi-ok-power",
        "datastore": "esxi-ok-eject",
    }[phase]
    claim = session.execute(
        update(GuardedOperation)
        .where(
            GuardedOperation.id == run_id,
            GuardedOperation.status == expected,
            GuardedOperation.active_device.is_not(None),
        )
        .values(status=f"esxi-sent-{phase}", updated_at=utcnow())
    )
    if claim.rowcount != 1:
        session.rollback()
        raise EsxiInstallError("This step is already claimed or unresolved. Nothing was resent.")
    _record(
        session,
        actor,
        "kit.esxi_install.attempt",
        f"ESXi install step '{phase}' starting; outcome unverified.",
        {"run_id": run_id, "phase": phase},
    )
    try:
        with dispatch_lease(action):
            result = function()
    except Exception as exc:
        _record(
            session,
            actor,
            "kit.esxi_install.result",
            f"ESXi install step '{phase}' outcome unknown.",
            {
                "run_id": run_id,
                "phase": phase,
                "outcome": "uncertain",
                "message": f"The server did not confirm the '{phase}' step ({_safe_reason(exc)}).",
            },
        )
        raise
    return result


def _safe_reason(exc: Exception) -> str:
    """govc and app errors are written to be shown (passwords masked); anything else by type only."""
    from app.providers.esxi_govc import GovcError

    if isinstance(exc, (GovcError, EsxiInstallError)):
        return f"{type(exc).__name__}: {str(exc)[:300]}"
    return type(exc).__name__


def start_install(session: Session, profile_id: str, device_id: str, actor: str) -> dict[str, Any]:
    from app.providers.spp_media_server import ensure_media_server

    current = install_status(session, profile_id, device_id)
    if current["active"]:
        raise EsxiInstallError(
            "An ESXi install is already recorded for this server. Watch it to the end or check its status."
        )
    build = build_status(session, profile_id, device_id)
    if build["status"] != "ready":
        raise EsxiInstallError((build["blockers"] or ["Build the installer first."])[0])
    blockers = _policy_blockers()
    if blockers:
        raise EsxiInstallError(blockers[0])
    config = _config(session, device_id)
    built = build["built"]
    url = _media_url(config, built["iso_name"])
    try:
        server = _read_server(config)
    except Exception:
        raise EsxiInstallError(
            "The server's iLO did not answer a read. Check its connection on Connect."
        ) from None
    if server["power"] not in {"On", "Off"}:
        raise EsxiInstallError("The server's power state is not known yet. Try again in a minute.")
    if not server.get("hardware_identity"):
        raise EsxiInstallError("The server did not report a stable hardware identity.")
    if _current_boot_disk(session, device_id, config) != built["install_disk_id"]:
        raise EsxiInstallError(
            "The boot mirror changed. Read the disks and build the installer again."
        )
    if server["inserted"] is True and server["image"] != url:
        raise EsxiInstallError(
            "Other virtual media is attached to this server. Eject it in the iLO first; it will not be replaced."
        )
    # The served bytes must be the built installer, checked before anything is sent.
    if not os.getenv("ESXI_MEDIA_BASE_URL"):
        ensure_media_server(_media_root(), int(os.getenv("ESXI_MEDIA_HTTP_PORT", "8088")))
    digest, size = hashlib.sha256(), 0
    try:
        with httpx.stream(
            "GET", url, timeout=60, follow_redirects=False, trust_env=False
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes(1024 * 1024):
                size += len(chunk)
                if size > built["size_bytes"]:
                    break
                digest.update(chunk)
    except httpx.HTTPError:
        raise EsxiInstallError(
            "The installer ISO is not reachable from the lab media service."
        ) from None
    if size != built["size_bytes"] or digest.hexdigest() != built["iso_sha256"]:
        raise EsxiInstallError(
            "The media service is not serving the built installer. Nothing was sent."
        )

    from app.services.guarded_operation_ledger import reserve, OperationConflict
    from app.providers.ilo_redfish import ilo_target_fingerprint

    inputs = _build_inputs(session, profile_id, device_id)
    saved_settings, saved_kit = inputs["row"].data_json, inputs["kit"]
    data_volume = _data_volume(session, device_id)

    try:
        operation = reserve(
            session,
            profile_id=profile_id,
            device_id=device_id,
            resource="esxi-install",
            idempotency_key=secrets.token_hex(16),
            actor=actor,
            reviewed_intent={
                "build": built,
                "hardware_identity": server["hardware_identity"],
                "endpoint_identity": ilo_target_fingerprint(config.host),
            },
        )
    except OperationConflict as exc:
        raise EsxiInstallError(str(exc)) from None
    run_id = operation.id
    data = {
        "run_id": run_id,
        "profile_id": profile_id,
        "device_id": device_id,
        "iso_name": built["iso_name"],
        "iso_sha256": built["iso_sha256"],
        "media_url": url,
        "management_ip": built["management_ip"],
        "hostname": built["hostname"],
        "install_disk_id": built["install_disk_id"],
        "addressing": saved_settings.get("addressing", "static"),
        "vlan_id": saved_settings.get("vlan_id", 0),
        "management_nic": saved_settings.get("management_nic", "vmnic0"),
        "netmask": str(ipaddress.ip_network(str(saved_kit["subnet"]), strict=False).netmask),
        "datastore_name": saved_settings.get("datastore_name") if data_volume and data_volume.get("disk_id") else None,
        "data_disk_id": data_volume.get("disk_id") if data_volume else None,
        "power_before": server["power"],
        "hardware_identity": server["hardware_identity"],
        "endpoint_identity": ilo_target_fingerprint(config.host),
    }
    _record(
        session,
        actor,
        "kit.esxi_install.run",
        "ESXi install approved: attach installer, boot once, power on or restart.",
        data,
    )
    _continue_recorded(session, actor, data, config)
    return install_status(session, profile_id, device_id)


POST_BUSY = {"InPost", "InPostDiscoveryComplete"}
POST_WAIT_SECONDS = 480
POST_POLL_SECONDS = 10


def _ilo_reason(response: dict[str, Any]) -> str:
    """The iLO's own refusal, e.g. 'HTTP 400: iLO.2.14.UnableToModifyDuringSystemPOST'."""
    body = response.get("response") if isinstance(response.get("response"), dict) else {}
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    ids = [
        str(item.get("MessageId"))
        for item in error.get("@Message.ExtendedInfo") or []
        if isinstance(item, dict) and item.get("MessageId")
    ]
    reason = ", ".join(ids) or str(error.get("message") or "").strip()
    return f"HTTP {response.get('status_code')}" + (f": {reason[:200]}" if reason else "")


def _wait_for_post(data, config, server) -> dict[str, Any]:
    """HPE iLO refuses boot-override changes while the server is in POST. Read-only wait."""
    deadline = time.monotonic() + POST_WAIT_SECONDS
    while server.get("post") in POST_BUSY:
        if time.monotonic() >= deadline:
            raise EsxiInstallError(
                "The server is still in POST, so the iLO will not accept a one-time boot yet. "
                "Nothing was sent; check the server again once POST has finished."
            )
        time.sleep(POST_POLL_SECONDS)
        server = _read_server(config)
        _assert_target(data, config, server)
    return server


def _continue_recorded(session: Session, actor: str, data: dict[str, Any], config) -> None:
    """Run the remaining steps. An unconfirmed step is already recorded by _send; the run stops
    there and its status says so. Nothing is retried."""
    try:
        _continue(session, actor, data, config)
    except Exception as exc:
        session.rollback()
        current = install_status(session, data["profile_id"], data["device_id"])
        phase = next((p for p in PHASES[:3] if current["phases"].get(p) != "ok"), None)
        if phase and not _latest(
            session, "kit.esxi_install.attempt", run_id=data["run_id"], phase=phase
        ):
            _record(
                session,
                actor,
                "kit.esxi_install.result",
                "ESXi preparation paused before dispatch.",
                {
                    "run_id": data["run_id"],
                    "phase": phase,
                    "outcome": "failed",
                    "message": str(exc)
                    if isinstance(exc, EsxiInstallError)
                    else "The server could not be read before the next command. Nothing was sent for this phase.",
                },
            )


def _continue(session: Session, actor: str, data: dict[str, Any], config) -> None:
    from app.services import esxi_boot_workflow as boot

    run_id, url = data["run_id"], data["media_url"]
    done = {
        event.data_json["phase"]
        for event in _events(session, "kit.esxi_install.result", run_id=run_id)
        if event.data_json["outcome"] == "ok"
    }
    server = _read_server(config)
    _assert_target(data, config, server)
    if "media" not in done:
        if not (server["inserted"] is True and server["image"] == url):
            response = _send(
                session,
                actor,
                run_id,
                "media",
                ACTION_MEDIA,
                lambda: boot._post_virtual_media_action(server["media"], url, config=config),
            )
            if response.get("status_code") not in {200, 202, 204}:
                _record(
                    session,
                    actor,
                    "kit.esxi_install.result",
                    "Virtual media was refused.",
                    {
                        "run_id": run_id,
                        "phase": "media",
                        "outcome": "failed",
                        "message": f"The iLO refused to attach the installer ({_ilo_reason(response)}).",
                        "refused": True,
                    },
                )
                return
            server = _read_server(config)
            _assert_target(data, config, server)
            if not (server["inserted"] is True and server["image"] == url):
                _record(
                    session,
                    actor,
                    "kit.esxi_install.result",
                    "Virtual media not confirmed.",
                    {
                        "run_id": run_id,
                        "phase": "media",
                        "outcome": "uncertain",
                        "message": "The iLO did not confirm the installer is attached.",
                    },
                )
                return
        _record(
            session,
            actor,
            "kit.esxi_install.result",
            "Installer attached and read back.",
            {"run_id": run_id, "phase": "media", "outcome": "ok"},
        )
    if "boot" not in done:
        if server["inserted"] is not True or server["image"] != url:
            raise EsxiInstallError(
                "The reviewed installer is no longer attached. No boot command was sent."
            )
        once = (
            server["boot"].get("BootSourceOverrideEnabled") == "Once"
            and server["boot"].get("BootSourceOverrideTarget") == "Cd"
        )
        if not once:
            server = _wait_for_post(data, config, server)
        if not once:
            response = _send(
                session,
                actor,
                run_id,
                "boot",
                ACTION_BOOT,
                lambda: boot._patch_system_boot(
                    {
                        "Boot": {
                            "BootSourceOverrideEnabled": "Once",
                            "BootSourceOverrideTarget": "Cd",
                        }
                    },
                    config=config,
                ),
            )
            if response.get("status_code") not in {200, 202, 204}:
                _record(
                    session,
                    actor,
                    "kit.esxi_install.result",
                    "One-time boot was refused.",
                    {
                        "run_id": run_id,
                        "phase": "boot",
                        "outcome": "failed",
                        "message": f"The iLO refused the one-time boot from the installer ({_ilo_reason(response)}). Nothing was applied; Check the server again sends it once more.",
                        "refused": True,
                    },
                )
                return
            server = _read_server(config)
            _assert_target(data, config, server)
            if not (
                server["boot"].get("BootSourceOverrideEnabled") == "Once"
                and server["boot"].get("BootSourceOverrideTarget") == "Cd"
            ):
                _record(
                    session,
                    actor,
                    "kit.esxi_install.result",
                    "One-time boot not confirmed.",
                    {
                        "run_id": run_id,
                        "phase": "boot",
                        "outcome": "uncertain",
                        "message": "The iLO did not confirm the one-time boot.",
                    },
                )
                return
        _record(
            session,
            actor,
            "kit.esxi_install.result",
            "One-time installer boot set and read back.",
            {"run_id": run_id, "phase": "boot", "outcome": "ok"},
        )
    if "power" not in done:
        if _current_boot_disk(session, data["device_id"], config) != data["install_disk_id"]:
            raise EsxiInstallError("The boot mirror changed before restart. No restart was sent.")
        if (
            server["boot"].get("BootSourceOverrideEnabled") != "Once"
            or server["boot"].get("BootSourceOverrideTarget") != "Cd"
        ):
            raise EsxiInstallError("The one-time installer boot changed. No restart was sent.")
        if not (server["inserted"] is True and server["image"] == url):
            _record(
                session,
                actor,
                "kit.esxi_install.result",
                "Installer no longer attached.",
                {
                    "run_id": run_id,
                    "phase": "power",
                    "outcome": "failed",
                    "message": "The installer was detached before the restart; the server was not restarted.",
                },
            )
            return
        reset = "On" if server["power"] == "Off" else "ForceRestart"
        response = _send(
            session,
            actor,
            run_id,
            "power",
            ACTION_POWER,
            lambda: boot._post_system_reset(reset, config=config),
        )
        if response.get("status_code") not in {200, 202, 204}:
            _record(
                session,
                actor,
                "kit.esxi_install.result",
                "Power request was refused.",
                {
                    "run_id": run_id,
                    "phase": "power",
                    "outcome": "failed",
                    "message": "The iLO refused to start the server.",
                },
            )
            return
        _record(
            session,
            actor,
            "kit.esxi_install.result",
            f"Server {'powered on' if reset == 'On' else 'restarted'} into the installer.",
            {"run_id": run_id, "phase": "power", "outcome": "ok", "reset": reset},
        )


def _discover_address(session: Session, device_id: str, kit_subnet: str | None) -> str | None:
    """DHCP: the address the host reports to its iLO (HPE's ESXi image includes the agent)."""
    from app.services import esxi_boot_workflow as boot

    try:
        config = _config(session, device_id)
        listing = boot._body(boot._get_redfish_resource("/redfish/v1/Systems/1/EthernetInterfaces/", config=config))
    except Exception:
        return None
    try:
        network = ipaddress.ip_network(str(kit_subnet), strict=False) if kit_subnet else None
    except ValueError:
        network = None
    found: list[str] = []
    for member in listing.get("Members") or []:
        path = member.get("@odata.id") if isinstance(member, dict) else None
        if not path:
            continue
        try:
            body = boot._body(boot._get_redfish_resource(path, config=config))
        except Exception:
            continue
        for entry in body.get("IPv4Addresses") or []:
            try:
                value = ipaddress.ip_address(str((entry or {}).get("Address") or ""))
            except ValueError:
                continue
            if value.is_unspecified or value.is_link_local or value.is_loopback:
                continue
            found.append(str(value))
    inside = [item for item in found if network and ipaddress.ip_address(item) in network]
    return (inside or found or [None])[0]


def _network_ports(session: Session, device_id: str) -> list[dict[str, Any]] | None:
    """Read-only: every physical network port the iLO knows, with its link. vmnic names appear
    once ESXi has run; before that a port is identified by its MAC, which the kickstart accepts."""
    from app.services import esxi_boot_workflow as boot

    try:
        config = _config(session, device_id)
        listing = boot._body(boot._get_redfish_resource("/redfish/v1/Systems/1/BaseNetworkAdapters/", config=config))
        adapters = [
            boot._body(boot._get_redfish_resource(member["@odata.id"], config=config))
            for member in listing.get("Members") or []
            if isinstance(member, dict) and member.get("@odata.id")
        ]
    except Exception:
        return None
    ports = []
    for adapter in adapters:
        name = re.sub(r"\s*-\s*NIC$", "", str(adapter.get("Name") or "Network adapter")).strip()
        location = str(adapter.get("Location") or adapter.get("StructuredName") or "").strip()
        for index, port in enumerate(adapter.get("PhysicalPorts") or []):
            if not isinstance(port, dict):
                continue
            mac = str(port.get("MacAddress") or "").strip().lower().replace("-", ":")
            if not MAC.fullmatch(mac):
                continue
            number = ((port.get("Oem") or {}).get("Hpe") or {}).get("PortNumber") or index + 1
            vmnic = str(port.get("Name") or "")
            ports.append({
                "mac": mac,
                "adapter": name,
                "location": location,
                "port": number,
                "link": port.get("LinkStatus") == "LinkUp",
                "speed_mbps": port.get("SpeedMbps") or None,
                "vmnic": vmnic if NIC.fullmatch(vmnic) else None,
            })
    return ports


def _port_label(port: dict[str, Any]) -> str:
    where = f"{port['location'] or port['adapter']} port {port['port']}"
    return f"{port['vmnic']} ({where})" if port.get("vmnic") else where


def _port_for(ports: list[dict[str, Any]], nic: str) -> dict[str, Any] | None:
    return next((port for port in ports if nic in {port["mac"], port.get("vmnic")}), None)


def list_network_ports(session: Session, profile_id: str, device_id: str) -> dict[str, Any]:
    ports = _network_ports(session, device_id)
    if ports is None:
        return {"available": False, "ports": [], "suggested": None,
                "message": "The iLO did not list the server's network ports. Check the iLO connection on the Connect step."}
    linked = [port for port in ports if port["link"]]
    # Prefer a cabled built-in port: that is where management usually lives.
    builtin = [port for port in linked if any(word in port["location"].lower() for word in ("lom", "embedded"))]
    suggested = (builtin or linked or [None])[0]
    return {
        "available": True,
        "ports": ports,
        "suggested": suggested["mac"] if suggested else None,
        "message": None if linked else "The iLO reports no port with a cable. Link shows only while the server is powered on.",
    }


def _no_lease_detail(session: Session, run: dict[str, Any], address: str) -> str:
    nic = run.get("management_nic") or "vmnic0"
    ports = _network_ports(session, run["device_id"]) or []
    planned = _port_for(ports, nic)
    planned_label = _port_label(planned) if planned else nic
    linked = [port for port in ports if port["link"]]
    cable = (
        f" The iLO sees a network cable only on {', '.join(_port_label(port) for port in linked)}, not on {planned_label}."
        if linked and not (planned and planned["link"])
        else ""
    )
    return (
        f"ESXi has {address}, a self-assigned address: no DHCP server answered on {planned_label}.{cable} "
        "On the server's console (F2, Configure Management Network) choose the connected network "
        "adapter, then Restart Management Network. Then check again."
    )


def _verification_checks(
    run: dict[str, Any], facts: dict[str, Any], address: str, subnet: str | None = None
) -> list[dict[str, Any]]:
    vmk0 = facts.get("vmk0") or {}
    static = run.get("addressing", "static") == "static"
    disk = run["install_disk_id"]
    # DHCP plan, but the operator set a fixed address on the console because no lease came:
    # accepted only for the address the app signed in on, inside the kit subnet.
    console_static = (
        not static
        and vmk0.get("type") == "STATIC"
        and vmk0.get("ip") == address
        and bool(subnet)
        and ipaddress.ip_address(address) in ipaddress.ip_network(str(subnet), strict=False)
    )
    fqdn = str(facts.get("fqdn") or "")
    short, planned_short = fqdn.split(".")[0], str(run["hostname"]).split(".")[0]
    # With DHCP the server hands out its own domain (option 15) and ESXi takes it; the name the
    # operator chose is the short name, so that is what must match.
    dhcp_domain = not static and fqdn != run["hostname"] and bool(short) and short == planned_short
    host_check = {
        "name": "Host name",
        "ok": fqdn == run["hostname"] or dhcp_domain,
        "expected": run["hostname"] if static else f"{planned_short} (any domain DHCP supplies)",
        "found": f"{fqdn} (domain from DHCP)" if dhcp_domain else fqdn,
    }
    return [
        {"name": "ESXi answered the root sign-in", "ok": "esxi" in str(facts.get("product", "")).lower(),
         "expected": "VMware ESXi", "found": f"{facts.get('product')} {facts.get('version')}".strip()},
        host_check,
        {"name": "Management address", "ok": vmk0.get("ip") == (run["management_ip"] if static else address)
         and (vmk0.get("type") == ("STATIC" if static else "DHCP") or console_static)
         and (not static or vmk0.get("netmask") == run.get("netmask")),
         "expected": f"{run['management_ip']}/{run.get('netmask')} static" if static
         else "an address from DHCP, or one set on the console inside the kit subnet",
         "found": f"{vmk0.get('ip')}/{vmk0.get('netmask')} {str(vmk0.get('type') or '').lower()}".strip()},
        {"name": "Management VLAN", "ok": str(facts.get("management_vlan")) == str(run.get("vlan_id", 0)),
         "expected": str(run.get("vlan_id", 0)) if run.get("vlan_id") else "untagged (0)", "found": str(facts.get("management_vlan"))},
        {"name": "Installed on the boot mirror", "ok": bool((facts.get("partitions") or {}).get(disk)),
         "expected": disk, "found": "ESXi partitions found" if (facts.get("partitions") or {}).get(disk) else "no partitions on that disk"},
    ]


def check_install(
    session: Session, profile_id: str, device_id: str, actor: str, address: str | None = None
) -> dict[str, Any]:
    """Read-only watch. Once ESXi answers, sign in as root and prove the install; only then
    eject this run's installer and create the reviewed VM datastore."""
    from app.providers import esxi_govc as govc
    from app.services import esxi_boot_workflow as boot

    current = install_status(session, profile_id, device_id)
    adopt = current["state"] == "needs_attention" and current.get("can_check_installed")
    if current["state"] != "installing" and not adopt:
        return current
    run = _run(session, device_id).data_json
    target = run["management_ip"]
    if run.get("addressing", "static") == "dhcp":
        if address:
            try:
                target = str(ipaddress.ip_address(address.strip()))
            except ValueError:
                raise EsxiInstallError("Enter the address exactly as the server's screen shows it.") from None
        else:
            from app.services.lab_profiles import active_lab_profile_context

            target = _discover_address(session, device_id, _kit(active_lab_profile_context())["subnet"])
        if not target:
            _record(session, actor, "kit.esxi_install.observed", "Read-only ESXi install check.", {
                "run_id": run["run_id"], "checked_at": _now(), "answering": False, "address": None,
                "detail": "Waiting for the server to report its DHCP address. If the server's screen shows one, enter it."})
            return install_status(session, profile_id, device_id)
    if ipaddress.ip_address(target).is_link_local:
        _record(session, actor, "kit.esxi_install.observed", "Read-only ESXi install check.", {
            "run_id": run["run_id"], "checked_at": _now(), "answering": False, "address": None,
            "detail": _no_lease_detail(session, run, target)})
        return install_status(session, profile_id, device_id)
    answer = _esxi_answers(target)
    _record(session, actor, "kit.esxi_install.observed", "Read-only ESXi install check.",
            {"run_id": run["run_id"], "checked_at": _now(), "address": target, **answer})
    if not answer["answering"]:
        return install_status(session, profile_id, device_id)

    password = _root_password(device_id)
    if not password:
        _record(session, actor, "kit.esxi_install.verification", "Signed-in check not possible.", {
            "run_id": run["run_id"], "address": target, "checked_at": _now(), "passed": False, "checks": [],
            "problem": "The root password is not saved. Enter it again in Host settings."})
        return install_status(session, profile_id, device_id)
    try:
        facts = govc.host_facts(target, password)
    except govc.GovcError as exc:
        _record(session, actor, "kit.esxi_install.verification", "Signed-in check did not complete.", {
            "run_id": run["run_id"], "address": target, "checked_at": _now(), "passed": False, "checks": [], "problem": str(exc)})
        return install_status(session, profile_id, device_id)
    from app.services.lab_profiles import active_lab_profile_context

    checks = _verification_checks(run, facts, target, _kit(active_lab_profile_context()).get("subnet"))
    passed = all(check["ok"] for check in checks)
    _record(session, actor, "kit.esxi_install.verification",
            "Signed-in ESXi verification passed." if passed else "Signed-in ESXi verification found differences.",
            {"run_id": run["run_id"], "address": target, "checked_at": _now(), "passed": passed, "checks": checks,
             "build": facts.get("build"), "version": facts.get("version")})
    if not passed:
        return install_status(session, profile_id, device_id)
    if adopt:
        # Signed-in proof that ESXi is on the boot mirror: the boot and restart the app could
        # not send were not needed. Nothing is sent for them.
        note = "Not needed: the server booted the attached installer itself; ESXi was proven by signing in."
        for phase in ("boot", "power"):
            if current["phases"].get(phase) != "ok":
                _record(session, actor, "kit.esxi_install.result", note,
                        {"run_id": run["run_id"], "phase": phase, "outcome": "ok", "adopted": True})
        current = install_status(session, profile_id, device_id)

    # Installer cleanup only after signed-in proof.
    try:
        config = _config(session, device_id)
        server = _read_server(config)
        _assert_target(run, config, server)
    except Exception:
        return install_status(session, profile_id, device_id)
    if current["phases"].get("eject") != "ok":
        if server["inserted"] is True and server["image"] == run["media_url"] and server["eject_target"]:
            from app.providers.hpe_firmware_inventory import _resource_path

            try:
                _send(session, actor, run["run_id"], "eject", ACTION_MEDIA,
                      lambda: boot._post_redfish(_resource_path(server["eject_target"]), {}, config=config))
                readback = _read_server(config)
                _assert_target(run, config, readback)
                ejected = readback["inserted"] is False
            except Exception:
                return install_status(session, profile_id, device_id)
            _record(session, actor, "kit.esxi_install.result", "Installer ejected." if ejected else "Eject not confirmed.", {
                "run_id": run["run_id"], "phase": "eject", "outcome": "ok" if ejected else "uncertain",
                **({} if ejected else {"message": "The installer media is still attached; eject it in the iLO."})})
            if not ejected:
                return install_status(session, profile_id, device_id)
        elif server["inserted"] is False:
            _record(session, actor, "kit.esxi_install.result", "Installer already disconnected.",
                    {"run_id": run["run_id"], "phase": "eject", "outcome": "ok"})
        else:
            _record(session, actor, "kit.esxi_install.result", "Media cleanup needs attention.", {
                "run_id": run["run_id"], "phase": "eject", "outcome": "uncertain",
                "message": "Different virtual media is attached; it was not ejected."})
            return install_status(session, profile_id, device_id)

    datastore = _create_datastore(session, actor, run, target, password, facts)
    if datastore is False:
        return install_status(session, profile_id, device_id)
    _record(session, actor, "kit.esxi_install.done", "ESXi installed and verified by signing in.", {
        "run_id": run["run_id"], "verified_at": _now(), "ejected": True, "address": target, "datastore": datastore})
    return install_status(session, profile_id, device_id)


def _create_datastore(session: Session, actor: str, run: dict[str, Any], target: str, password: str, facts: dict[str, Any]):
    """Format the reviewed RAID data volume as the VM datastore, once. None when not planned;
    False when it needs attention; otherwise the datastore found on that exact disk."""
    from app.providers import esxi_govc as govc

    name, disk = run.get("datastore_name"), run.get("data_disk_id")
    if not name or not disk:
        return None
    existing = next((item for item in facts.get("datastores") or [] if item.get("disk") == disk), None)
    if existing:
        if _latest(session, "kit.esxi_install.result", run_id=run["run_id"], phase="datastore") is None:
            _record(session, actor, "kit.esxi_install.result", "VM datastore found on the data volume.",
                    {"run_id": run["run_id"], "phase": "datastore", "outcome": "ok"})
        return {"name": existing["name"], "disk": disk}
    if (facts.get("partitions") or {}).get(disk):
        _record(session, actor, "kit.esxi_install.result", "Data volume not empty.", {
            "run_id": run["run_id"], "phase": "datastore", "outcome": "failed",
            "message": "The VM data volume already has partitions, so it was not formatted. Check it before creating a datastore."})
        return False
    try:
        _send(session, actor, run["run_id"], "datastore", ACTION_DATASTORE, lambda: govc.create_vmfs_datastore(target, password, name, disk))
        after = govc.host_facts(target, password)
    except Exception:
        return False
    found = next((item for item in after.get("datastores") or [] if item.get("disk") == disk and item.get("name") == name), None)
    _record(session, actor, "kit.esxi_install.result", "VM datastore created and read back." if found else "VM datastore not confirmed.", {
        "run_id": run["run_id"], "phase": "datastore", "outcome": "ok" if found else "uncertain",
        **({} if found else {"message": f"ESXi did not show datastore '{name}' on the data volume."})})
    return {"name": name, "disk": disk} if found else False


def _refused(session: Session, run_id: str, phase: str) -> bool:
    """The latest result for this phase is an explicit iLO refusal (non-2xx): nothing was applied."""
    latest = _latest(session, "kit.esxi_install.result", run_id=run_id, phase=phase)
    data = latest.data_json if latest else {}
    return data.get("outcome") == "failed" and (
        data.get("refused") is True
        or str(data.get("message", "")).startswith(("The iLO refused the one-time boot", "The iLO refused to attach"))
    )


def resume_install(session: Session, profile_id: str, device_id: str, actor: str) -> dict[str, Any]:
    """After an unconfirmed step: read the server back; continue only the steps still not done."""
    current = install_status(session, profile_id, device_id)
    if current["state"] != "needs_attention":
        return current
    if current.get("phase") == "admission":
        raise EsxiInstallError(current["message"])
    run = _run(session, device_id).data_json
    config = _config(session, device_id)
    server = _read_server(config)
    _assert_target(run, config, server)
    phase = current["phase"]
    refused = phase in {"media", "boot"} and _refused(session, run["run_id"], phase)
    if phase in PHASES[:3] and (refused or not _latest(
        session, "kit.esxi_install.attempt", run_id=run["run_id"], phase=phase
    )):
        previous = {"media": "accepted", "boot": "esxi-ok-media", "power": "esxi-ok-boot"}[phase]
        session.execute(
            update(GuardedOperation)
            .where(
                GuardedOperation.id == run["run_id"],
                GuardedOperation.status == f"esxi-failed-{phase}",
            )
            .values(status=previous)
        )
        session.commit()
        _continue_recorded(session, actor, run, config)
        return install_status(session, profile_id, device_id)
    if phase == "datastore":
        from app.providers import esxi_govc as govc

        address = (current.get("verification") or {}).get("address") or run["management_ip"]
        password = _root_password(device_id)
        try:
            facts = govc.host_facts(address, password or "")
        except govc.GovcError as exc:
            raise EsxiInstallError(f"ESXi could not be read: {exc}") from None
        found = next((item for item in facts.get("datastores") or [] if item.get("disk") == run.get("data_disk_id")), None)
        attempt = _latest(session, "kit.esxi_install.attempt", run_id=run["run_id"], phase="datastore")
        settled = attempt is None or datetime.now(UTC) - attempt.created_at.replace(tzinfo=UTC) > DATASTORE_SETTLE
        if not found and not (facts.get("partitions") or {}).get(run.get("data_disk_id")):
            if not settled:
                raise EsxiInstallError("ESXi does not show the VM datastore yet. Check again in two minutes; nothing was resent.")
            # Two minutes on, no datastore and still no partitions: the create never wrote
            # anything (VMFS creation partitions the disk within seconds), so it may be sent again.
            session.execute(
                update(GuardedOperation)
                .where(GuardedOperation.id == run["run_id"],
                       GuardedOperation.status.in_(["esxi-uncertain-datastore", "esxi-failed-datastore"]))
                .values(status="esxi-ok-eject", updated_at=utcnow())
            )
            session.commit()
            created = _create_datastore(session, actor, run, address, password or "", facts)
            if not created:
                return install_status(session, profile_id, device_id)
            found = created
        if not found:
            raise EsxiInstallError("The data volume has partitions but no VM datastore. Nothing was retried; check it in the ESXi host client.")
        _record(session, actor, "kit.esxi_install.result", "VM datastore confirmed by reading ESXi back.",
                {"run_id": run["run_id"], "phase": "datastore", "outcome": "ok"})
        _record(session, actor, "kit.esxi_install.done", "ESXi installed and verified by signing in.", {
            "run_id": run["run_id"], "verified_at": _now(), "ejected": True, "address": address,
            "datastore": {"name": found["name"], "disk": run["data_disk_id"]}})
        return install_status(session, profile_id, device_id)
    if phase == "eject" and server["inserted"] is False:
        _record(
            session,
            actor,
            "kit.esxi_install.done",
            "Media is disconnected; ESXi reachability was observed, installation remains unverified.",
            {"run_id": run["run_id"], "verified_at": None, "ejected": True},
        )
        return install_status(session, profile_id, device_id)
    confirmed = (
        phase == "media" and server["inserted"] is True and server["image"] == run["media_url"]
    ) or (
        phase == "boot"
        and server["boot"].get("BootSourceOverrideEnabled") == "Once"
        and server["boot"].get("BootSourceOverrideTarget") == "Cd"
    )
    if not confirmed:
        raise EsxiInstallError(
            "The server does not show that step as done. Nothing was retried; look at the iLO before starting again."
        )
    _record(
        session,
        actor,
        "kit.esxi_install.result",
        f"Step '{phase}' confirmed by reading the server back.",
        {"run_id": run["run_id"], "phase": phase, "outcome": "ok"},
    )
    _continue_recorded(session, actor, run, config)
    return install_status(session, profile_id, device_id)


def cancel_install(session: Session, profile_id: str, device_id: str, actor: str) -> dict[str, Any]:
    """Close a run that did not start the server, so a fresh one can be reviewed. Nothing is sent."""
    current = install_status(session, profile_id, device_id)
    if current["state"] not in {"needs_attention", "installing"}:
        return current
    proof = current.get("verification") or {}
    if proof.get("passed") and current["phases"].get("eject") == "ok":
        # ESXi itself was proven by signing in; only the datastore step is left open.
        _record(session, actor, "kit.esxi_install.done", "ESXi verified; datastore step closed by the operator.", {
            "run_id": current["run_id"], "verified_at": proof.get("checked_at") or _now(), "ejected": True,
            "address": proof.get("address"), "datastore": None})
        return install_status(session, profile_id, device_id)
    if (
        current["phases"].get("power") in {"ok", "sent", "uncertain"}
        and current["state"] != "installing"
    ):
        raise EsxiInstallError(
            "The server may have been restarted into the installer. Check it before closing this run."
        )
    _record(
        session,
        actor,
        "kit.esxi_install.done",
        "ESXi install run closed by the operator; not verified.",
        {"run_id": current["run_id"], "verified_at": None, "closed": True, "ejected": None},
    )
    return install_status(session, profile_id, device_id)
