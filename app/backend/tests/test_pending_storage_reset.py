from types import SimpleNamespace

import httpx
import pytest

from app.providers import hpe_storage_rebuild as provider


def test_snapshot_accepts_action_only_pending_reset(monkeypatch):
    config = SimpleNamespace(configured=True, fallback_hosts=[], host='192.0.2.10')
    pending = {'Actions': [{'Action': 'FactoryReset'}], 'DataGuard': 'Disabled'}
    current = {'@odata.type': '#SmartStorageConfig.v2_0_0.SmartStorageConfig',
               'Location': 'Slot 0', 'LogicalDrives': [],
               '@Redfish.Settings': {'SettingsObject': {
                   '@odata.id': '/redfish/v1/systems/1/SmartStorageConfig/Settings/'}}}
    probe = {'systems': [{'@odata.id': '/redfish/v1/systems/1/', 'PowerState': 'Off'}],
             'storage': {'controllers': [{'Model': 'Fixture controller', 'Location': 'Slot 0'}]}}
    monkeypatch.setattr(provider, 'current_lab_action_policy',
                        lambda: SimpleNamespace(readonly_blockers=lambda: []))
    monkeypatch.setattr(provider, 'ilo_config_for_device', lambda *a: config)
    monkeypatch.setattr(provider, 'IloRedfishAdapter', lambda **k: SimpleNamespace(probe=lambda: probe))
    monkeypatch.setattr(provider, 'resolve_ilo_write_target_context',
                        lambda *a, **k: (SimpleNamespace(identity_fingerprint_sha256='fixture'), []))
    requests = []

    def respond(request):
        requests.append(request.method)
        return httpx.Response(200, json=pending if 'settings' in request.url.path.lower() else current,
                              headers={'etag': '"fixture"'})

    monkeypatch.setattr(provider, 'client_for', lambda c: httpx.Client(transport=httpx.MockTransport(respond)))
    snapshot = provider.read_snapshot(None, 'fixture')
    assert snapshot['power'] == 'Off'
    assert snapshot['pending_differs']
    assert snapshot['pending'] == pending
    assert requests == ['GET', 'GET']
    # A reset request must never substitute for missing applied-state evidence.
    del current['LogicalDrives']
    with pytest.raises(provider.StorageRebuildError, match='complete logical-drive'):
        provider.read_snapshot(None, 'fixture')


@pytest.mark.parametrize('pending', [
    {}, {'Actions': [{'Action': 'FactoryReset'}]},
    {'Actions': [{'Action': 'FactoryReset'}], 'DataGuard': 'Strict'},
    {'Actions': [{'Action': 'Unknown'}], 'DataGuard': 'Disabled'},
    {'Actions': [{'Action': 'FactoryReset'}], 'DataGuard': 'Disabled', 'LogicalDrives': None},
])
def test_incomplete_other_pending_configurations_remain_blocked(pending):
    with pytest.raises(provider.StorageRebuildError):
        provider.pending_signature(pending)
