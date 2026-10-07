"""Supported SPP iLO images; paths are server-owned, never operator input."""

from dataclasses import dataclass

from app.services.firmware_packages import FirmwarePackageError
from app.services.spp_assessment import numeric_version


@dataclass(frozen=True)
class IloComponent:
    version: str
    directory: str
    rpm_name: str
    filename: str

    @property
    def package_path(self):
        return f"/{self.directory}/{self.filename.removesuffix('.bin')}.fwpkg"

    @property
    def rpm_path(self):
        return f"/{self.directory}/{self.rpm_name}.x86_64.rpm"

    @property
    def binary_member(self):
        return f"./usr/lib/x86_64-linux-gnu/{self.rpm_name}/{self.filename}"


COMPONENTS = {
    "1.48": IloComponent("1.48", "prerequisite", "firmware-ilo5-1.48-3.1", "ilo5_148.bin"),
    "3.19": IloComponent("3.19", "packages", "firmware-ilo5-3.19-1.1", "ilo5_319.bin"),
}


def ilo_component(version: str) -> IloComponent:
    if not isinstance(version, str) or version not in COMPONENTS:
        raise FirmwarePackageError(
            "This iLO firmware version has no supported installation adapter."
        )
    return COMPONENTS[version]


def next_ilo_version(installed: str) -> str:
    current = numeric_version(installed, "ilo") if isinstance(installed, str) else None
    if current is None:
        raise FirmwarePackageError("Read the installed iLO version before preparing an update.")
    width = max(2, len(current))
    current += (0,) * (width - len(current))
    if current < (1, 48) + (0,) * (width - 2):
        return "1.48"
    if current < (3, 19) + (0,) * (width - 2):
        return "3.19"
    raise FirmwarePackageError(
        "iLO is already at or above 3.19; reinstall and downgrade are not enabled."
    )
