from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import esxi_installer_artifact as artifact
from app.services.esxi_installer_artifact import (
    BIOS_BOOT_CFG_ISO_PATH,
    KICKSTART_BOOT_OPTION,
    UEFI_BOOT_CFG_ISO_PATH,
    EsxiIsoBuildEvidence,
    EsxiInstallerArtifactRequest,
    prepare_esxi_installer_artifact,
)
from app.services.lab_profiles import lab_profile_context_fingerprint

PASSWORD_HASH = f"$6$salt1234${'A' * 86}"

SOURCE_BOOT_REPORT = """
El Torito catalog  : 42  1
El Torito cat path : /boot.catalog
El Torito images   :   N  Pltf  B   Emul  Ld_seg  Hdpt  Ldsiz         LBA
El Torito boot img :   1  BIOS  y   none  0x0000  0x00      4         100
El Torito boot img :   2  UEFI  y   none  0x0000  0x00   8192         200
El Torito img path :   1  /ISOLINUX.BIN
El Torito img opts :   1  boot-info-table isohybrid-suitable
El Torito img path :   2  /EFI/BOOT/EFIBOOT.IMG
System area options: 0x00000102
System area summary: MBR isohybrid cyl-align-on GPT
ISO image size/512 : 100000
Partition offset   : 0
MBR heads per cyl  : 64
MBR secs per head  : 32
MBR partition table:   N Status  Type        Start       Blocks
MBR partition      :   1   0x80  0x17            0       100000
MBR partition      :   2   0x00  0xef        90000         8192
GPT disk GUID      :      aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
GPT partition GUID :   1  aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01
GPT type GUID      :   1  a2a0d0ebe5b9334487c068b6b72699c7
GPT partition flags:   1  0x1000000000000001
GPT partition name :   1  4700610070003000
GPT partname local :   1  Gap0
GPT start and size :   1  64  89936
GPT partition GUID :   2  aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa02
GPT type GUID      :   2  c12a7328f81f11d2ba4b00a0c93ec93b
GPT partition flags:   2  0x0000000000000000
GPT partition name :   2  450046004900
GPT partname local :   2  EFI
GPT partition path :   2  /EFI/BOOT/EFIBOOT.IMG
GPT start and size :   2  90000  8192
"""

DERIVED_BOOT_REPORT = """
El Torito catalog  : 142  1
El Torito cat path : /boot.catalog
El Torito images   :   N  Pltf  B   Emul  Ld_seg  Hdpt  Ldsiz         LBA
El Torito boot img :   1  BIOS  y   none  0x0000  0x00      4         300
El Torito boot img :   2  UEFI  y   none  0x0000  0x00   8192         400
El Torito img path :   1  /ISOLINUX.BIN
El Torito img opts :   1  boot-info-table isohybrid-suitable
El Torito img path :   2  /EFI/BOOT/EFIBOOT.IMG
System area options: 0x00000102
System area summary: MBR isohybrid cyl-align-on GPT
ISO image size/512 : 101024
Partition offset   : 0
MBR heads per cyl  : 64
MBR secs per head  : 32
MBR partition table:   N Status  Type        Start       Blocks
MBR partition      :   1   0x80  0x17            0       101024
MBR partition      :   2   0x00  0xef        91024         8192
GPT disk GUID      :      bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
GPT partition GUID :   1  bbbbbbbbbbbbbbbbbbbbbbbbbbbbbb01
GPT type GUID      :   1  a2a0d0ebe5b9334487c068b6b72699c7
GPT partition flags:   1  0x1000000000000001
GPT partition name :   1  4700610070003000
GPT partname local :   1  Gap0
GPT start and size :   1  64  90960
GPT partition GUID :   2  bbbbbbbbbbbbbbbbbbbbbbbbbbbbbb02
GPT type GUID      :   2  c12a7328f81f11d2ba4b00a0c93ec93b
GPT partition flags:   2  0x0000000000000000
GPT partition name :   2  450046004900
GPT partname local :   2  EFI
GPT partition path :   2  /EFI/BOOT/EFIBOOT.IMG
GPT start and size :   2  91024  8192
"""


class FakeIsoBuilder:
    name = "xorriso"
    version = "xorriso fake 1.0"

    def __init__(self, *, valid: bool = True) -> None:
        self.valid = valid
        self.calls = 0
        self.source_paths: list[Path] = []
        self.kickstart: bytes | None = None

    def build(
        self,
        *,
        source_iso: Path,
        output_iso: Path,
        kickstart_path: Path,
        boot_options: tuple[str, ...],
    ) -> EsxiIsoBuildEvidence:
        self.calls += 1
        self.source_paths.append(source_iso)
        self.kickstart = kickstart_path.read_bytes()
        output_iso.write_bytes(b"derived-iso\n" + source_iso.read_bytes() + self.kickstart)
        kickstart_sha256 = hashlib.sha256(self.kickstart).hexdigest()
        return EsxiIsoBuildEvidence(
            builder_name="xorriso",
            builder_version=self.version,
            kickstart_readback_sha256=(kickstart_sha256 if self.valid else "0" * 64),
            boot_config_paths=(BIOS_BOOT_CFG_ISO_PATH, UEFI_BOOT_CFG_ISO_PATH),
            boot_options=boot_options,
            bios_boot_config_verified=self.valid,
            uefi_boot_config_verified=self.valid,
            source_boot_platforms=("BIOS", "UEFI"),
            derived_boot_platforms=(("BIOS", "UEFI") if self.valid else ("BIOS",)),
            el_torito_equipment_equivalent=self.valid,
            system_area_equivalent=self.valid,
            source_system_area_summary=("MBR", "isohybrid", "cyl-align-on", "GPT"),
            derived_system_area_summary=(
                ("MBR", "isohybrid", "cyl-align-on", "GPT")
                if self.valid
                else ("MBR", "cyl-align-off")
            ),
        )


def test_successful_offline_build_is_profile_bound_checksummed_and_secret_safe(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    source_iso = media_root / "source-esxi.iso"
    source_iso.write_bytes(b"immutable-source-iso")
    source_before = source_iso.read_bytes()
    context = _profile_context()
    request = _request(source_iso, context)
    builder = FakeIsoBuilder()
    result, report_json, report_markdown = _prepare(
        request,
        context,
        media_root,
        builder,
        tmp_path,
    )

    assert result["status"] == "ready"
    assert result["hardware_contacted"] is False
    assert result["provider_calls_attempted"] == 0
    assert result["source_iso_write_attempted"] is False
    assert result["credential_handling"]["plaintext_root_credential_accepted"] is False
    assert result["source_iso"]["source_snapshot_used"] is True
    assert result["source_iso"]["source_iso_modified"] is False
    assert source_iso.read_bytes() == source_before
    assert builder.calls == 1
    assert builder.source_paths[0] != source_iso
    assert builder.source_paths[0].name == "source.iso"

    derived = Path(result["derived_artifact"]["iso"])
    manifest = Path(result["derived_artifact"]["manifest"])
    sidecar = Path(result["derived_artifact"]["checksum_sidecar"])
    assert derived.is_file()
    assert manifest.is_file()
    assert sidecar.is_file()
    assert _sha256(derived) == result["derived_artifact"]["iso_sha256"]
    assert sidecar.read_text(encoding="utf-8") == (f"{_sha256(derived)}  {derived.name}\n")
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["profile_binding"]["profile_id"] == request["profile_id"]
    assert manifest_payload["source_iso"]["sha256"] == _sha256(source_iso)
    assert manifest_payload["boot_configuration"]["bios_verified"] is True
    assert manifest_payload["boot_configuration"]["uefi_verified"] is True
    assert manifest_payload["boot_configuration"]["source_platforms"] == [
        "BIOS",
        "UEFI",
    ]
    assert manifest_payload["boot_configuration"]["derived_platforms"] == [
        "BIOS",
        "UEFI",
    ]
    assert manifest_payload["boot_configuration"]["el_torito_replayed"] is True
    assert manifest_payload["boot_configuration"]["system_area_replayed"] is True

    rendered_reports = "\n".join(
        [
            json.dumps(result, default=str),
            report_json.read_text(encoding="utf-8"),
            report_markdown.read_text(encoding="utf-8"),
            manifest.read_text(encoding="utf-8"),
        ]
    )
    assert PASSWORD_HASH not in rendered_reports
    assert str(source_iso) not in rendered_reports
    assert request["hostname"] not in rendered_reports
    assert builder.kickstart is not None
    kickstart = builder.kickstart.decode()
    assert f"rootpw --iscrypted {PASSWORD_HASH}" in kickstart
    assert "password=" not in kickstart.lower()
    assert "--disk=naa.600508b1001cafe0" in kickstart
    assert "--nameserver=192.0.2.53" in kickstart
    assert "dns server add --server=192.0.2.54" in kickstart
    assert "ntp set -s ntp1.example.test -s ntp2.example.test -e 1" in kickstart
    assert "\r" not in kickstart


def test_plaintext_password_is_refused_without_echoing_it(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    source_iso = media_root / "source.iso"
    source_iso.write_bytes(b"iso")
    context = _profile_context()
    request = _request(source_iso, context)
    request["root_password_sha512_crypt"] = "Plaintext-should-never-appear"
    builder = FakeIsoBuilder()
    result, report_json, report_markdown = _prepare(
        request,
        context,
        media_root,
        builder,
        tmp_path,
    )

    assert result["status"] == "blocked"
    assert result["failure_code"] == "request_validation_failed"
    assert builder.calls == 0
    rendered = (
        json.dumps(result)
        + report_json.read_text(encoding="utf-8")
        + report_markdown.read_text(encoding="utf-8")
    )
    assert "Plaintext-should-never-appear" not in rendered


def test_profile_mismatch_blocks_before_builder_or_artifact_write(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    source_iso = media_root / "source.iso"
    source_iso.write_bytes(b"iso")
    context = _profile_context()
    request = _request(source_iso, context)
    request["management_ip"] = "192.0.2.99"
    builder = FakeIsoBuilder()
    result, _, _ = _prepare(request, context, media_root, builder, tmp_path)

    assert result["status"] == "blocked"
    assert result["failure_code"] == "preflight_blocked"
    assert "management_ip does not exactly match" in " ".join(result["blockers"])
    assert builder.calls == 0
    assert not list((tmp_path / "derived").rglob("*.iso"))


def test_source_outside_media_inventory_root_is_refused(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "allowed"
    media_root.mkdir()
    source_iso = tmp_path / "outside.iso"
    source_iso.write_bytes(b"iso")
    context = _profile_context()
    request = _request(source_iso, context)
    builder = FakeIsoBuilder()
    result, _, _ = _prepare(request, context, media_root, builder, tmp_path)

    assert result["status"] == "blocked"
    assert "outside MEDIA_INVENTORY_DIRS" in " ".join(result["blockers"])
    assert builder.calls == 0


def test_unapproved_source_checksum_is_refused_before_snapshot_or_build(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    source_iso = media_root / "source.iso"
    source_iso.write_bytes(b"iso")
    context = _profile_context()
    request = _request(source_iso, context)
    request["expected_source_iso_sha256"] = "0" * 64
    builder = FakeIsoBuilder()
    result, _, _ = _prepare(request, context, media_root, builder, tmp_path)

    assert result["status"] == "blocked"
    assert result["failure_code"] == "source_checksum_mismatch"
    assert builder.calls == 0
    assert source_iso.read_bytes() == b"iso"
    assert not (tmp_path / "derived").exists()


def test_missing_xorriso_dependency_fails_closed_without_writing_media(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    source_iso = media_root / "source.iso"
    source_iso.write_bytes(b"iso")
    context = _profile_context()
    request = _request(source_iso, context)
    monkeypatch.setattr(artifact.XorrisoEsxiIsoBuilder, "discover", lambda: None)
    report_json = tmp_path / "report.json"
    report_markdown = tmp_path / "report.md"

    result = prepare_esxi_installer_artifact(
        request,
        profile_context=context,
        allowed_media_roots=(media_root,),
        derived_media_root=tmp_path / "derived",
        report_json=report_json,
        report_markdown=report_markdown,
    )

    assert result["status"] == "blocked"
    assert result["failure_code"] == "builder_dependency_missing"
    assert result["hardware_contacted"] is False
    assert "1.5.8.pl02 or newer" in " ".join(result["blockers"])
    assert not (tmp_path / "derived").exists()
    assert source_iso.read_bytes() == b"iso"


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("xorriso version   :  1.5.8", None),
        ("xorriso version   :  1.5.8.pl01", None),
        ("xorriso version   :  1.5.8.pl02", "1.5.8.pl02"),
        ("GNU xorriso 1.5.9 : development snapshot", "1.5.9"),
        ("not xorriso output", None),
    ],
)
def test_xorriso_version_floor_requires_patched_replay_release(
    output: str,
    expected: str | None,
) -> None:
    assert artifact._supported_xorriso_version(output) == expected


def test_xorriso_discovery_and_commands_disable_startup_files_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(
            returncode=0,
            stdout="xorriso version   :  1.5.8.pl02\n",
            stderr="",
        )

    monkeypatch.setattr(artifact.shutil, "which", lambda _name: "C:/tools/xorriso.exe")
    monkeypatch.setattr(artifact.subprocess, "run", fake_run)

    builder = artifact.XorrisoEsxiIsoBuilder.discover()
    assert builder is not None
    assert builder.version == "xorriso 1.5.8.pl02"
    assert commands == [["C:/tools/xorriso.exe", "-no_rc", "-version"]]

    builder._run(("-abort_on", "FAILURE", "-end"), error_code="test_failed")
    assert commands[-1][:3] == [
        "C:/tools/xorriso.exe",
        "-no_rc",
        "-abort_on",
    ]

    builder._boot_report(Path("source.iso"))
    assert commands[-1][1] == "-no_rc"
    assert commands[-1][-5:] == [
        "-report_el_torito",
        "plain",
        "-report_system_area",
        "plain",
        "-end",
    ]


def test_xorriso_discovery_rejects_unpatched_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(artifact.shutil, "which", lambda _name: "C:/tools/xorriso.exe")
    monkeypatch.setattr(
        artifact.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="xorriso version   :  1.5.8.pl01\n",
            stderr="",
        ),
    )

    assert artifact.XorrisoEsxiIsoBuilder.discover() is None
    with pytest.raises(ValueError, match="1.5.8.pl02 or newer"):
        artifact.XorrisoEsxiIsoBuilder("C:/tools/xorriso.exe", "xorriso 1.5.8.pl01")


def test_boot_equipment_comparison_allows_only_relocated_addresses_and_sizes() -> None:
    source = artifact._parse_boot_equipment(SOURCE_BOOT_REPORT)
    derived = artifact._parse_boot_equipment(DERIVED_BOOT_REPORT)

    assert artifact._boot_platforms(source) == ("BIOS", "UEFI")
    assert artifact._boot_platforms(derived) == ("BIOS", "UEFI")
    assert source.el_torito == derived.el_torito
    assert source.system_area == derived.system_area


def test_boot_equipment_comparison_detects_catalog_and_system_area_changes() -> None:
    source = artifact._parse_boot_equipment(SOURCE_BOOT_REPORT)
    changed_load_size = artifact._parse_boot_equipment(
        DERIVED_BOOT_REPORT.replace(
            "UEFI  y   none  0x0000  0x00   8192",
            "UEFI  y   none  0x0000  0x00   4096",
        )
    )
    changed_system_area = artifact._parse_boot_equipment(
        DERIVED_BOOT_REPORT.replace(
            "System area options: 0x00000102",
            "System area options: 0x00000202",
        )
    )

    assert source.el_torito != changed_load_size.el_torito
    assert source.system_area != changed_system_area.system_area


def test_boot_equipment_requires_explicit_bios_and_uefi_platform_entries() -> None:
    missing_uefi = artifact._parse_boot_equipment(
        SOURCE_BOOT_REPORT.replace(
            "El Torito boot img :   2  UEFI",
            "El Torito boot img :   2  PPC ",
        )
    )

    assert artifact._boot_platforms(missing_uefi) == ("BIOS", "PPC")
    with pytest.raises(artifact.IsoBuilderError) as exc_info:
        artifact._parse_boot_equipment("El Torito is present\nSystem area summary: MBR\n")
    assert exc_info.value.code == "boot_equipment_inspection_invalid"

    evidence = EsxiIsoBuildEvidence(
        builder_name="xorriso",
        builder_version="xorriso 1.5.8.pl02",
        kickstart_readback_sha256="a" * 64,
        boot_config_paths=(BIOS_BOOT_CFG_ISO_PATH, UEFI_BOOT_CFG_ISO_PATH),
        boot_options=(KICKSTART_BOOT_OPTION,),
        bios_boot_config_verified=True,
        uefi_boot_config_verified=True,
        source_boot_platforms=artifact._boot_platforms(missing_uefi),
        derived_boot_platforms=("BIOS", "UEFI"),
        el_torito_equipment_equivalent=False,
        system_area_equivalent=True,
        source_system_area_summary=missing_uefi.system_area.summary,
        derived_system_area_summary=missing_uefi.system_area.summary,
    )
    blockers = artifact._build_evidence_blockers(
        evidence,
        expected_kickstart_sha256="a" * 64,
        expected_boot_options=(KICKSTART_BOOT_OPTION,),
    )
    assert any("Source ISO does not prove bootable BIOS and UEFI" in item for item in blockers)


def test_secure_boot_firstboot_conflict_fails_closed(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    source_iso = media_root / "source.iso"
    source_iso.write_bytes(b"iso")
    context = _profile_context()
    request = _request(source_iso, context)
    request["secure_boot_expected"] = True
    builder = FakeIsoBuilder()
    result, _, _ = _prepare(request, context, media_root, builder, tmp_path)

    assert result["status"] == "blocked"
    assert "%firstboot" in " ".join(result["blockers"])
    assert builder.calls == 0


def test_invalid_iso_readback_is_not_published(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    source_iso = media_root / "source.iso"
    source_iso.write_bytes(b"iso")
    context = _profile_context()
    request = _request(source_iso, context)
    builder = FakeIsoBuilder(valid=False)
    result, _, _ = _prepare(request, context, media_root, builder, tmp_path)

    assert result["status"] == "blocked"
    assert result["failure_code"] == "derived_iso_readback_failed"
    assert builder.calls == 1
    assert not list((tmp_path / "derived").rglob("*.iso"))


def test_manifest_failure_does_not_publish_a_partial_iso_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    source_iso = media_root / "source.iso"
    source_iso.write_bytes(b"iso")
    context = _profile_context()
    request = _request(source_iso, context)
    builder = FakeIsoBuilder()
    original_write_json = artifact.write_json_object

    def fail_manifest(path: Path, payload: dict, **kwargs) -> None:
        if path.name.endswith(".manifest.json"):
            raise OSError("simulated manifest failure")
        original_write_json(path, payload, **kwargs)

    monkeypatch.setattr(artifact, "write_json_object", fail_manifest)
    result, _, _ = _prepare(request, context, media_root, builder, tmp_path)

    assert result["status"] == "blocked"
    assert result["failure_code"] == "artifact_build_io_failed"
    assert builder.calls == 1
    assert not list((tmp_path / "derived").rglob("*.iso"))


def test_identical_content_addressed_build_reuses_complete_bundle(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    source_iso = media_root / "source.iso"
    source_iso.write_bytes(b"iso")
    context = _profile_context()
    request = _request(source_iso, context)
    first, _, _ = _prepare(
        request,
        context,
        media_root,
        FakeIsoBuilder(),
        tmp_path,
    )
    second, _, _ = _prepare(
        request,
        context,
        media_root,
        FakeIsoBuilder(),
        tmp_path,
    )

    assert first["status"] == second["status"] == "ready"
    assert first["derived_artifact"]["iso"] == second["derived_artifact"]["iso"]
    assert (
        first["derived_artifact"]["manifest_sha256"]
        == second["derived_artifact"]["manifest_sha256"]
    )
    assert len(list((tmp_path / "derived").rglob("*.iso"))) == 1


def test_boot_cfg_update_is_exact_and_refuses_prior_customization() -> None:
    updated = artifact._updated_boot_cfg(
        "bootstate=0\r\nkernelopt=runweasel cdromBoot\r\nmodules=a.v00\r\n",
        (KICKSTART_BOOT_OPTION, "systemMediaSize=min"),
    )

    assert "\r" not in updated
    assert "kernelopt=runweasel cdromBoot ks=cdrom:/KS.CFG systemMediaSize=min" in updated
    assert artifact._boot_cfg_has_options(
        updated,
        (KICKSTART_BOOT_OPTION, "systemMediaSize=min"),
    )
    with pytest.raises(artifact.IsoBuilderError) as exc_info:
        artifact._updated_boot_cfg(
            "kernelopt=runweasel ks=http://example.test/ks.cfg\n",
            (KICKSTART_BOOT_OPTION,),
        )
    assert exc_info.value.code == "source_boot_config_already_customized"


def test_request_model_repr_does_not_expose_password_hash(tmp_path: Path) -> None:
    source_iso = tmp_path / "source.iso"
    source_iso.write_bytes(b"iso")
    context = _profile_context()
    request = EsxiInstallerArtifactRequest.model_validate(_request(source_iso, context))

    assert PASSWORD_HASH not in repr(request)
    assert "**********" in repr(request)


def _prepare(
    request: dict,
    context: dict,
    media_root: Path,
    builder: FakeIsoBuilder,
    tmp_path: Path,
) -> tuple[dict, Path, Path]:
    report_json = tmp_path / "reports" / "report.json"
    report_markdown = tmp_path / "reports" / "report.md"
    result = prepare_esxi_installer_artifact(
        request,
        profile_context=context,
        allowed_media_roots=(media_root,),
        builder=builder,
        derived_media_root=tmp_path / "derived",
        report_json=report_json,
        report_markdown=report_markdown,
    )
    return result, report_json, report_markdown


def _profile_context() -> dict:
    features = {
        "deployment_mode": "single_server_local_storage",
        "storage_location": "server_local",
    }
    active = {
        "id": "lab-single-server",
        "version": 7,
        "source": "saved",
        "subnet_cidr": "192.0.2.0/24",
        "gateway": "192.0.2.1",
        "dns": ["192.0.2.53", "192.0.2.54"],
        "ntp": ["ntp1.example.test", "ntp2.example.test"],
        "global_settings": {
            "gateway": "192.0.2.1",
            "dns_servers": ["192.0.2.53", "192.0.2.54"],
            "ntp_servers": ["ntp1.example.test", "ntp2.example.test"],
            "vlan_id": 100,
            "domain_name": "example.test",
        },
        "features": features,
    }
    return {
        "active_profile": active,
        "resolved_address_plan": {
            "subnet": "192.0.2.0/24",
            "esxi_management": "192.0.2.203",
        },
        "enabled_features": features,
    }


def _request(source_iso: Path, context: dict) -> dict:
    return {
        "profile_id": "lab-single-server",
        "profile_version": 7,
        "profile_fingerprint": lab_profile_context_fingerprint(context),
        "source_iso_path": str(source_iso.resolve()),
        "expected_source_iso_sha256": _sha256(source_iso),
        "hostname": "esxi01.example.test",
        "management_ip": "192.0.2.203",
        "subnet_cidr": "192.0.2.0/24",
        "gateway": "192.0.2.1",
        "dns_servers": ["192.0.2.53", "192.0.2.54"],
        "ntp_servers": ["ntp1.example.test", "ntp2.example.test"],
        "management_nic": "vmnic0",
        "management_vlan_id": 100,
        "install_disk_id": "naa.600508b1001cafe0",
        "system_media_size": "min",
        "root_password_sha512_crypt": PASSWORD_HASH,
        "secure_boot_expected": False,
        "allow_firstboot_network_services": True,
        "local_datastore_expected": True,
        "acknowledge_install_disk_overwrite": True,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
