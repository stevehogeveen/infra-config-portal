from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)

from app.core.config import settings
from app.providers.redaction import redact_sensitive
from app.services.json_file_store import write_json_object, write_text_value
from app.services.lab_profiles import active_lab_profile_context, lab_profile_context_fingerprint
from app.services.path_utils import display_path

REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
DERIVED_MEDIA_ROOT = REPO_ROOT / "artifacts" / "derived-media" / "esxi"
REPORT_JSON = CODEX_RUN_DIR / "esxi-installer-artifact-redacted.json"
REPORT_MARKDOWN = CODEX_RUN_DIR / "esxi-installer-artifact-report.md"

KICKSTART_ISO_PATH = "/KS.CFG"
BIOS_BOOT_CFG_ISO_PATH = "/BOOT.CFG"
UEFI_BOOT_CFG_ISO_PATH = "/EFI/BOOT/BOOT.CFG"
KICKSTART_BOOT_OPTION = "ks=cdrom:/KS.CFG"
BUILDER_TIMEOUT_SECONDS = 1800
MINIMUM_XORRISO_VERSION = (1, 5, 8, 2)
MINIMUM_XORRISO_VERSION_LABEL = "1.5.8.pl02"

PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$")
HOST_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
XORRISO_VERSION_RE = re.compile(
    r"\bxorriso(?:\s+version\s*:)?\s+"
    r"(?P<version>[0-9]+\.[0-9]+\.[0-9]+(?:\.pl[0-9]+)?)\b",
    re.IGNORECASE,
)
EL_TORITO_BOOT_ENTRY_RE = re.compile(
    r"^El Torito boot img\s*:\s*"
    r"(?P<number>[0-9]+)\s+"
    r"(?P<platform>\S+)\s+"
    r"(?P<bootable>\S+)\s+"
    r"(?P<emulation>\S+)\s+"
    r"(?P<load_segment>\S+)\s+"
    r"(?P<partition_type>\S+)\s+"
    r"(?P<load_size>[0-9]+)\s+"
    r"(?P<lba>[0-9]+)\s*$",
    re.IGNORECASE,
)
EL_TORITO_INDEXED_VALUE_RE = re.compile(
    r"^El Torito (?P<label>img path|img opts)\s*:\s*"
    r"(?P<number>[0-9]+)\s*(?P<value>.*)$",
    re.IGNORECASE,
)
MBR_PARTITION_RE = re.compile(
    r"^MBR partition\s*:\s*"
    r"(?P<number>[0-9]+)\s+"
    r"(?P<status>\S+)\s+"
    r"(?P<type>\S+)\s+"
    r"(?P<start>[0-9]+)\s+"
    r"(?P<blocks>[0-9]+)\s*$",
    re.IGNORECASE,
)
SYSTEM_AREA_INDEXED_VALUE_RE = re.compile(
    r"^(?P<label>"
    r"GPT partition name|GPT partname local|GPT type GUID|GPT partition flags|"
    r"GPT partition path|APM partition name|APM partition type|APM partition path"
    r")\s*:\s*(?P<number>[0-9]+)\s*(?P<value>.*)$",
    re.IGNORECASE,
)
INTERVAL_RANGE_RE = re.compile(
    r"(?P<prefix>:(?:imported_iso|local_fs):)"
    r"[0-9]+[sdb]?-[0-9]+[sdb]?"
    r"(?P<suffix>:)",
    re.IGNORECASE,
)
APPENDED_PARTITION_RANGE_RE = re.compile(
    r"(?P<prefix>appended_partition_[0-9]+)_start_[0-9]+[sdb]?_size_[0-9]+[sdb]?",
    re.IGNORECASE,
)
SHA512_CRYPT_RE = re.compile(
    r"^\$6\$(?:rounds=[1-9][0-9]{3,8}\$)?"
    r"[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86}$"
)


@dataclass(frozen=True)
class _ElToritoEntry:
    number: int
    platform: str
    bootable: str
    emulation: str
    load_segment: str
    partition_type: str
    load_size: int
    image_path: str
    image_options: tuple[str, ...]


@dataclass(frozen=True)
class _ElToritoSignature:
    catalog_path: str
    catalog_block_count: int
    entries: tuple[_ElToritoEntry, ...]


@dataclass(frozen=True)
class _SystemAreaSignature:
    options: str
    summary: tuple[str, ...]
    partition_offset: int | None
    mbr_heads_per_cylinder: int | None
    mbr_sectors_per_head: int | None
    mbr_partitions: tuple[tuple[int, str, str], ...]
    indexed_characteristics: tuple[tuple[str, int, str], ...]


@dataclass(frozen=True)
class _BootEquipmentSignature:
    el_torito: _ElToritoSignature
    system_area: _SystemAreaSignature


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class EsxiInstallerArtifactRequest(_StrictModel):
    """Explicit, saved-profile-bound inputs for one offline ESXi installer artifact."""

    profile_id: str = Field(min_length=1, max_length=120)
    profile_version: int = Field(ge=1)
    profile_fingerprint: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    source_iso_path: Path
    expected_source_iso_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    hostname: str = Field(min_length=3, max_length=253)
    management_ip: ipaddress.IPv4Address
    subnet_cidr: ipaddress.IPv4Network
    gateway: ipaddress.IPv4Address
    dns_servers: tuple[ipaddress.IPv4Address, ...] = Field(min_length=1, max_length=4)
    ntp_servers: tuple[str, ...] = Field(min_length=1, max_length=4)
    management_nic: str = Field(min_length=1, max_length=128)
    management_vlan_id: int = Field(ge=0, le=4094)
    install_disk_id: str = Field(min_length=1, max_length=128)
    system_media_size: Literal["min", "small", "default", "max"]
    root_password_sha512_crypt: SecretStr
    secure_boot_expected: bool
    allow_firstboot_network_services: bool
    local_datastore_expected: Literal[True]
    acknowledge_install_disk_overwrite: Literal[True]

    @field_validator("profile_id")
    @classmethod
    def _valid_profile_id(cls, value: str) -> str:
        if not PROFILE_ID_RE.fullmatch(value):
            raise ValueError("profile_id must be a simple saved-profile identifier")
        return value

    @field_validator("hostname")
    @classmethod
    def _valid_fqdn(cls, value: str) -> str:
        labels = value.rstrip(".").split(".")
        if len(labels) < 2 or any(not HOST_LABEL_RE.fullmatch(label) for label in labels):
            raise ValueError("hostname must be an explicit FQDN")
        return value.rstrip(".").lower()

    @field_validator("management_nic", "install_disk_id")
    @classmethod
    def _valid_device_id(cls, value: str) -> str:
        if not DEVICE_ID_RE.fullmatch(value):
            raise ValueError(
                "device identifiers may contain only letters, digits, dot, colon, dash, and underscore"
            )
        return value

    @field_validator("ntp_servers")
    @classmethod
    def _valid_ntp_servers(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_validated_network_name(value, label="NTP server") for value in values)
        if len(set(normalized)) != len(normalized):
            raise ValueError("ntp_servers must not contain duplicates")
        return normalized

    @field_validator("dns_servers")
    @classmethod
    def _unique_dns_servers(
        cls,
        values: tuple[ipaddress.IPv4Address, ...],
    ) -> tuple[ipaddress.IPv4Address, ...]:
        if len(set(values)) != len(values):
            raise ValueError("dns_servers must not contain duplicates")
        return values

    @field_validator("root_password_sha512_crypt")
    @classmethod
    def _encrypted_root_password_only(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if not SHA512_CRYPT_RE.fullmatch(secret):
            raise ValueError(
                "root_password_sha512_crypt must be a salted SHA-512 crypt value; plaintext is refused"
            )
        return value

    @model_validator(mode="after")
    def _network_is_coherent(self) -> EsxiInstallerArtifactRequest:
        subnet = self.subnet_cidr
        if self.management_ip not in subnet:
            raise ValueError("management_ip must belong to subnet_cidr")
        if self.gateway not in subnet:
            raise ValueError("gateway must belong to subnet_cidr")
        if self.management_ip in {subnet.network_address, subnet.broadcast_address}:
            raise ValueError("management_ip cannot be the subnet network or broadcast address")
        if self.gateway in {subnet.network_address, subnet.broadcast_address}:
            raise ValueError("gateway cannot be the subnet network or broadcast address")
        return self


class EsxiIsoBuildEvidence(_StrictModel):
    builder_name: Literal["xorriso"]
    builder_version: str = Field(min_length=1)
    kickstart_readback_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    boot_config_paths: tuple[str, ...]
    boot_options: tuple[str, ...]
    bios_boot_config_verified: bool
    uefi_boot_config_verified: bool
    source_boot_platforms: tuple[str, ...]
    derived_boot_platforms: tuple[str, ...]
    el_torito_equipment_equivalent: bool
    system_area_equivalent: bool
    source_system_area_summary: tuple[str, ...]
    derived_system_area_summary: tuple[str, ...]


class EsxiIsoBuilder(Protocol):
    name: str
    version: str

    def build(
        self,
        *,
        source_iso: Path,
        output_iso: Path,
        kickstart_path: Path,
        boot_options: tuple[str, ...],
    ) -> EsxiIsoBuildEvidence: ...


class IsoBuilderError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class XorrisoEsxiIsoBuilder:
    """Offline ISO remastering through xorriso boot-equipment replay."""

    name = "xorriso"

    def __init__(self, executable: str, version: str) -> None:
        supported_version = _supported_xorriso_version(version)
        if supported_version is None:
            raise ValueError(f"GNU xorriso {MINIMUM_XORRISO_VERSION_LABEL} or newer is required")
        self.executable = executable
        self.version = f"xorriso {supported_version}"

    @classmethod
    def discover(cls) -> XorrisoEsxiIsoBuilder | None:
        executable = shutil.which("xorriso")
        if not executable:
            return None
        try:
            result = subprocess.run(
                [executable, "-no_rc", "-version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        version = _supported_xorriso_version(f"{result.stdout}\n{result.stderr}")
        if version is None:
            return None
        return cls(executable, f"xorriso {version}")

    def build(
        self,
        *,
        source_iso: Path,
        output_iso: Path,
        kickstart_path: Path,
        boot_options: tuple[str, ...],
    ) -> EsxiIsoBuildEvidence:
        with tempfile.TemporaryDirectory(prefix="esxi-iso-builder-") as temp_dir_value:
            temp_dir = Path(temp_dir_value)
            bios_boot_cfg = temp_dir / "bios-boot.cfg"
            uefi_boot_cfg = temp_dir / "uefi-boot.cfg"
            source_boot_report = self._boot_report(source_iso)
            source_boot_equipment = _parse_boot_equipment(source_boot_report)
            self._extract_boot_configs(source_iso, bios_boot_cfg, uefi_boot_cfg)
            bios_text = _updated_boot_cfg(_read_ascii(bios_boot_cfg), boot_options)
            uefi_text = _updated_boot_cfg(_read_ascii(uefi_boot_cfg), boot_options)
            bios_boot_cfg.write_text(bios_text, encoding="utf-8", newline="\n")
            uefi_boot_cfg.write_text(uefi_text, encoding="utf-8", newline="\n")

            self._run(
                [
                    "-abort_on",
                    "FAILURE",
                    "-indev",
                    str(source_iso),
                    "-outdev",
                    str(output_iso),
                    "-overwrite",
                    "on",
                    "-map",
                    str(kickstart_path),
                    KICKSTART_ISO_PATH,
                    "-map",
                    str(bios_boot_cfg),
                    BIOS_BOOT_CFG_ISO_PATH,
                    "-map",
                    str(uefi_boot_cfg),
                    UEFI_BOOT_CFG_ISO_PATH,
                    "-boot_image",
                    "any",
                    "replay",
                    "-commit",
                    "-end",
                ],
                error_code="iso_build_failed",
            )

            readback_dir = temp_dir / "readback"
            readback_dir.mkdir()
            kickstart_readback = readback_dir / "ks.cfg"
            bios_readback = readback_dir / "bios-boot.cfg"
            uefi_readback = readback_dir / "uefi-boot.cfg"
            self._extract(
                output_iso,
                (
                    (KICKSTART_ISO_PATH, kickstart_readback),
                    (BIOS_BOOT_CFG_ISO_PATH, bios_readback),
                    (UEFI_BOOT_CFG_ISO_PATH, uefi_readback),
                ),
                error_code="iso_readback_failed",
            )
            derived_boot_report = self._boot_report(output_iso)
            derived_boot_equipment = _parse_boot_equipment(derived_boot_report)

            kickstart_sha256 = _sha256_file(kickstart_readback)
            bios_verified = _boot_cfg_has_options(_read_ascii(bios_readback), boot_options)
            uefi_verified = _boot_cfg_has_options(_read_ascii(uefi_readback), boot_options)
            source_platforms = _boot_platforms(source_boot_equipment)
            derived_platforms = _boot_platforms(derived_boot_equipment)
            return EsxiIsoBuildEvidence(
                builder_name="xorriso",
                builder_version=self.version,
                kickstart_readback_sha256=kickstart_sha256,
                boot_config_paths=(BIOS_BOOT_CFG_ISO_PATH, UEFI_BOOT_CFG_ISO_PATH),
                boot_options=boot_options,
                bios_boot_config_verified=bios_verified,
                uefi_boot_config_verified=uefi_verified,
                source_boot_platforms=source_platforms,
                derived_boot_platforms=derived_platforms,
                el_torito_equipment_equivalent=(
                    source_boot_equipment.el_torito == derived_boot_equipment.el_torito
                ),
                system_area_equivalent=(
                    source_boot_equipment.system_area == derived_boot_equipment.system_area
                ),
                source_system_area_summary=source_boot_equipment.system_area.summary,
                derived_system_area_summary=derived_boot_equipment.system_area.summary,
            )

    def _extract_boot_configs(
        self,
        source_iso: Path,
        bios_path: Path,
        uefi_path: Path,
    ) -> None:
        self._extract(
            source_iso,
            (
                (BIOS_BOOT_CFG_ISO_PATH, bios_path),
                (UEFI_BOOT_CFG_ISO_PATH, uefi_path),
            ),
            error_code="source_boot_config_missing",
        )

    def _extract(
        self,
        iso_path: Path,
        mappings: Sequence[tuple[str, Path]],
        *,
        error_code: str,
    ) -> None:
        command = ["-abort_on", "FAILURE", "-osirrox", "on", "-indev", str(iso_path)]
        for source, target in mappings:
            command.extend(["-extract", source, str(target)])
        command.append("-end")
        self._run(command, error_code=error_code)
        if any(not target.is_file() for _, target in mappings):
            raise IsoBuilderError(error_code)

    def _boot_report(self, iso_path: Path) -> str:
        return self._run(
            [
                "-abort_on",
                "FAILURE",
                "-indev",
                str(iso_path),
                "-report_el_torito",
                "plain",
                "-report_system_area",
                "plain",
                "-end",
            ],
            error_code="boot_equipment_inspection_failed",
        )

    def _run(self, arguments: Sequence[str], *, error_code: str) -> str:
        try:
            result = subprocess.run(
                [self.executable, "-no_rc", *arguments],
                check=False,
                capture_output=True,
                text=True,
                timeout=BUILDER_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise IsoBuilderError(error_code) from exc
        if result.returncode != 0:
            raise IsoBuilderError(error_code)
        return f"{result.stdout}\n{result.stderr}"


def prepare_esxi_installer_artifact(
    payload: Mapping[str, Any] | EsxiInstallerArtifactRequest,
    *,
    profile_context: dict[str, Any] | None = None,
    allowed_media_roots: Sequence[Path | str] | None = None,
    builder: EsxiIsoBuilder | None = None,
    derived_media_root: Path = DERIVED_MEDIA_ROOT,
    report_json: Path = REPORT_JSON,
    report_markdown: Path = REPORT_MARKDOWN,
) -> dict[str, Any]:
    """Build and checksum a derived installer without contacting any provider."""

    checked_at = _now()
    try:
        request = (
            payload
            if isinstance(payload, EsxiInstallerArtifactRequest)
            else EsxiInstallerArtifactRequest.model_validate(payload)
        )
    except ValidationError:
        return _write_reports(
            _base_report(
                checked_at,
                status="blocked",
                message="ESXi installer artifact request validation failed closed.",
                blockers=[
                    "Provide every explicit profile, network, disk, media checksum, "
                    "and encrypted-password input using the documented request contract."
                ],
                failure_code="request_validation_failed",
            ),
            report_json=report_json,
            report_markdown=report_markdown,
        )

    context = profile_context or active_lab_profile_context()
    roots = _allowed_media_roots(allowed_media_roots)
    source_iso, source_blockers = _validated_source_path(request.source_iso_path, roots)
    blockers = [
        *_profile_binding_blockers(request, context),
        *_generation_policy_blockers(request),
        *source_blockers,
    ]
    if blockers:
        return _finish_blocked(
            request,
            checked_at,
            blockers,
            failure_code="preflight_blocked",
            source_iso=source_iso,
            report_json=report_json,
            report_markdown=report_markdown,
        )

    selected_builder = builder or XorrisoEsxiIsoBuilder.discover()
    if selected_builder is None:
        return _finish_blocked(
            request,
            checked_at,
            [
                f"GNU xorriso {MINIMUM_XORRISO_VERSION_LABEL} or newer is not installed "
                "or did not pass its isolated local version check. No Kickstart or "
                "derived ISO was written."
            ],
            failure_code="builder_dependency_missing",
            source_iso=source_iso,
            report_json=report_json,
            report_markdown=report_markdown,
        )

    assert source_iso is not None
    try:
        source_sha256_before = _sha256_file(source_iso)
    except OSError:
        return _finish_blocked(
            request,
            checked_at,
            ["The selected source ISO could not be checksummed. No derived artifact was written."],
            failure_code="source_checksum_failed",
            source_iso=source_iso,
            report_json=report_json,
            report_markdown=report_markdown,
        )
    if source_sha256_before.lower() != request.expected_source_iso_sha256.lower():
        return _finish_blocked(
            request,
            checked_at,
            ["The selected source ISO does not match the explicitly approved SHA-256 checksum."],
            failure_code="source_checksum_mismatch",
            source_iso=source_iso,
            source_sha256=source_sha256_before,
            report_json=report_json,
            report_markdown=report_markdown,
        )

    kickstart_bytes = _render_kickstart(request).encode("utf-8")
    kickstart_sha256 = hashlib.sha256(kickstart_bytes).hexdigest()
    boot_options = (
        KICKSTART_BOOT_OPTION,
        f"systemMediaSize={request.system_media_size}",
    )
    derived_media_root.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory(
            prefix=".esxi-installer-build-",
            dir=derived_media_root,
        ) as temp_dir_value:
            temp_dir = Path(temp_dir_value)
            source_snapshot = temp_dir / "source.iso"
            kickstart_path = temp_dir / "ks.cfg"
            output_iso = temp_dir / "derived.iso"
            shutil.copy2(source_iso, source_snapshot)
            if _sha256_file(source_snapshot) != source_sha256_before:
                raise IsoBuilderError("source_snapshot_checksum_mismatch")
            kickstart_path.write_bytes(kickstart_bytes)
            _restrict_local_file(kickstart_path)
            evidence = selected_builder.build(
                source_iso=source_snapshot,
                output_iso=output_iso,
                kickstart_path=kickstart_path,
                boot_options=boot_options,
            )
            evidence_blockers = _build_evidence_blockers(
                evidence,
                expected_kickstart_sha256=kickstart_sha256,
                expected_boot_options=boot_options,
            )
            if evidence_blockers:
                return _finish_blocked(
                    request,
                    checked_at,
                    evidence_blockers,
                    failure_code="derived_iso_readback_failed",
                    source_iso=source_iso,
                    source_sha256=source_sha256_before,
                    builder_name=selected_builder.name,
                    builder_version=selected_builder.version,
                    report_json=report_json,
                    report_markdown=report_markdown,
                )
            if not output_iso.is_file() or output_iso.stat().st_size <= 0:
                raise IsoBuilderError("derived_iso_missing")

            source_sha256_after = _sha256_file(source_iso)
            if source_sha256_after != source_sha256_before:
                raise IsoBuilderError("source_iso_changed_during_build")

            derived_sha256 = _sha256_file(output_iso)
            profile_dir = derived_media_root / _safe_profile_slug(request.profile_id)
            profile_dir.mkdir(parents=True, exist_ok=True)
            artifact_stem = f"esxi-installer-{source_sha256_before[:12]}-{derived_sha256[:16]}"
            final_bundle = profile_dir / artifact_stem
            final_iso = final_bundle / f"{artifact_stem}.iso"
            manifest_path = final_bundle / f"{artifact_stem}.manifest.json"
            checksum_path = final_bundle / f"{artifact_stem}.sha256"
            staged_bundle = temp_dir / "publish"
            staged_bundle.mkdir()
            staged_iso = staged_bundle / final_iso.name
            staged_manifest = staged_bundle / manifest_path.name
            staged_checksum = staged_bundle / checksum_path.name
            os.replace(output_iso, staged_iso)
            _restrict_local_file(staged_iso)

            manifest = _artifact_manifest(
                request,
                checked_at=checked_at,
                source_sha256=source_sha256_before,
                source_size_bytes=source_iso.stat().st_size,
                derived_iso=final_iso,
                derived_sha256=derived_sha256,
                derived_size_bytes=staged_iso.stat().st_size,
                kickstart_sha256=kickstart_sha256,
                boot_options=boot_options,
                evidence=evidence,
            )
            write_json_object(staged_manifest, manifest)
            write_text_value(staged_checksum, f"{derived_sha256}  {final_iso.name}\n")
            _publish_artifact_bundle(
                staged_bundle,
                final_bundle,
                iso_name=final_iso.name,
                expected_iso_sha256=derived_sha256,
                manifest_name=manifest_path.name,
                checksum_name=checksum_path.name,
            )
            manifest_sha256 = _sha256_file(manifest_path)

    except (IsoBuilderError, OSError, shutil.Error) as exc:
        failure_code = exc.code if isinstance(exc, IsoBuilderError) else "artifact_build_io_failed"
        return _finish_blocked(
            request,
            checked_at,
            ["Offline ESXi installer derivation failed closed. No unvalidated ISO was published."],
            failure_code=failure_code,
            source_iso=source_iso,
            source_sha256=source_sha256_before,
            builder_name=selected_builder.name,
            builder_version=selected_builder.version,
            report_json=report_json,
            report_markdown=report_markdown,
        )

    report = _base_report(
        checked_at,
        status="ready",
        message=(
            "A profile-bound, read-back-validated ESXi installer ISO was derived offline. "
            "It has not been attached, booted, or tested on hardware."
        ),
        blockers=[],
        failure_code=None,
    )
    report.update(
        {
            "profile_binding": _profile_summary(request),
            "source_iso": {
                "path_redacted": True,
                "sha256": source_sha256_before,
                "size_bytes": source_iso.stat().st_size,
                "source_snapshot_used": True,
                "source_iso_modified": False,
            },
            "builder": {
                "name": evidence.builder_name,
                "version": evidence.builder_version,
                "bios_boot_config_verified": evidence.bios_boot_config_verified,
                "uefi_boot_config_verified": evidence.uefi_boot_config_verified,
                "source_boot_platforms": list(evidence.source_boot_platforms),
                "derived_boot_platforms": list(evidence.derived_boot_platforms),
                "el_torito_equipment_equivalent": (evidence.el_torito_equipment_equivalent),
                "system_area_equivalent": evidence.system_area_equivalent,
                "source_system_area_summary": list(evidence.source_system_area_summary),
                "derived_system_area_summary": list(evidence.derived_system_area_summary),
            },
            "derived_artifact": {
                "iso": _display(final_iso),
                "iso_sha256": derived_sha256,
                "iso_size_bytes": final_iso.stat().st_size,
                "manifest": _display(manifest_path),
                "manifest_sha256": manifest_sha256,
                "checksum_sidecar": _display(checksum_path),
                "kickstart_sha256": kickstart_sha256,
                "content_addressed": True,
            },
            "credential_handling": {
                "plaintext_root_credential_accepted": False,
                "encrypted_value_in_reports": False,
                "encrypted_value_in_manifest": False,
                "encrypted_value_embedded_only_in_derived_iso": True,
            },
            "remaining_live_gates": [
                "Prove the ESXi installer sees install_disk_id as the intended local RAID logical drive.",
                "Reconfirm the active profile fingerprint and source/derived checksums immediately before attach.",
                "Use the existing guarded virtual-media and installer-boot stages; this service never performs them.",
                "After install, prove ESXi API identity, management networking, local datastore, and media ejection.",
            ],
            "next_safe_action": (
                "Review the manifest and checksums, then perform the separate live disk-identity "
                "preflight before any guarded virtual-media attach or installer boot."
            ),
        }
    )
    return _write_reports(
        _sanitize_report(report, request),
        report_json=report_json,
        report_markdown=report_markdown,
    )


def _render_kickstart(request: EsxiInstallerArtifactRequest) -> str:
    netmask = str(request.subnet_cidr.netmask)
    network_parts = [
        "network",
        "--bootproto=static",
        f"--device={request.management_nic}",
        f"--ip={request.management_ip}",
        f"--netmask={netmask}",
        f"--gateway={request.gateway}",
        f"--nameserver={request.dns_servers[0]}",
        f"--hostname={request.hostname}",
        "--addvmportgroup=1",
    ]
    if request.management_vlan_id:
        network_parts.append(f"--vlanid={request.management_vlan_id}")

    lines = [
        "vmaccepteula",
        f"rootpw --iscrypted {request.root_password_sha512_crypt.get_secret_value()}",
        f"install --disk={request.install_disk_id} --overwritevmfs",
        " ".join(network_parts),
        "reboot",
        "",
        "%firstboot --interpreter=busybox",
    ]
    for dns_server in request.dns_servers[1:]:
        lines.append(f"localcli network ip dns server add --server={dns_server}")
    ntp_arguments = " ".join(f"-s {server}" for server in request.ntp_servers)
    lines.extend(
        [
            "localcli network firewall ruleset set --enabled=true --ruleset-id=ntpClient",
            f"localcli system ntp set {ntp_arguments} -e 1",
            "",
        ]
    )
    return "\n".join(lines)


def _updated_boot_cfg(text: str, boot_options: tuple[str, ...]) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines()
    indices = [index for index, line in enumerate(lines) if line.startswith("kernelopt=")]
    if len(indices) != 1:
        raise IsoBuilderError("source_boot_config_kernelopt_invalid")
    index = indices[0]
    current = lines[index].removeprefix("kernelopt=").strip()
    current_tokens = current.split()
    if any(token.startswith(("ks=", "systemMediaSize=")) for token in current_tokens):
        raise IsoBuilderError("source_boot_config_already_customized")
    lines[index] = f"kernelopt={' '.join([*current_tokens, *boot_options])}"
    return "\n".join(lines) + "\n"


def _boot_cfg_has_options(text: str, options: tuple[str, ...]) -> bool:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    kernel_lines = [line for line in normalized.splitlines() if line.startswith("kernelopt=")]
    if len(kernel_lines) != 1:
        return False
    tokens = kernel_lines[0].removeprefix("kernelopt=").split()
    return all(tokens.count(option) == 1 for option in options)


def _profile_binding_blockers(
    request: EsxiInstallerArtifactRequest,
    context: dict[str, Any],
) -> list[str]:
    active = _dict(context.get("active_profile"))
    plan = _dict(context.get("resolved_address_plan"))
    global_settings = _dict(active.get("global_settings"))
    features = _dict(context.get("enabled_features") or active.get("features"))
    blockers: list[str] = []
    if active.get("source") != "saved" or active.get("id") == "runtime":
        blockers.append("A saved active lab profile is required; runtime fallback is not accepted.")
    if str(active.get("id") or "") != request.profile_id:
        blockers.append("profile_id does not match the active saved lab profile.")
    if int(active.get("version") or 0) != request.profile_version:
        blockers.append("profile_version does not match the active saved lab profile.")
    if lab_profile_context_fingerprint(context) != request.profile_fingerprint.lower():
        blockers.append("profile_fingerprint does not match the active lab profile context.")

    expected_subnet = str(plan.get("subnet") or active.get("subnet_cidr") or "")
    expected_ip = str(plan.get("esxi_management") or "")
    expected_gateway = str(global_settings.get("gateway") or active.get("gateway") or "")
    expected_dns = tuple(
        str(value)
        for value in (
            global_settings.get("dns_servers")
            if isinstance(global_settings.get("dns_servers"), list)
            else active.get("dns") or []
        )
    )
    expected_ntp = tuple(
        str(value)
        for value in (
            global_settings.get("ntp_servers")
            if isinstance(global_settings.get("ntp_servers"), list)
            else active.get("ntp") or []
        )
    )
    profile_vlan = global_settings.get("vlan_id", active.get("vlan_id"))
    expected_vlan = int(profile_vlan) if str(profile_vlan or "").isdigit() else 0
    comparisons = (
        ("subnet_cidr", str(request.subnet_cidr), expected_subnet),
        ("management_ip", str(request.management_ip), expected_ip),
        ("gateway", str(request.gateway), expected_gateway),
        ("dns_servers", tuple(str(value) for value in request.dns_servers), expected_dns),
        ("ntp_servers", request.ntp_servers, expected_ntp),
        ("management_vlan_id", request.management_vlan_id, expected_vlan),
    )
    for label, requested, expected in comparisons:
        if requested != expected:
            blockers.append(f"{label} does not exactly match the active saved lab profile.")

    domain = str(global_settings.get("domain_name") or "").strip().strip(".").lower()
    if domain and not request.hostname.endswith(f".{domain}"):
        blockers.append("hostname does not belong to the active profile domain_name.")
    if features.get("deployment_mode") != "single_server_local_storage":
        blockers.append("Active profile deployment_mode must be single_server_local_storage.")
    if features.get("storage_location") != "server_local":
        blockers.append("Active profile storage_location must be server_local.")
    return _unique(blockers)


def _generation_policy_blockers(request: EsxiInstallerArtifactRequest) -> list[str]:
    blockers: list[str] = []
    if request.secure_boot_expected:
        blockers.append(
            "This artifact uses %firstboot for multi-DNS/NTP setup; generation is refused "
            "when secure_boot_expected is true."
        )
    if not request.allow_firstboot_network_services:
        blockers.append(
            "allow_firstboot_network_services must be explicit because multi-DNS/NTP "
            "configuration is applied during %firstboot."
        )
    if request.install_disk_id.lower().startswith("firstdisk"):
        blockers.append(
            "Generic firstdisk selection is refused; provide one exact installer disk ID."
        )
    return blockers


def _validated_source_path(
    requested_path: Path,
    allowed_roots: tuple[Path, ...],
) -> tuple[Path | None, list[str]]:
    blockers: list[str] = []
    if not requested_path.is_absolute():
        return None, ["source_iso_path must be an explicit absolute path."]
    try:
        if requested_path.is_symlink():
            blockers.append("Symlinked source ISO paths are refused.")
        source = requested_path.resolve(strict=True)
    except OSError:
        return None, ["The selected source ISO does not exist or cannot be resolved."]
    if not source.is_file() or source.suffix.lower() != ".iso":
        blockers.append("The selected source media must be a readable .iso file.")
    if not allowed_roots:
        blockers.append("MEDIA_INVENTORY_DIRS must contain an explicit allowed source-media root.")
    elif not any(source == root or root in source.parents for root in allowed_roots):
        blockers.append("The selected source ISO is outside MEDIA_INVENTORY_DIRS.")
    return source, blockers


def _allowed_media_roots(
    configured: Sequence[Path | str] | None,
) -> tuple[Path, ...]:
    values = configured if configured is not None else settings.media_inventory_dirs
    roots: list[Path] = []
    for value in values:
        try:
            path = Path(value).expanduser().resolve(strict=True)
        except OSError:
            continue
        if path.is_dir() and path not in roots:
            roots.append(path)
    return tuple(roots)


def _build_evidence_blockers(
    evidence: EsxiIsoBuildEvidence,
    *,
    expected_kickstart_sha256: str,
    expected_boot_options: tuple[str, ...],
) -> list[str]:
    blockers: list[str] = []
    if evidence.kickstart_readback_sha256 != expected_kickstart_sha256:
        blockers.append("Derived ISO Kickstart readback checksum does not match generated content.")
    if set(evidence.boot_config_paths) != {
        BIOS_BOOT_CFG_ISO_PATH,
        UEFI_BOOT_CFG_ISO_PATH,
    }:
        blockers.append("Both BIOS and UEFI ESXi boot.cfg files were not read back.")
    if evidence.boot_options != expected_boot_options:
        blockers.append("Derived ISO boot options do not match the approved Kickstart intent.")
    if not evidence.bios_boot_config_verified:
        blockers.append("BIOS boot.cfg does not contain the exact approved boot options once.")
    if not evidence.uefi_boot_config_verified:
        blockers.append("UEFI boot.cfg does not contain the exact approved boot options once.")
    required_platforms = {"BIOS", "UEFI"}
    source_platforms = set(evidence.source_boot_platforms)
    derived_platforms = set(evidence.derived_boot_platforms)
    if not required_platforms.issubset(source_platforms):
        blockers.append("Source ISO does not prove bootable BIOS and UEFI El Torito entries.")
    if not required_platforms.issubset(derived_platforms):
        blockers.append(
            "Derived ISO does not prove bootable BIOS and UEFI El Torito entries after replay."
        )
    if not evidence.el_torito_equipment_equivalent:
        blockers.append(
            "Derived ISO El Torito catalog characteristics do not match the source "
            "after ignoring expected LBA relocation."
        )
    if (
        not evidence.system_area_equivalent
        or evidence.source_system_area_summary != evidence.derived_system_area_summary
    ):
        blockers.append(
            "Derived ISO system-area boot characteristics do not match the source "
            "after ignoring expected partition relocation and size changes."
        )
    return blockers


def _artifact_manifest(
    request: EsxiInstallerArtifactRequest,
    *,
    checked_at: str,
    source_sha256: str,
    source_size_bytes: int,
    derived_iso: Path,
    derived_sha256: str,
    derived_size_bytes: int,
    kickstart_sha256: str,
    boot_options: tuple[str, ...],
    evidence: EsxiIsoBuildEvidence,
) -> dict[str, Any]:
    return {
        "contract_version": "esxi-installer-artifact-v1",
        "created_at": checked_at,
        "offline_only": True,
        "hardware_contacted": False,
        "profile_binding": _profile_summary(request),
        "generation_intent_sha256": _generation_intent_digest(request),
        "source_iso": {
            "path_redacted": True,
            "sha256": source_sha256,
            "size_bytes": source_size_bytes,
            "source_snapshot_used": True,
            "source_iso_modified": False,
        },
        "install_intent": {
            "hostname_redacted": True,
            "management_ip": str(request.management_ip),
            "subnet_cidr": str(request.subnet_cidr),
            "gateway": str(request.gateway),
            "dns_servers": [str(value) for value in request.dns_servers],
            "ntp_servers": list(request.ntp_servers),
            "management_nic": request.management_nic,
            "management_vlan_id": request.management_vlan_id,
            "install_disk_id": request.install_disk_id,
            "system_media_size": request.system_media_size,
            "local_datastore_expected": request.local_datastore_expected,
            "install_disk_overwrite_acknowledged": request.acknowledge_install_disk_overwrite,
            "secure_boot_expected": request.secure_boot_expected,
        },
        "credential_handling": {
            "format": "sha512-crypt",
            "value_omitted": True,
            "plaintext_root_credential_accepted": False,
        },
        "kickstart": {
            "iso_path": KICKSTART_ISO_PATH,
            "sha256": kickstart_sha256,
            "encoding": "utf-8",
            "line_endings": "LF",
        },
        "boot_configuration": {
            "paths": list(evidence.boot_config_paths),
            "options": list(boot_options),
            "bios_verified": evidence.bios_boot_config_verified,
            "uefi_verified": evidence.uefi_boot_config_verified,
            "source_platforms": list(evidence.source_boot_platforms),
            "derived_platforms": list(evidence.derived_boot_platforms),
            "el_torito_replayed": evidence.el_torito_equipment_equivalent,
            "system_area_replayed": evidence.system_area_equivalent,
            "source_system_area_summary": list(evidence.source_system_area_summary),
            "derived_system_area_summary": list(evidence.derived_system_area_summary),
        },
        "derived_iso": {
            "path": _display(derived_iso),
            "sha256": derived_sha256,
            "size_bytes": derived_size_bytes,
            "content_addressed": True,
        },
        "builder": {
            "name": evidence.builder_name,
            "version": evidence.builder_version,
        },
        "remaining_live_gates": [
            "exact install disk identity",
            "profile/checksum reconfirmation",
            "guarded virtual-media attach and installer boot",
            "post-install ESXi identity/network/datastore validation",
            "virtual-media ejection",
        ],
    }


def _profile_summary(request: EsxiInstallerArtifactRequest) -> dict[str, Any]:
    return {
        "profile_id": request.profile_id,
        "profile_version": request.profile_version,
        "profile_fingerprint": request.profile_fingerprint.lower(),
        "hostname_redacted": True,
    }


def _finish_blocked(
    request: EsxiInstallerArtifactRequest,
    checked_at: str,
    blockers: list[str],
    *,
    failure_code: str,
    source_iso: Path | None,
    report_json: Path,
    report_markdown: Path,
    source_sha256: str | None = None,
    builder_name: str | None = None,
    builder_version: str | None = None,
) -> dict[str, Any]:
    report = _base_report(
        checked_at,
        status="blocked",
        message="Offline ESXi installer artifact preparation failed closed.",
        blockers=_unique(blockers),
        failure_code=failure_code,
    )
    report.update(
        {
            "profile_binding": _profile_summary(request),
            "source_iso": {
                "path_redacted": True,
                "sha256": source_sha256,
                "source_iso_modified": False,
            },
            "builder": {
                "name": builder_name,
                "version": builder_version,
            },
            "credential_handling": {
                "plaintext_root_credential_accepted": False,
                "encrypted_value_in_reports": False,
                "encrypted_value_in_manifest": False,
            },
            "next_safe_action": _blocked_next_action(failure_code),
        }
    )
    return _write_reports(
        _sanitize_report(report, request, source_iso=source_iso),
        report_json=report_json,
        report_markdown=report_markdown,
    )


def _base_report(
    checked_at: str,
    *,
    status: str,
    message: str,
    blockers: list[str],
    failure_code: str | None,
) -> dict[str, Any]:
    return {
        "provider_id": "esxi-installer-artifact",
        "action": "offline-derive-installer",
        "checked_at": checked_at,
        "status": status,
        "message": message,
        "failure_code": failure_code,
        "provider_mode": settings.provider_mode,
        "offline_only": True,
        "hardware_contacted": False,
        "provider_calls_attempted": 0,
        "source_iso_write_attempted": False,
        "blockers": blockers,
        "warnings": [
            "A ready artifact is not proof that the ISO has booted or that the selected disk is correct."
        ],
    }


def _write_reports(
    payload: dict[str, Any],
    *,
    report_json: Path,
    report_markdown: Path,
) -> dict[str, Any]:
    result = {
        **payload,
        "reports": {
            "json": _display(report_json),
            "markdown": _display(report_markdown),
        },
    }
    write_json_object(report_json, result)
    write_text_value(report_markdown, _report_markdown(result))
    return result


def _report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# ESXi Installer Artifact Report",
        "",
        f"- checked_at: {report.get('checked_at')}",
        f"- status: {report.get('status')}",
        f"- failure_code: {report.get('failure_code') or 'none'}",
        f"- hardware_contacted: {report.get('hardware_contacted')}",
        f"- source_iso_write_attempted: {report.get('source_iso_write_attempted')}",
        f"- message: {report.get('message')}",
        "",
        "## Blockers",
        "",
    ]
    lines.extend([f"- {item}" for item in report.get("blockers") or []] or ["- none"])
    lines.extend(["", "## Artifact", ""])
    artifact = _dict(report.get("derived_artifact"))
    if artifact:
        for key in (
            "iso",
            "iso_sha256",
            "iso_size_bytes",
            "manifest",
            "manifest_sha256",
            "checksum_sidecar",
            "kickstart_sha256",
        ):
            lines.append(f"- {key}: {artifact.get(key)}")
    else:
        lines.append("- none")
    lines.extend(["", "## Remaining Live Gates", ""])
    lines.extend(
        [f"- {item}" for item in report.get("remaining_live_gates") or []]
        or ["- Artifact preparation did not reach the live-gate handoff."]
    )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- The source ISO was never passed to the remastering tool; a temporary snapshot was used.",
            "- Plaintext passwords are refused. The SHA-512 crypt value is omitted from reports and manifests.",
            "- This action never contacts iLO, ESXi, a switch, storage, or any other provider.",
            "",
            "## Next Safe Action",
            "",
            f"- {report.get('next_safe_action') or 'Resolve blockers and rerun offline preparation.'}",
            "",
        ]
    )
    return "\n".join(lines)


def _sanitize_report(
    report: dict[str, Any],
    request: EsxiInstallerArtifactRequest,
    *,
    source_iso: Path | None = None,
) -> dict[str, Any]:
    secrets = [
        request.root_password_sha512_crypt.get_secret_value(),
        str(source_iso or request.source_iso_path),
        request.hostname,
    ]
    return redact_sensitive(report, secrets)


def _publish_artifact_bundle(
    staged_bundle: Path,
    final_bundle: Path,
    *,
    iso_name: str,
    expected_iso_sha256: str,
    manifest_name: str,
    checksum_name: str,
) -> None:
    if final_bundle.exists():
        iso_path = final_bundle / iso_name
        if (
            not iso_path.is_file()
            or _sha256_file(iso_path) != expected_iso_sha256
            or not (final_bundle / manifest_name).is_file()
            or not (final_bundle / checksum_name).is_file()
        ):
            raise IsoBuilderError("content_address_collision")
        return
    os.replace(staged_bundle, final_bundle)
    if _sha256_file(final_bundle / iso_name) != expected_iso_sha256:
        raise IsoBuilderError("published_checksum_mismatch")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_ascii(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise IsoBuilderError("boot_config_not_utf8") from exc


def _supported_xorriso_version(output: str) -> str | None:
    versions = [match.group("version") for match in XORRISO_VERSION_RE.finditer(output)]
    if not versions:
        return None
    version = max(versions, key=_xorriso_version_key)
    if _xorriso_version_key(version) < MINIMUM_XORRISO_VERSION:
        return None
    return version


def _xorriso_version_key(version: str) -> tuple[int, int, int, int]:
    base, separator, patch = version.lower().partition(".pl")
    parts = base.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        return (0, 0, 0, 0)
    return (
        int(parts[0]),
        int(parts[1]),
        int(parts[2]),
        int(patch) if separator and patch.isdigit() else 0,
    )


def _parse_boot_equipment(report: str) -> _BootEquipmentSignature:
    return _BootEquipmentSignature(
        el_torito=_parse_el_torito_signature(report),
        system_area=_parse_system_area_signature(report),
    )


def _parse_el_torito_signature(report: str) -> _ElToritoSignature:
    catalog_path: str | None = None
    catalog_block_count: int | None = None
    entries: dict[int, tuple[str, str, str, str, str, int]] = {}
    paths: dict[int, str] = {}
    options: dict[int, tuple[str, ...]] = {}

    for raw_line in report.splitlines():
        line = raw_line.strip()
        if line.lower().startswith("el torito catalog"):
            values = line.partition(":")[2].split()
            if len(values) != 2 or any(not value.isdigit() for value in values):
                raise IsoBuilderError("boot_equipment_inspection_invalid")
            catalog_block_count = int(values[1])
            continue
        if line.lower().startswith("el torito cat path"):
            value = line.partition(":")[2].strip()
            if not value:
                raise IsoBuilderError("boot_equipment_inspection_invalid")
            catalog_path = _normalized_boot_path(value)
            continue
        if line.lower().startswith("el torito boot img"):
            match = EL_TORITO_BOOT_ENTRY_RE.fullmatch(line)
            if match is None:
                raise IsoBuilderError("boot_equipment_inspection_invalid")
            number = int(match.group("number"))
            if number in entries:
                raise IsoBuilderError("boot_equipment_inspection_invalid")
            entries[number] = (
                match.group("platform").upper(),
                match.group("bootable").lower(),
                match.group("emulation").lower(),
                match.group("load_segment").lower(),
                match.group("partition_type").lower(),
                int(match.group("load_size")),
            )
            continue
        if line.lower().startswith(("el torito img path", "el torito img opts")):
            match = EL_TORITO_INDEXED_VALUE_RE.fullmatch(line)
            if match is None:
                raise IsoBuilderError("boot_equipment_inspection_invalid")
            number = int(match.group("number"))
            label = match.group("label").lower()
            value = match.group("value").strip()
            target = paths if label == "img path" else options
            if number in target:
                raise IsoBuilderError("boot_equipment_inspection_invalid")
            if label == "img path":
                if not value:
                    raise IsoBuilderError("boot_equipment_inspection_invalid")
                paths[number] = _normalized_boot_path(value)
            else:
                options[number] = tuple(value.lower().split())

    if (
        catalog_path is None
        or catalog_block_count is None
        or catalog_block_count < 1
        or not entries
        or set(paths) != set(entries)
        or not set(options).issubset(entries)
    ):
        raise IsoBuilderError("boot_equipment_inspection_invalid")

    parsed_entries = tuple(
        _ElToritoEntry(
            number=number,
            platform=values[0],
            bootable=values[1],
            emulation=values[2],
            load_segment=values[3],
            partition_type=values[4],
            load_size=values[5],
            image_path=paths[number],
            image_options=options.get(number, ()),
        )
        for number, values in sorted(entries.items())
    )
    return _ElToritoSignature(
        catalog_path=catalog_path,
        catalog_block_count=catalog_block_count,
        entries=parsed_entries,
    )


def _parse_system_area_signature(report: str) -> _SystemAreaSignature:
    options: str | None = None
    summary: tuple[str, ...] | None = None
    partition_offset: int | None = None
    mbr_heads: int | None = None
    mbr_sectors: int | None = None
    mbr_partitions: dict[int, tuple[str, str]] = {}
    indexed: dict[tuple[str, int], str] = {}

    for raw_line in report.splitlines():
        line = raw_line.strip()
        lower_line = line.lower()
        if lower_line.startswith("system area options"):
            value = line.partition(":")[2].strip().lower()
            if not re.fullmatch(r"0x[0-9a-f]+", value):
                raise IsoBuilderError("system_area_inspection_invalid")
            options = value
            continue
        if lower_line.startswith("system area summary"):
            values = tuple(line.partition(":")[2].strip().split())
            if not values or "not-recognized" in {value.lower() for value in values}:
                raise IsoBuilderError("system_area_inspection_invalid")
            summary = values
            continue
        if lower_line.startswith("partition offset"):
            partition_offset = _parsed_report_integer(line, "system_area_inspection_invalid")
            continue
        if lower_line.startswith("mbr heads per cyl"):
            mbr_heads = _parsed_report_integer(line, "system_area_inspection_invalid")
            continue
        if lower_line.startswith("mbr secs per head"):
            mbr_sectors = _parsed_report_integer(line, "system_area_inspection_invalid")
            continue
        if lower_line.startswith("mbr partition") and not lower_line.startswith(
            "mbr partition table"
        ):
            match = MBR_PARTITION_RE.fullmatch(line)
            if match is None:
                raise IsoBuilderError("system_area_inspection_invalid")
            number = int(match.group("number"))
            if number in mbr_partitions:
                raise IsoBuilderError("system_area_inspection_invalid")
            mbr_partitions[number] = (
                match.group("status").lower(),
                match.group("type").lower(),
            )
            continue

        match = SYSTEM_AREA_INDEXED_VALUE_RE.fullmatch(line)
        if match is not None:
            label = " ".join(match.group("label").lower().split())
            number = int(match.group("number"))
            value = _normalized_boot_path(match.group("value").strip())
            key = (label, number)
            if key in indexed or not value:
                raise IsoBuilderError("system_area_inspection_invalid")
            indexed[key] = value.lower()

    if options is None or summary is None:
        raise IsoBuilderError("system_area_inspection_invalid")
    summary_words = {value.upper() for value in summary}
    if "MBR" in summary_words and any(
        value is None for value in (partition_offset, mbr_heads, mbr_sectors)
    ):
        raise IsoBuilderError("system_area_inspection_invalid")
    indexed_labels = {key[0] for key in indexed}
    if "GPT" in summary_words and "gpt type guid" not in indexed_labels:
        raise IsoBuilderError("system_area_inspection_invalid")
    if "APM" in summary_words and "apm partition type" not in indexed_labels:
        raise IsoBuilderError("system_area_inspection_invalid")

    return _SystemAreaSignature(
        options=options,
        summary=summary,
        partition_offset=partition_offset,
        mbr_heads_per_cylinder=mbr_heads,
        mbr_sectors_per_head=mbr_sectors,
        mbr_partitions=tuple(
            (number, values[0], values[1]) for number, values in sorted(mbr_partitions.items())
        ),
        indexed_characteristics=tuple(
            (label, number, value) for (label, number), value in sorted(indexed.items())
        ),
    )


def _parsed_report_integer(line: str, error_code: str) -> int:
    value = line.partition(":")[2].strip()
    if not value.isdigit():
        raise IsoBuilderError(error_code)
    return int(value)


def _normalized_boot_path(value: str) -> str:
    normalized = INTERVAL_RANGE_RE.sub(
        lambda match: f"{match.group('prefix')}<relocated>{match.group('suffix')}",
        value,
    )
    return APPENDED_PARTITION_RANGE_RE.sub(
        lambda match: f"{match.group('prefix')}_start_<relocated>_size_<relocated>",
        normalized,
    )


def _boot_platforms(equipment: _BootEquipmentSignature) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            entry.platform for entry in equipment.el_torito.entries if entry.bootable == "y"
        )
    )


def _validated_network_name(value: str, *, label: str) -> str:
    normalized = value.strip().rstrip(".").lower()
    try:
        ipaddress.ip_address(normalized)
        return normalized
    except ValueError:
        labels = normalized.split(".")
        if len(labels) < 2 or any(not HOST_LABEL_RE.fullmatch(item) for item in labels):
            raise ValueError(f"{label} must be an IP address or FQDN") from None
        return normalized


def _generation_intent_digest(request: EsxiInstallerArtifactRequest) -> str:
    payload = {
        "profile_id": request.profile_id,
        "profile_version": request.profile_version,
        "profile_fingerprint": request.profile_fingerprint.lower(),
        "source_iso_sha256": request.expected_source_iso_sha256.lower(),
        "hostname": request.hostname,
        "management_ip": str(request.management_ip),
        "subnet_cidr": str(request.subnet_cidr),
        "gateway": str(request.gateway),
        "dns_servers": [str(value) for value in request.dns_servers],
        "ntp_servers": list(request.ntp_servers),
        "management_nic": request.management_nic,
        "management_vlan_id": request.management_vlan_id,
        "install_disk_id": request.install_disk_id,
        "system_media_size": request.system_media_size,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _restrict_local_file(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _safe_profile_slug(profile_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", profile_id).strip("-") or "profile"


def _blocked_next_action(failure_code: str) -> str:
    if failure_code == "builder_dependency_missing":
        return (
            f"Install GNU xorriso {MINIMUM_XORRISO_VERSION_LABEL} or newer locally, "
            "verify its isolated version check, and rerun the same offline request."
        )
    if failure_code == "source_checksum_mismatch":
        return "Review the selected source media and explicitly approve its exact SHA-256."
    if failure_code in {"preflight_blocked", "request_validation_failed"}:
        return "Correct the explicit request or active saved profile; do not attach the source ISO."
    return "Inspect the failure code, correct the offline build prerequisite, and rerun; do not attach an unvalidated artifact."


def _display(path: Path) -> str:
    return display_path(path, REPO_ROOT)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _now() -> str:
    return datetime.now(UTC).isoformat()
