"""Offline SUM discovery and report-only command construction, never deployment.

This module deliberately does not launch SUM. A supervised isolated runner and a
versioned vendor-report parser are required before exposing live plan endpoints.
"""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Literal

import pycdlib

from app.services.firmware_packages import FirmwarePackageError, media_path, package_unchanged

Report = Literal["preview", "firmware", "dependency", "inventory"]
REPORT_FLAGS = {
    "preview": "--report",
    "firmware": "--firmware_report",
    "dependency": "--dependency_report",
    "inventory": "--inventory_report",
}


def _file_identity(iso, path, limit):
    record = iso.get_record(rr_path=path)
    if record.is_symlink() or not 0 < record.data_length <= limit:
        raise FirmwarePackageError("SUM bundle member is unsafe or exceeds the inspection limit.")
    digest = hashlib.sha256()
    count = 0
    with iso.open_file_from_iso(rr_path=path) as source:
        while chunk := source.read(1024**2):
            count += len(chunk)
            if count > limit:
                raise FirmwarePackageError("SUM bundle member exceeds the inspection limit.")
            digest.update(chunk)
    if count != record.data_length:
        raise FirmwarePackageError("SUM bundle member is truncated.")
    return {"path": path, "size_bytes": count, "sha256": digest.hexdigest()}


def inspect_sum_bundle(package: dict) -> dict:
    if not package_unchanged(package):
        raise FirmwarePackageError("Selected SPP changed. Select it again.")
    iso = pycdlib.PyCdlib()
    try:
        iso.open(str(media_path(package["path"])))
        markers = []
        count = 0
        for directory, folders, files in iso.walk(rr_path="/packages"):
            count += len(folders) + len(files)
            if count > 20000:
                raise FirmwarePackageError("SUM bundle directory exceeds the inspection limit.")
            if directory.rstrip("/") == "/packages":
                markers.extend(
                    name for name in files if re.fullmatch(r"sum[0-9]{3,5}_b[0-9]+\.txt", name)
                )
        if len(markers) != 1:
            raise FirmwarePackageError("The SPP must identify exactly one bundled SUM build.")
        marker = _file_identity(iso, "/packages/" + markers[0], 4096)
        launcher = _file_identity(iso, "/packages/smartupdate", 1024**2)
        binary = _file_identity(iso, "/packages/x64/sum_bin_x64", 128 * 1024**2)
        if not package_unchanged(package):
            raise FirmwarePackageError("Selected SPP changed during SUM inspection.")
        return {
            "source": "local-spp-inspection",
            "build_marker": markers[0],
            "members": [marker, launcher, binary],
            "binary_authenticated": False,
            "runtime_verified": False,
            "hardware_support_verified": False,
            "can_apply": False,
        }
    except FirmwarePackageError:
        raise
    except Exception:
        raise FirmwarePackageError(
            "The selected SPP does not contain a readable supported SUM layout."
        ) from None
    finally:
        try:
            iso.close()
        except Exception:
            pass


@dataclass(frozen=True)
class ReportInvocation:
    argv: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]
    input_content: str = field(repr=False)
    network_target: str = field(repr=False)
    report: Report


def _path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not path.is_absolute()
        or ".." in path.parts
        or not re.fullmatch(r"/[A-Za-z0-9_./-]+", value)
    ):
        raise ValueError("SUM runner paths must be absolute controlled paths.")
    return value


def _input_value(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 1024
        or any(c in value for c in "\r\n\x00[]")
    ):
        raise ValueError("SUM connection fields must be single-line input-file values.")
    return value


def report_invocation(
    *,
    report: Report,
    executable: str,
    input_path: str,
    report_dir: str,
    baseline: str,
    host: str,
    username: str,
    password: str,
) -> ReportInvocation:
    """Server-owned values only; secrets go in a restricted temporary file, not argv."""
    if report not in REPORT_FLAGS:
        raise ValueError("Only read-only SUM reports are supported by this adapter.")
    binary = PurePosixPath(_path(executable))
    if binary.name != "sum_bin_x64" or binary.parent.name != "x64":
        raise ValueError("Use the inspected SUM binary in its x64 bundle directory.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:-]{0,252}", host):
        raise ValueError("Use one exact saved SUM target without URL paths or options.")
    content = "\n".join(
        [
            "SILENT = YES",
            "DRYRUN = YES",
            f"SOURCEPATH = {_path(baseline)}",
            "[TARGETS]",
            f"HOST = {_input_value(host)}",
            "TARGETTYPE = iLO",
            f"UID = {_input_value(username)}",
            f"PWD = {_input_value(password)}",
            "[END]",
            "",
        ]
    )
    return ReportInvocation(
        argv=(
            _path(executable),
            "--s",
            REPORT_FLAGS[report],
            "--dryrun",
            "--inputfile",
            _path(input_path),
            "--reportdir",
            _path(report_dir),
        ),
        # The vendor launcher supplies these selectors. Call the binary without its
        # shell/eval wrapper, preserving the documented input-file/legacy mode.
        environment=(
            ("PATH", "/usr/bin:/bin"),
            ("SUM_ROOT", str(binary.parent.parent)),
            ("LEGACYMODE", "1"),
            ("INPUTFILEPATH", _path(input_path)),
            ("USERNAME", ""),
            ("PASSWORD", ""),
            ("USECURRCRED", ""),
            ("USELOCATION", "0"),
            ("VERSION", "0"),
            ("HELP", "0"),
        ),
        input_content=content,
        network_target=host,
        report=report,
    )
