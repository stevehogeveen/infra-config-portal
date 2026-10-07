import pytest

from app.services.ilo_upgrade_path import ilo_upgrade_blockers


@pytest.mark.parametrize("installed", ["1.37", "iLO 5 v1.37", "1.47.9"])
def test_legacy_firmware_requires_first_bridge(installed):
    blockers = " ".join(ilo_upgrade_blockers(installed, "3.19", 33557086))
    assert "1.48" in blockers
    assert "2.78" not in blockers


@pytest.mark.parametrize("installed", ["1.48", "1.48.0", "iLO 5 v1.48", "2.77", "2.77.9", "2.78", "2.78.0", "iLO 5 v3.00"])
def test_first_bridge_or_later_passes_version_gate_without_278_hop(installed):
    assert ilo_upgrade_blockers(installed, "3.19", 33557086) == []


def test_raw_size_is_not_the_vendor_format_limit():
    assert ilo_upgrade_blockers("1.37", "1.48", 33556520) == []
    assert ilo_upgrade_blockers("1.48", "2.78", 33556520) == []
    assert "1.48" in " ".join(ilo_upgrade_blockers("1.37", "2.78", 100))
    assert ilo_upgrade_blockers("1.48", "3.19", 100) == []


@pytest.mark.parametrize("installed,target,size", [
    ("unknown", "3.19", 100), ("2.78", "unknown", 100),
    ("3.19", "3.19", 100), ("3.19", "2.78", 100),
    ("2.78", "3.19", None), ("2.78", "3.19", True), ("2.78", "3.19", 0),
])
def test_unknown_or_non_upgrade_fails_closed(installed, target, size):
    assert ilo_upgrade_blockers(installed, target, size)
