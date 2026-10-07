import hashlib

import httpx
import pytest

from app.providers.hpe_ilo_firmware import FirmwareUploadError, upload_ilo_binary


def upload(client, **overrides):
    values = dict(
        host="192.0.2.1",
        http_push_uri="/cgi-bin/uploadFile",
        session_token="fixture-session",
        filename="ilo5_fixture.bin",
        binary=b"offline firmware fixture",
        installed_version="2.78",
        target_version="3.19",
        expected_sha256=hashlib.sha256(b"offline firmware fixture").hexdigest(),
    )
    values.update(overrides)
    upload_ilo_binary(client, **values)


@pytest.mark.parametrize("installed", ["1.48", "2.77", "2.78"])
def test_exact_multipart_single_request_and_no_reboot(installed):
    calls = []

    def handler(request):
        calls.append(request)
        assert str(request.url) == "https://192.0.2.1/cgi-bin/uploadFile"
        assert request.method == "POST"
        assert request.headers["Cookie"] == "sessionKey=fixture-session"
        assert request.headers["Accept"] == "application/json"
        assert request.headers["OData-Version"] == "4.0"
        assert request.headers["Expect"] == ""
        assert "authorization" not in request.headers
        assert request.extensions["timeout"]["write"] == 300
        content = request.read()
        assert b'name="sessionKey"' in content
        assert b'name="file"' in content
        assert b'filename="ilo5_fixture.bin"' in content
        assert b"offline firmware fixture" in content
        assert b"TPMOverride" not in content
        return httpx.Response(200, json={})

    with httpx.Client(
        auth=("fixture-user", "fixture-password"), timeout=5, transport=httpx.MockTransport(handler)
    ) as client:
        assert upload(client, installed_version=installed) is None
    assert len(calls) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"host": "server.example.invalid"},
        {"http_push_uri": "https://192.0.2.2/cgi-bin/uploadFile"},
        {"http_push_uri": "//192.0.2.2/cgi-bin/uploadFile"},
        {"http_push_uri": "/cgi-bin/uploadFile?force=true"},
        {"http_push_uri": "/redfish/v1/Systems/1/Actions/ComputerSystem.Reset"},
        {"filename": "../ilo.bin"},
        {"filename": "ilo.fwpkg"},
        {"expected_sha256": "0" * 64},
        {"binary": b""},
        {"session_token": ""},
    ],
)
def test_invalid_request_never_touches_transport(changes):
    calls = []
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(200),
        )
    ) as client:
        with pytest.raises(FirmwareUploadError):
            upload(client, **changes)
    assert calls == []


@pytest.mark.parametrize("status", [301, 302, 307, 401, 500])
def test_errors_and_redirects_never_retried(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={"Location": "https://192.0.2.2/stolen"})

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        with pytest.raises(FirmwareUploadError):
            upload(client)
    assert len(calls) == 1


def test_timeout_redacted_and_never_retried():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("fixture-session secret", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(FirmwareUploadError) as exc:
            upload(client)
    assert "fixture-session" not in str(exc.value)
    assert len(calls) == 1


def test_http_success_with_error_body_is_not_acceptance():
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"error": {"code": "rejected"}}),
        )
    ) as client:
        with pytest.raises(FirmwareUploadError) as exc:
            upload(client)
        assert exc.value.facts == {
            "http_status": 200,
            "content_type": "application/json",
            "json_error_present": True,
        }


def test_failure_diagnostics_do_not_include_vendor_body_or_content_type_secrets():
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                401,
                headers={"content-type": "application/secret-value"},
                text="fixture-session fixture-password",
            )
        )
    ) as client:
        with pytest.raises(FirmwareUploadError) as exc:
            upload(client)
    assert exc.value.facts == {
        "http_status": 401,
        "content_type": "other",
        "json_error_present": None,
    }
    assert "secret" not in str(exc.value.facts)


def test_missing_first_bridge_blocked_before_http():
    binary = b"x" * (32 * 1024**2 + 1)
    calls = []
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(200),
        )
    ) as client:
        with pytest.raises(FirmwareUploadError, match="1.48"):
            upload(
                client,
                binary=binary,
                expected_sha256=hashlib.sha256(binary).hexdigest(),
                installed_version="1.37",
            )
    assert calls == []
