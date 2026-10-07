import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zipfile import ZipFile

import httpx
import pytest

from app.providers import hpe_firmware_adapter as provider
from app.providers.ilo_redfish import ilo_target_fingerprint
from app.services.audit import record_audit_event
from app.services.firmware_catalog import ilo_component
from app.services.firmware_worker import (
    FirmwareReview,
    FirmwareReviewError,
    canonical_intent,
)


@pytest.fixture(params=[("1.37", "1.48"), ("1.48", "3.19")])
def preparation(db_session, monkeypatch, request):
    installed, target = request.param
    binary = b"offline firmware"
    sha = hashlib.sha256(binary).hexdigest()
    package = {"path": "fixture.iso"}
    event = record_audit_event(
        db_session,
        actor="fixture",
        event_type="kit.firmware_package_selected",
        message="fixture",
        data={"profile_id": "kit", "package": package},
    )
    db_session.commit()
    config = SimpleNamespace(
        host="192.0.2.1",
        username="fixture",
        password="fixture-only",
        configured=True,
        fallback_hosts=(),
    )
    capabilities = {
        "device_id": "device",
        "checked_at": datetime.now(UTC).isoformat(),
        "source": "live-ilo-firmware-capabilities",
        "authenticated": True,
        "exact_target_only": True,
        "identity_verified": True,
        "state": "Idle",
        "http_push_uri": "/cgi-bin/uploadFile",
        "target_identity_sha256": "a" * 64,
        "target_fingerprint": ilo_target_fingerprint(config.host),
        "manager_firmware_version": installed,
        "inventory": [{"targets": ["fixture-target"], "updateable": True, "version": installed}],
        "system_health": "OK",
        "health_issues": [],
        "ilo_update_health": {"scope": "ilo-only-v1", "blockers": [], "warnings": []},
        "errors": [],
    }
    bridge = {"path": "/bridge.fwpkg", "sha256": "c" * 64, "payload": {"binary": {"sha256": sha}}}
    auth = {
        "binary_authenticated": True,
        "component_sha256": "c" * 64,
        "binary": {"sha256": sha, "size_bytes": len(binary)},
        "authenticated_declaration": {
            "version": target,
            "direct_flash": True,
            "host_power_change_required": False,
            "targets": ["fixture-target"],
            "device_class": "fixture-class",
        },
    }
    intent = provider.bridge_intent("kit", "device", event.id, bridge, auth, capabilities)
    review = FirmwareReview(
        "kit",
        "device",
        "r" * 64,
        datetime.now(UTC) + timedelta(minutes=5),
        "INSTALL",
        canonical_intent(intent),
    )
    data = io.BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr(ilo_component(target).filename, binary)

    class ISO:
        def open(self, path):
            pass

        def close(self):
            pass

        def open_file_from_iso(self, **kwargs):
            return io.BytesIO(data.getvalue())

    monkeypatch.setenv("LAB_ALLOWED_WRITE_ACTIONS", "ilo.firmware-update")
    monkeypatch.setattr(
        provider,
        "current_lab_action_policy",
        lambda: SimpleNamespace(action_blockers=lambda *args: []),
    )
    monkeypatch.setattr(provider, "inspect_spp_bridge", lambda p, *args: bridge)
    monkeypatch.setattr(provider, "verify_bridge_from_spp", lambda p, s: auth)
    monkeypatch.setattr(provider, "collect_firmware_capabilities", lambda *args: capabilities)
    monkeypatch.setattr(provider, "ilo_config_for_device", lambda *args: config)
    monkeypatch.setattr(provider, "media_path", lambda p: p)
    monkeypatch.setattr(provider, "package_unchanged", lambda p: True)
    monkeypatch.setattr(provider.pycdlib, "PyCdlib", ISO)
    return provider.HpeFirmwareAdapter(db_session), review, config, capabilities, auth, data


@pytest.mark.parametrize("change", ["scope", "policy"])
def test_authorization_revoked_after_preparation_never_contacts_target(
    preparation, monkeypatch, change
):
    adapter, review, *_ = preparation
    prepared = adapter.prepare(review)
    if change == "scope":
        monkeypatch.setenv("LAB_ALLOWED_WRITE_ACTIONS", "")
    else:
        monkeypatch.setattr(
            provider,
            "current_lab_action_policy",
            lambda: SimpleNamespace(action_blockers=lambda *args: ["revoked"]),
        )
    monkeypatch.setattr(provider, "client_for", lambda c: pytest.fail("must not contact hardware"))
    from app.services.firmware_transport import FirmwareDispatchError

    with pytest.raises(FirmwareDispatchError, match="upload was not started") as exc:
        adapter.send(prepared)
    assert exc.value.facts["stage"] == "authorization"
    assert exc.value.upload_started is False


def test_preparation_revalidates_exact_bytes(preparation):
    adapter, review, config, *_ = preparation
    prepared = adapter.prepare(review)
    assert prepared.intent_json == review.intent_json
    assert prepared.handle.binary == b"offline firmware"
    assert "fixture-only" not in repr(prepared)


@pytest.mark.parametrize(
    "changed", ["identity", "config", "version", "class", "bytes", "power", "scope", "generation"]
)
def test_changed_preflight_blocks_before_send(preparation, monkeypatch, changed):
    adapter, review, config, caps, auth, data = preparation
    if changed == "identity":
        caps["target_identity_sha256"] = "f" * 64
    elif changed == "config":
        config.host = "192.0.2.2"
    elif changed == "version":
        caps["manager_firmware_version"] = "1.40"
    elif changed == "class":
        caps["inventory"][0]["device_class"] = "different"
    elif changed == "power":
        auth["authenticated_declaration"]["host_power_change_required"] = True
    elif changed == "scope":
        monkeypatch.setenv("LAB_ALLOWED_WRITE_ACTIONS", "ilo.firmware-update,ilo.power-action")
    elif changed == "generation":
        caps["manager_model"] = "iLO 6"
    else:
        data.seek(0)
        data.truncate()
        with ZipFile(data, "w") as archive:
            archive.writestr(
                ilo_component(json.loads(review.intent_json)["target_version"]).filename,
                b"changed firmware",
            )
    with pytest.raises(FirmwareReviewError):
        adapter.prepare(review)


@pytest.mark.parametrize(
    "case",
    ["success", "lost", "login-failed", "external-session", "login-timeout", "missing-token"],
)
def test_session_transport_one_upload_no_redirect_or_retry(preparation, monkeypatch, case):
    adapter, review, config, *_ = preparation
    prepared = adapter.prepare(review)
    requests = []

    def handler(request):
        requests.append((request.method, str(request.url)))
        path = request.url.path
        if path == "/redfish/v1/":
            return httpx.Response(
                200, json={"SessionService": {"@odata.id": "/redfish/v1/SessionService"}}
            )
        if path == "/redfish/v1/SessionService":
            return httpx.Response(
                200, json={"Sessions": {"@odata.id": "/redfish/v1/SessionService/Sessions"}}
            )
        if path == "/redfish/v1/SessionService/Sessions":
            if case == "login-timeout":
                raise httpx.ReadTimeout("private fixture credential")
            return httpx.Response(
                403 if case == "login-failed" else 201,
                headers={
                    "X-Auth-Token": "" if case == "missing-token" else "fixture-token",
                    "Location": "https://example.invalid/session"
                    if case == "external-session"
                    else "/redfish/v1/SessionService/Sessions/42",
                },
            )
        if path == "/cgi-bin/uploadFile":
            assert requests[-2][0] == "POST" and requests[-2][1].endswith("/Sessions")
            assert request.headers["Cookie"] == "sessionKey=fixture-token"
            filename = ilo_component(json.loads(review.intent_json)["target_version"]).filename
            assert f'filename="{filename}"'.encode() in request.content
            if case == "lost":
                raise httpx.ReadTimeout("fixture lost response")
            return httpx.Response(200, json={})
        assert request.method == "DELETE" and path.endswith("/42")
        return httpx.Response(204)

    monkeypatch.setattr(
        provider, "client_for", lambda c: httpx.Client(transport=httpx.MockTransport(handler))
    )
    if case in {"lost", "login-failed", "login-timeout", "missing-token"}:
        from app.services.firmware_transport import FirmwareDispatchError

        with pytest.raises(FirmwareDispatchError) as exc:
            adapter.send(prepared)
        assert exc.value.upload_started is (case == "lost")
        assert "private" not in str(exc.value.facts)
    else:
        adapter.send(prepared)
    assert sum(path.endswith("/cgi-bin/uploadFile") for _, path in requests) == (
        0 if case in {"login-failed", "login-timeout", "missing-token"} else 1
    )
    assert all(path.startswith("https://192.0.2.1/") for _, path in requests)
    assert not any(method == "PATCH" for method, _ in requests)


def _intent(preparation, **changes):
    adapter, review, config, capabilities, auth, data = preparation
    caps = {**capabilities, **changes.pop("caps", {})}
    caps["inventory"] = [{**capabilities["inventory"][0], **changes}]
    bridge = {
        "path": "/bridge.fwpkg",
        "sha256": "c" * 64,
        "payload": {"binary": {"sha256": auth["binary"]["sha256"]}},
    }
    return provider.bridge_intent("kit", "device", 1, bridge, auth, caps)


def test_ilo5_1x_inventory_without_updateable_and_dated_version_is_accepted(preparation):
    # Observed on iLO 5 1.37: Updateable is null and the inventory version carries a date.
    installed = preparation[3]["manager_firmware_version"]
    intent = _intent(
        preparation,
        updateable=None,
        version=f"{installed} Oct 25 2018",
        caps={"manager_firmware_version": f"iLO 5 v{installed}"},
    )
    assert intent["installed_version"] == f"iLO 5 v{installed}"


@pytest.mark.parametrize("value", [0, 1, "false", "true", [], {}])
def test_malformed_updateable_is_not_treated_as_missing(preparation, value):
    with pytest.raises(FirmwareReviewError, match="invalid Updateable"):
        _intent(preparation, updateable=value)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"updateable": False}, "The iLO reports that its firmware can't be updated right now."),
        ({"targets": ["other"]}, "HPE's signed file does not name this iLO."),
        (
            {"device_class": "other-class"},
            "HPE's signed file is for a different kind of device than this iLO.",
        ),
        ({"version": "9.99"}, "disagree. Check again."),
    ],
)
def test_target_mismatches_are_named(preparation, change, message):
    with pytest.raises(FirmwareReviewError, match=message.replace(".", r"\.").replace("(", r"\(")):
        _intent(preparation, **change)
