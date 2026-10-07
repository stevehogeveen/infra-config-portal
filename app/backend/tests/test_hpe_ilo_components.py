import json
from types import SimpleNamespace

import httpx
import pytest

from app.providers import hpe_ilo_components as ilo

CONFIG = SimpleNamespace(host="192.0.2.10", username="fixture-user", password="fixture-pass")


def mock(monkeypatch, handler):
    seen = []

    def wrapped(request):
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(ilo, "client_for", lambda config: httpx.Client(transport=httpx.MockTransport(wrapped), base_url="https://192.0.2.10"))
    return seen


def service_body(state="Idle"):
    return {"HttpPushUri": "/cgi-bin/uploadFile", "Oem": {"Hpe": {"State": state}}}


def test_upload_matches_ilorest_form_and_closes_the_session(monkeypatch):
    def handler(request):
        if request.url.path == "/redfish/v1/UpdateService/":
            return httpx.Response(200, json=service_body())
        if request.url.path == "/redfish/v1/SessionService/Sessions/":
            return httpx.Response(201, headers={"X-Auth-Token": "tok123", "Location": "/redfish/v1/SessionService/Sessions/admin1/"}, json={})
        if request.url.path == "/cgi-bin/uploadFile":
            return httpx.Response(200, json={})
        return httpx.Response(200, json={})

    seen = mock(monkeypatch, handler)
    ilo.upload_package(CONFIG, filename="U32_3.66_04_01_2026.fwpkg", data=b"PK-fixture", flash_now=True)
    upload = next(r for r in seen if r.url.path == "/cgi-bin/uploadFile")
    body = upload.content.decode("latin-1")
    assert upload.headers["Cookie"] == "sessionKey=tok123"
    assert 'name="sessionKey"' in body and "tok123" in body
    params = json.loads(body.split('name="parameters"')[1].split("\r\n\r\n", 1)[1].split("\r\n--", 1)[0])
    assert params == {"UpdateRepository": True, "UpdateTarget": True, "ETag": "sumU32366040120 26fwpkg".replace(" ", ""),
                      "Section": 0, "UpdateRecoverySet": False, "TPMOverride": False}
    assert 'filename="U32_3.66_04_01_2026.fwpkg"' in body
    assert body.index('name="sessionKey"') < body.index('name="parameters"') < body.index('name="file"')
    assert any(r.method == "DELETE" and r.url.path == "/redfish/v1/SessionService/Sessions/admin1/" for r in seen)
    assert "fixture-pass" not in body


def test_a_busy_ilo_gets_nothing_and_an_error_reply_is_unknown(monkeypatch):
    mock(monkeypatch, lambda r: httpx.Response(200, json=service_body("Writing")))
    with pytest.raises(ilo.ComponentError) as busy:
        ilo.upload_package(CONFIG, filename="SR_8.00.fwpkg", data=b"x", flash_now=True)
    assert busy.value.sent is False and busy.value.refused is False

    def refuse(request):
        if request.url.path == "/redfish/v1/SessionService/Sessions/":
            return httpx.Response(201, headers={"X-Auth-Token": "tok"}, json={})
        if request.url.path == "/cgi-bin/uploadFile":
            return httpx.Response(400, json={})
        return httpx.Response(200, json=service_body())

    mock(monkeypatch, refuse)
    with pytest.raises(ilo.ComponentError) as refused:
        ilo.upload_package(CONFIG, filename="SR_8.00.fwpkg", data=b"x", flash_now=False)
    # The body may already be on the iLO: an error reply is "unknown", never "not applied".
    assert refused.value.sent is True and refused.value.refused is False


def test_queue_task_body_is_an_apply_update_for_uefi(monkeypatch):
    seen = mock(monkeypatch, lambda r: httpx.Response(201, json={}))
    ilo.queue_bios_update(CONFIG, filename="IEGen10_0.2.3.0.fwpkg")
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/redfish/v1/UpdateService/UpdateTaskQueue/"
    assert body["Command"] == "ApplyUpdate" and body["Filename"] == "IEGen10_0.2.3.0.fwpkg"
    assert body["UpdatableBy"] == ["Uefi"] and body["TPMOverride"] is False and body["Name"].startswith("Update-")


def test_only_plain_fwpkg_names_are_accepted():
    for bad in ("../x.fwpkg", "x.bin", "a b.fwpkg", ""):
        with pytest.raises(ilo.ComponentError):
            ilo.upload_package(CONFIG, filename=bad, data=b"x", flash_now=True)
