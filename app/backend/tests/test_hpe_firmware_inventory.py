import httpx
import pytest

from app.providers.hpe_firmware_inventory import (
    FirmwareInventoryError, discover_update_service,
)


def resources():
    return {
        "/redfish/v1/": {"UpdateService": {"@odata.id": "/redfish/v1/UpdateService/"}},
        "/redfish/v1/UpdateService/": {
            "ServiceEnabled": True, "HttpPushUri": "/cgi-bin/uploadFile",
            "FirmwareInventory": {"@odata.id": "/redfish/v1/UpdateService/FirmwareInventory/"},
            "Oem": {"Hpe": {"State": "Idle"}},
        },
        "/redfish/v1/UpdateService/FirmwareInventory/": {
            "Members@odata.count": 1, "Members": [{"@odata.id": "/redfish/v1/UpdateService/FirmwareInventory/1/"}],
        },
        "/redfish/v1/UpdateService/FirmwareInventory/1/": {
            "Name": "iLO 5", "Version": "1.37", "Updateable": True,
            "Oem": {"Hpe": {"Targets": ["fixture-target"]}},
        },
    }


def discover(data):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.host == "192.0.2.1"
        return httpx.Response(200, json=data[request.url.path])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = discover_update_service(client, "https://192.0.2.1")
    return result, calls


def test_discovery_follows_advertised_resources_with_get_only():
    result, calls = discover(resources())
    assert len(calls) == 4
    assert result["inventory"][0]["targets"] == ["fixture-target"]
    assert result["state"] == "Idle"
    assert result["capabilities"] == {}
    assert result["max_image_size_bytes"] is None


@pytest.mark.parametrize("path", [
    "https://192.0.2.2/steal", "//192.0.2.2/steal",
    "/redfish/v1/../escape", "/redfish/v1/%2e%2e/escape", "/redfish/v1/UpdateService?force=true",
])
def test_external_or_unsafe_links_never_followed(path):
    data = resources()
    data["/redfish/v1/"]["UpdateService"]["@odata.id"] = path
    with pytest.raises(FirmwareInventoryError):
        discover(data)


@pytest.mark.parametrize("case", ["count", "pagination", "disabled", "duplicate"])
def test_incomplete_inventory_fails_closed(case):
    data = resources()
    collection = data["/redfish/v1/UpdateService/FirmwareInventory/"]
    if case == "count":
        collection["Members@odata.count"] = 3
    elif case == "pagination":
        collection["Members@odata.nextLink"] = "/redfish/v1/next"
    elif case == "disabled":
        data["/redfish/v1/UpdateService/"]["ServiceEnabled"] = False
    else:
        collection["Members"] *= 2
        collection["Members@odata.count"] = 2
    with pytest.raises(FirmwareInventoryError):
        discover(data)


def test_redirect_not_followed():
    calls = []
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: calls.append(request) or httpx.Response(
            302, headers={"Location": "https://192.0.2.2/steal"}),
    ), follow_redirects=True) as client:
        with pytest.raises(FirmwareInventoryError):
            discover_update_service(client, "https://192.0.2.1")
    assert len(calls) == 1


def test_capabilities_require_explicit_scoped_read(client, monkeypatch):
    from app.api import firmware_execution

    kit = client.post("/api/v1/lab/profiles", json={
        "name": "Capability fixture", "profile_topology": "custom",
        "subnet_cidr": "192.0.2.0/24",
    }).json()
    base = "/api/v1/rack-plans/" + kit["id"]
    plan = client.put(base, json={"equipment": [{
        "id": "server", "name": "Fixture", "kind": "server", "model": "HPE DL360",
        "position": 1, "height": 1,
    }]}).json()
    device = plan["equipment"][0]["device_id"]
    calls = []

    def collect(session, device_id):
        calls.append(device_id)
        return {"device_id": device_id, "can_apply": False, "source": "offline_fixture"}

    monkeypatch.setattr(firmware_execution, "collect_firmware_capabilities", collect)
    root = base + "/firmware-execution"
    url = root + "/capabilities?device_id=" + device
    assert client.post(url, json={"confirm_read_only": False}).status_code == 409
    assert client.post(url, json={"confirm_read_only": "true"}).status_code == 422
    assert client.post(url, json={"confirm_read_only": True, "host": "192.0.2.2"}).status_code == 422
    assert client.post(root + "/capabilities?device_id=wrong",
                       json={"confirm_read_only": True}).status_code == 404
    assert client.get(root + "/status?device_id=" + device).status_code == 200
    assert client.post(root + "/preview?device_id=" + device, json={}).status_code == 200
    assert calls == []
    assert client.post(url, json={"confirm_read_only": True}).status_code == 200
    assert calls == [device]
