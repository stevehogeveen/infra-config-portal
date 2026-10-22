import os
import io

import pycdlib
import pytest

from app.services.firmware_packages import browse_packages, inspect_package, FirmwarePackageError


def iso_file(path, baseline=True):
    iso = pycdlib.PyCdlib()
    iso.new(vol_ident="SPP_FIXTURE_GEN11")
    data = b"<baseline>fixture metadata only</baseline>"
    iso.add_fp(io.BytesIO(data), len(data), iso_path="/BP000001.XML;1" if baseline else "/OTHER.XML;1")
    iso.write(str(path))
    iso.close()


@pytest.fixture
def media(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRMWARE_MEDIA_ROOT", str(tmp_path))
    return tmp_path


def test_iso_contents_and_browse(media):
    iso_file(media / "fixture.iso")
    source = browse_packages()
    assert source["files"][0]["name"] == "fixture.iso"
    package = inspect_package("fixture.iso")
    assert package["baseline_found"]
    assert package["manifest_files"] == ["/BP000001.XML;1"]
    assert "unverified" in package["status"]
    assert package["volume_label"] == "SPP_FIXTURE_GEN11"


@pytest.mark.parametrize("path", ["../outside", "/etc", "C:\\media", "a/../../etc"])
def test_traversal_rejected(media, path):
    with pytest.raises(FirmwarePackageError):
        browse_packages(path)


@pytest.mark.skipif(os.name == "nt", reason="Creating symlinks needs extra Windows privileges; covered on Linux.")
def test_symlink_escape_rejected(media, tmp_path):
    outside = tmp_path.parent / "outside-iso-fixture"
    outside.mkdir(exist_ok=True)
    (media / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(FirmwarePackageError):
        browse_packages("escape")


def test_corrupt_iso_rejected(media):
    (media / "bad.iso").write_bytes(b"not an ISO")
    with pytest.raises(FirmwarePackageError, match="could not be read"):
        inspect_package("bad.iso")


def test_selection_per_kit_and_changes_detected(client, media):
    kit = client.post("/api/v1/lab/profiles", json={"name":"Firmware kit", "profile_topology":"custom", "subnet_cidr":"192.0.2.0/24"}).json()
    endpoint = f"/api/v1/rack-plans/{kit['id']}/firmware-package"
    iso_file(media / "fixture.iso")
    response = client.post(endpoint, json={"path":"fixture.iso"})
    assert response.status_code == 200, response.text
    assert client.get(endpoint).json()["selection_current"]
    other = client.post(f"/api/v1/rack-plans/{kit['id']}/save-as",json={"name":"Another kit"}).json()
    assert client.get(f"/api/v1/rack-plans/{other['id']}/firmware-package").json()["selected"] is None
    (media / "fixture.iso").write_bytes(b"changed")
    assert not client.get(endpoint).json()["selection_current"]
    iso_file(media / "other.iso", baseline=False)
    assert client.post(endpoint,json={"path":"other.iso"}).status_code == 422
    assert client.get(endpoint).json()["selected"]["file_name"] == "fixture.iso"


def test_a_selection_saved_under_docker_still_matches_the_same_file(media, monkeypatch):
    from app.services import firmware_packages as packages

    file = media / "spp.iso"
    file.write_bytes(b"iso-fixture")
    stat = file.stat()
    saved = {"path": "spp.iso", "source_root": packages.DOCKER_MEDIA_ROOT, "size_bytes": stat.st_size, "modified_ns": str(stat.st_mtime_ns)}
    assert not packages.package_unchanged(saved)  # no host mapping: an unknown folder
    monkeypatch.setenv("FIRMWARE_MEDIA_HOST_PATH", str(media))
    assert packages.package_unchanged(saved)
    assert not packages.package_unchanged({**saved, "modified_ns": str(stat.st_mtime_ns + 1)})
