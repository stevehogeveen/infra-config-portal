import hashlib
import json
from zipfile import ZipFile

import pytest
from sqlalchemy import select

from app.models import AuditEvent
from app.services.firmware_packages import FirmwarePackageError
from app.services.firmware_standalone import browse_standalone, inspect_standalone


@pytest.fixture
def media(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRMWARE_MEDIA_ROOT", str(tmp_path))
    path = tmp_path / "bridge.fwpkg"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "payload.json",
            json.dumps(
                {
                    "PackageFormat": "FWPKG-v2",
                    "UpdatableBy": ["Bmc"],
                    "Devices": {
                        "Device": [
                            {
                                "DeviceName": "iLO 5",
                                "Version": "1.48",
                                "Target": "fixture-target",
                                "FirmwareImages": [
                                    {
                                        "DirectFlashOk": True,
                                        "Type": "Firmware",
                                        "FileName": "bridge.bin",
                                    }
                                ],
                            }
                        ]
                    },
                }
            ),
        )
        archive.writestr("bridge.bin", b"fixture firmware")
    return path


def test_inspection_records_unknown_power_without_claiming_support(media):
    result = inspect_standalone(media.name)
    assert result["sha256"] == hashlib.sha256(media.read_bytes()).hexdigest()
    assert result["payload"]["declared_version"] == "1.48"
    assert result["payload"]["host_power_requirements_known"] is False
    assert result["signature_verified"] is False
    assert result["can_apply"] is False
    assert browse_standalone()["files"][0]["path"] == media.name


@pytest.mark.parametrize(
    "path",
    [
        "../bridge.fwpkg",
        "/bridge.fwpkg",
        "C:bridge.fwpkg",
        "missing.fwpkg",
        "bridge.iso",
        "bad\x00.fwpkg",
        "bad\n.fwpkg",
        "x" * 513,
    ],
)
def test_invalid_path(media, path):
    with pytest.raises(FirmwarePackageError):
        inspect_standalone(path)


def test_symlink_and_parent_symlink_rejected(media):
    link = media.parent / "link.fwpkg"
    link.symlink_to(media)
    with pytest.raises(FirmwarePackageError, match="symbolic"):
        inspect_standalone(link.name)
    parent = media.parent / "folder-link"
    parent.symlink_to(media.parent, target_is_directory=True)
    with pytest.raises(FirmwarePackageError, match="symbolic"):
        inspect_standalone("folder-link/bridge.fwpkg")
    assert len(browse_standalone()["files"]) == 1


def test_bounded_file_and_changed_during_inspection(media, monkeypatch):
    monkeypatch.setattr("app.services.firmware_standalone.MAX_PACKAGE_BYTES", 1)
    with pytest.raises(FirmwarePackageError, match="too large"):
        inspect_standalone(media.name)
    monkeypatch.setattr("app.services.firmware_standalone.MAX_PACKAGE_BYTES", 100000)
    from app.services.firmware_standalone import inspect_ilo_payload

    def changing(stream):
        result = inspect_ilo_payload(stream)
        media.write_bytes(b"replaced")
        return result

    monkeypatch.setattr("app.services.firmware_standalone.inspect_ilo_payload", changing)
    with pytest.raises(FirmwarePackageError, match="changed"):
        inspect_standalone(media.name)


def test_scoped_selection_preserves_spp(client, db_session, media):
    kit = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Fixture bridge",
            "profile_topology": "custom",
            "subnet_cidr": "192.0.2.0/24",
        },
    ).json()
    base = "/api/v1/rack-plans/" + kit["id"]
    plan = client.put(
        base,
        json={
            "equipment": [
                {"id": "server", "name": "Fixture", "kind": "server", "position": 1, "height": 1}
            ]
        },
    ).json()
    device = plan["equipment"][0]["device_id"]
    base += "/firmware-execution"
    params = {"device_id": device}
    from app.services.audit import record_audit_event

    spp = record_audit_event(
        db_session,
        actor="fixture",
        event_type="kit.firmware_package_selected",
        message="fixture",
        data={"profile_id": kit["id"], "package": {"fixture": True}},
    )
    db_session.commit()
    original = spp.data_json.copy()
    response = client.post(base + "/select-standalone", params=params, json={"path": media.name})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["selection_id"]
    assert result["can_apply"] is False
    assert client.get(base + "/selected-standalone", params=params).json()["selection"] == result
    assert (
        client.get(base + "/selected-standalone", params={"device_id": "wrong"}).status_code == 404
    )
    assert (
        client.post(
            base + "/select-standalone",
            params=params,
            json={"path": media.name, "signature_verified": True},
        ).status_code
        == 422
    )
    db_session.refresh(spp)
    assert spp.data_json == original
    assert (
        len(
            list(
                db_session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.event_type == "kit.firmware_standalone_selected"
                    )
                )
            )
        )
        == 1
    )


def test_bridge_preparation_is_scoped_offline_and_audited(client, db_session, monkeypatch):
    kit = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Fixture signed bridge",
            "profile_topology": "custom",
            "subnet_cidr": "192.0.2.0/24",
        },
    ).json()
    base = "/api/v1/rack-plans/" + kit["id"]
    plan = client.put(
        base,
        json={
            "equipment": [
                {"id": "server", "name": "Fixture", "kind": "server", "position": 1, "height": 1}
            ]
        },
    ).json()
    device = plan["equipment"][0]["device_id"]
    url = base + "/firmware-execution/prepare-spp-bridge"
    assert client.post(url, params={"device_id": device}, json={}).status_code == 409
    from app.services.audit import record_audit_event

    record_audit_event(
        db_session,
        actor="fixture",
        event_type="kit.firmware_package_selected",
        message="fixture",
        data={"profile_id": kit["id"], "package": {"fixture": True}},
    )
    db_session.commit()
    monkeypatch.setattr(
        "app.api.firmware_execution.inspect_spp_bridge", lambda p: {"sha256": "fixture"}
    )
    monkeypatch.setattr(
        "app.api.firmware_execution.verify_bridge_from_spp",
        lambda p, s: {"binary_authenticated": True, "can_apply": False},
    )
    response = client.post(url, params={"device_id": device}, json={})
    assert response.status_code == 200, response.text
    assert response.json()["can_apply"] is False
    assert response.json()["preparation_id"]
    assert response.json()["blockers"] == [
        "Fresh target applicability and prerequisites require review.",
        "Preparation does not authorize installation. Create a separate exact-target firmware install review.",
    ]
    assert client.post(url, params={"device_id": "wrong"}, json={}).status_code == 404
    assert (
        client.post(url, params={"device_id": device}, json={"can_apply": True}).status_code == 422
    )
    events = list(
        db_session.scalars(
            select(AuditEvent).where(AuditEvent.event_type == "kit.firmware_bridge_authenticated")
        )
    )
    assert len(events) == 1
    assert events[0].data_json["device_id"] == device
