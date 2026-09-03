from __future__ import annotations

from app.services import control_access


def test_saved_editable_fields_trim_labels_and_values() -> None:
    config = control_access._read_config(
        "ilo",
        {
            "address_plan": {"ilo": "192.0.2.10"},
            "global_settings": {"gateway": "192.0.2.1", "dns_servers": ["192.0.2.53"]},
        },
        {
            "first_time_configuring": False,
            "original_dhcp_ip": "192.0.2.100",
            "username_reference": "local credential reference",
            "password_configured": True,
            "editable_fields": {
                " Management IP ": " 192.0.2.20 ",
                "DNS": " 192.0.2.53, 192.0.2.54 ",
                "NTP": " ",
            },
        },
    )

    fields = {item["label"]: item for item in config["editable_fields"]}

    assert fields["Management IP"] == {
        "label": "Management IP",
        "value": "192.0.2.20",
        "source": "saved_override",
    }
    assert fields["DNS"] == {
        "label": "DNS",
        "value": "192.0.2.53, 192.0.2.54",
        "source": "saved_override",
    }
    assert fields["NTP"]["value"] == "Not set"
    assert fields["NTP"]["source"] == "active_lab_profile"
