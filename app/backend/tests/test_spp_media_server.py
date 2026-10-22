import pytest
import os
from fastapi.testclient import TestClient

from app.providers.spp_media_server import media_app


def test_iso_supports_head_and_random_byte_ranges(tmp_path):
    data = bytes(range(256)) * 10
    (tmp_path / "fixture.iso").write_bytes(data)
    client = TestClient(media_app(tmp_path))
    head = client.head("/fixture.iso")
    assert head.status_code == 200 and not head.content
    assert head.headers["accept-ranges"] == "bytes"
    assert int(head.headers["content-length"]) == len(data)
    for start, end in [(0, 0), (512, 1023), (2000, 2559)]:
        reply = client.get("/fixture.iso", headers={"Range": f"bytes={start}-{end}"})
        assert reply.status_code == 206
        assert reply.content == data[start : end + 1]
        assert reply.headers["content-range"] == f"bytes {start}-{end}/{len(data)}"
    assert client.get("/fixture.iso", headers={"Range": "bytes=9999-"}).status_code == 416


@pytest.mark.skipif(os.name == "nt", reason="Creating symlinks needs extra Windows privileges; covered on Linux.")
def test_media_service_exposes_no_directory_or_other_files(tmp_path):
    (tmp_path / "credentials.json").write_text("fixture secret")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested/other.iso").write_bytes(b"nested")
    (tmp_path / "link.iso").symlink_to(tmp_path / "credentials.json")
    client = TestClient(media_app(tmp_path))
    for path in [
        "/",
        "/docs",
        "/credentials.json",
        "/nested/other.iso",
        "/link.iso",
        "/..%5Csecret.iso",
    ]:
        assert client.get(path).status_code == 404
    assert client.post("/fixture.iso").status_code == 405
