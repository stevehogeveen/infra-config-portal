from __future__ import annotations

from app.schemas import LabGlobalSettings


def test_schema_unique_string_lists_strip_split_and_dedupe_values() -> None:
    settings = LabGlobalSettings(
        dns_servers=" 192.168.1.1,192.168.1.1, 192.168.1.2 ,, ",
        ntp_servers=["192.168.1.10", " 192.168.1.10 ", "192.168.1.11"],
    )

    assert settings.dns_servers == ["192.168.1.1", "192.168.1.2"]
    assert settings.ntp_servers == ["192.168.1.10", "192.168.1.11"]
