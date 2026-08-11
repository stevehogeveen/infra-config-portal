from __future__ import annotations

from pathlib import Path

import pytest

from app.services import lab_credentials


@pytest.fixture(autouse=True)
def _isolated_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env.local.real-lab"
    trigger_file = tmp_path / "main.py"
    trigger_file.write_text("# reload trigger stub\n", encoding="utf-8")
    monkeypatch.setattr(lab_credentials, "REAL_LAB_ENV_FILE", env_file)
    monkeypatch.setattr(lab_credentials, "RELOAD_TRIGGER_FILE", trigger_file)
    return env_file


def test_update_survives_blank_or_bom_lines_in_existing_file(_isolated_env_file: Path) -> None:
    # A real-world env file can carry a leading UTF-8 BOM (dotenv_values then
    # reports a stray key with a None value) or another blank/unparseable
    # line. Regression for a crash: _write_env_file assumed every existing
    # value was a string and blew up on `None.replace(...)`.
    _isolated_env_file.write_bytes(
        b"\xef\xbb\xbfLAB_ENVIRONMENT=isolated-real-lab\nESXI_TEST_HOST=192.0.2.10\n"
    )

    result = lab_credentials.update_lab_credentials({"esxi_host": "192.0.2.20"})

    esxi_group = next(g for g in result["groups"] if g["id"] == "esxi")
    host_field = next(f for f in esxi_group["fields"] if f["field"] == "esxi_host")
    assert host_field["value"] == "192.0.2.20"

    on_disk = _isolated_env_file.read_text(encoding="utf-8")
    assert 'ESXI_TEST_HOST="192.0.2.20"' in on_disk
    # The bogus BOM "key" must not be written back.
    assert "﻿" not in on_disk


def test_update_preserves_unrelated_existing_keys(_isolated_env_file: Path) -> None:
    # Regression for writing to the wrong file location: this service must
    # merge into whatever is already at REAL_LAB_ENV_FILE rather than
    # replacing it, since that file is shared with everything else that
    # reads real-lab configuration (60+ keys in the real deployment).
    _isolated_env_file.write_text(
        'LAB_ENVIRONMENT=isolated-real-lab\nCISCO_TARGET_IP="192.168.1.204"\n',
        encoding="utf-8",
    )

    lab_credentials.update_lab_credentials({"esxi_host": "192.0.2.20"})

    on_disk = _isolated_env_file.read_text(encoding="utf-8")
    assert 'CISCO_TARGET_IP="192.168.1.204"' in on_disk
    assert 'ESXI_TEST_HOST="192.0.2.20"' in on_disk


def test_status_reflects_a_save_immediately_in_the_same_process(_isolated_env_file: Path) -> None:
    # Regression: _field_status read from the frozen Settings snapshot for
    # fields with a settings attribute mapping, so a save's own response
    # kept showing the pre-save value until the process actually restarted.
    _isolated_env_file.write_text(
        'LAB_ENVIRONMENT=isolated-real-lab\nESXI_TEST_HOST="192.0.2.10"\n',
        encoding="utf-8",
    )

    result = lab_credentials.update_lab_credentials({"esxi_host": "192.0.2.20"})

    esxi_group = next(g for g in result["groups"] if g["id"] == "esxi")
    host_field = next(f for f in esxi_group["fields"] if f["field"] == "esxi_host")
    assert host_field["value"] == "192.0.2.20"


def test_ilo_fields_are_no_longer_global_lab_credentials() -> None:
    assert "ilo" not in {group["id"] for group in lab_credentials.CREDENTIAL_GROUPS}
    with pytest.raises(lab_credentials.LabCredentialsError, match="No credential values"):
        lab_credentials.update_lab_credentials({"ilo_host": "192.0.2.30"})
