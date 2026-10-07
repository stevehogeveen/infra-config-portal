import hashlib
import io

import pycdlib
import pytest

from app.services.firmware_component import inspect_component
from app.services.firmware_packages import FirmwarePackageError, inspect_package


@pytest.fixture
def package(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRMWARE_MEDIA_ROOT", str(tmp_path))
    iso = pycdlib.PyCdlib()
    iso.new(vol_ident="OFFLINE_FIXTURE", interchange_level=3)
    iso.add_directory(iso_path="/PACKAGES")
    iso.add_directory(iso_path="/MANIFEST")
    data = {
        "/PACKAGES/BP000001.XML;1": b'<cpq_bundle><contents><package>ilo.fwpkg</package></contents></cpq_bundle>',
        "/MANIFEST/SYSTEM.XML;1": b"<manifest/>",
        "/MANIFEST/META.XML;1": b'<manifest><meta lang="en"><product><product_version><id version="ilo"/><type id="universal-fw-ilo"/><version value="3.0"/><files><file><name>ilo.fwpkg</name></file></files></product_version></product></meta></manifest>',
        "/PACKAGES/ILO.FWPKG;1": b"fixture bytes, not installable firmware",
    }
    for name, content in data.items():
        iso.add_fp(io.BytesIO(content), len(content), iso_path=name)
    iso.write(str(tmp_path / "fixture.iso"))
    iso.close()
    return inspect_package("fixture.iso")


def test_component_hashes_actual_bytes_without_claiming_support(package):
    first = inspect_component(package, "ilo")
    second = inspect_component(package, "ilo")
    assert first == second
    assert first["files"][0]["sha256"] == hashlib.sha256(
        b"fixture bytes, not installable firmware").hexdigest()
    assert len(first["component_hash"]) == 64
    for flag in ("signature_verified", "applicability_verified", "dependencies_verified", "can_apply"):
        assert first[flag] is False


def test_unknown_component_and_changed_media_rejected(package, tmp_path):
    with pytest.raises(FirmwarePackageError, match="unambiguous"):
        inspect_component(package, "unknown")
    (tmp_path / "fixture.iso").write_bytes(b"changed")
    with pytest.raises(FirmwarePackageError, match="changed"):
        inspect_component(package, "ilo")


def test_size_limit(package, monkeypatch):
    monkeypatch.setattr("app.services.firmware_component.MAX_COMPONENT_BYTES", 1)
    with pytest.raises(FirmwarePackageError, match="size limit"):
        inspect_component(package, "ilo")


def test_319_constraints_keep_first_bridge_without_mandatory_278(package, monkeypatch):
    monkeypatch.setattr("app.services.firmware_component.inspect_ilo_payload",
                        lambda *args: {"declared_version": "3.19"})
    result = inspect_component(package, "ilo")
    constraints = " ".join(result["upgrade_constraints"])
    assert "1.48 bridge before 3.19" in constraints
    assert "does not require an intermediate 2.78 update" in constraints
    assert "Each update needs its own approval" in constraints
    assert result["can_apply"] is False
    assert result["dependencies_verified"] is False


def test_scoped_inspection_endpoint(client, package, db_session):
    from app.services.audit import record_audit_event

    kit = client.post("/api/v1/lab/profiles", json={
        "name": "Inspection fixture", "profile_topology": "custom",
        "subnet_cidr": "192.0.2.0/24",
    }).json()
    base = "/api/v1/rack-plans/" + kit["id"]
    plan = client.put(base, json={"equipment": [{
        "id": "server", "name": "Fixture", "kind": "server", "model": "HPE DL360",
        "position": 1, "height": 1,
    }]}).json()
    device = plan["equipment"][0]["device_id"]
    url = base + "/firmware-execution/inspect-component?device_id=" + device
    assert client.post(url, json={"component_id": "ilo"}).status_code == 409
    record_audit_event(db_session, actor="fixture", event_type="kit.firmware_package_selected",
                       message="Fixture selection", data={"profile_id": kit["id"], "package": package})
    db_session.commit()
    result = client.post(url, json={"component_id": "ilo"})
    assert result.status_code == 200, result.text
    assert result.json()["device_id"] == device
    assert result.json()["can_apply"] is False
    assert client.post(url, json={"component_id": "ilo", "path": "/arbitrary"}).status_code == 422
    assert client.post(base + "/firmware-execution/inspect-component?device_id=wrong",
                       json={"component_id": "ilo"}).status_code == 404
