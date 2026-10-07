import pytest

from app.services.firmware_catalog import ilo_component, next_ilo_version
from app.services.firmware_packages import FirmwarePackageError


@pytest.mark.parametrize(
    "installed,target",
    [("1.37", "1.48"), ("1.48", "3.19"), ("1.48.0", "3.19"), ("2.77", "3.19"), ("3.18", "3.19")],
)
def test_next_supported_update(installed, target):
    assert next_ilo_version(installed) == target


@pytest.mark.parametrize("installed", [None, "unknown", "3.19", "3.19.0", "3.20"])
def test_no_unknown_reinstall_or_downgrade(installed):
    with pytest.raises(FirmwarePackageError):
        next_ilo_version(installed)


@pytest.mark.parametrize("version", [None, "2.78", "../../3.19", "3.19.0"])
def test_only_exact_supported_catalog_versions(version):
    with pytest.raises(FirmwarePackageError):
        ilo_component(version)


def test_exact_319_paths():
    component = ilo_component("3.19")
    assert component.package_path == "/packages/ilo5_319.fwpkg"
    assert component.rpm_path == "/packages/firmware-ilo5-3.19-1.1.x86_64.rpm"
    assert (
        component.binary_member == "./usr/lib/x86_64-linux-gnu/firmware-ilo5-3.19-1.1/ilo5_319.bin"
    )
