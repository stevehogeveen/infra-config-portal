import asyncio

import pytest
from fastapi import HTTPException

from app.services.media_upload import receive_iso


@pytest.fixture
def media(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRMWARE_MEDIA_ROOT", str(tmp_path))
    return tmp_path


def test_upload_publishes_complete_bytes_and_refuses_overwrite(client, media):
    endpoint = "/api/v1/rack-plans/runtime/media-upload?name=fixture.iso&size=6"
    response = client.post(endpoint, content=b"abcdef", headers={"Content-Type":"application/octet-stream"})
    assert response.status_code == 201, response.text
    assert (media / "fixture.iso").read_bytes() == b"abcdef"
    assert not list(media.glob("*.partial"))
    assert client.post(endpoint, content=b"xxxxxx").status_code == 409
    assert (media / "fixture.iso").read_bytes() == b"abcdef"


@pytest.mark.parametrize("name", ["../bad.iso", "bad.exe", "C:\\bad.iso", ".hidden.iso"])
def test_bad_names_rejected(client, media, name):
    assert client.post("/api/v1/rack-plans/runtime/media-upload", params={"name":name,"size":3}, content=b"abc").status_code == 422
    assert not list(media.iterdir())


@pytest.mark.parametrize("size,status", [(2,413),(8,422)])
def test_incomplete_or_oversized_stream_cleaned(client, media, size, status):
    response = client.post("/api/v1/rack-plans/runtime/media-upload",params={"name":"fixture.iso","size":size},content=b"abcdef")
    assert response.status_code == status
    assert not list(media.iterdir())


def test_interrupted_stream_cleaned(media):
    async def broken():
        yield b"abc"
        raise RuntimeError("disconnected fixture")
    with pytest.raises(RuntimeError, match="disconnected fixture"):
        asyncio.run(receive_iso(broken(), "fixture.iso", 6))
    assert not list(media.iterdir())


def test_insufficient_space(client, media, monkeypatch):
    from app.services import media_upload
    from collections import namedtuple
    usage = namedtuple("usage", "total used free")(100,99,1)
    monkeypatch.setattr(media_upload.shutil, "disk_usage", lambda path:usage)
    assert client.post("/api/v1/rack-plans/runtime/media-upload?name=fixture.iso&size=6",content=b"abcdef").status_code == 507
    assert not list(media.iterdir())
