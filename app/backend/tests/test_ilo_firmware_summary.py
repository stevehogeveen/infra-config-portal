from app.providers.ilo_redfish import _resource_summary


def test_redfish_software_inventory_keeps_version():
    summary = _resource_summary({"Name": "Fixture ROM", "Version": "test-version"})
    assert summary["Version"] == "test-version"


def test_hpe_network_link_and_nested_firmware():
    from app.providers.ilo_redfish import _network_collection_paths, _network_summary
    from app.services.hardware_values import firmware_version
    paths = _network_collection_paths({'Oem':{'Hpe':{'Links':{'NetworkAdapters':{'@odata.id':'/redfish/v1/Systems/1/BaseNetworkAdapters/'}}}}},'/redfish/v1/Systems/1/')
    assert '/redfish/v1/Systems/1/BaseNetworkAdapters/' in paths
    summary = _network_summary({'Name':'Fixture NIC','Firmware':{'Current':{'VersionString':'20.12.41'}}})
    assert firmware_version(summary)=='20.12.41'


def test_logical_drive_readback_preserves_exact_member_paths(monkeypatch):
    from app.providers import ilo_redfish as provider
    payloads = {
        '/volumes': {'Members': [{'@odata.id': '/volumes/1'}]},
        '/volumes/1': {'Name': 'Boot mirror', 'Links': {'DataDrives': {'@odata.id': '/volumes/1/drives'}}},
        '/volumes/1/drives': {'Members': [{'@odata.id': '/drives/1'}, {'@odata.id': '/drives/2'}]},
    }
    monkeypatch.setattr(provider, '_get_json', lambda client, base, path, requests: payloads[path])
    rows = provider._storage_collection_summaries(None, 'https://192.0.2.10', '/volumes', [], provider._logical_drive_summary)
    assert rows[0]['physical_drive_paths'] == ['/drives/1', '/drives/2']
    payloads['/volumes/1']['Links'] = {'Drives': [{'@odata.id': '/drives/3'}]}
    rows = provider._storage_collection_summaries(None, 'https://192.0.2.10', '/volumes', [], provider._logical_drive_summary)
    assert rows[0]['physical_drive_paths'] == ['/drives/3']


def test_saved_rack_versions_require_current_exact_target(monkeypatch):
    from types import SimpleNamespace
    from app.services import ilo_access_settings as access
    probe = {'status': 'ok', 'target_fingerprint': access.ilo_target_fingerprint('192.0.2.10'),
             'managers': [{'FirmwareVersion': 'iLO 5 v1.37'}], 'systems': [{'BiosVersion': 'U32 v1.46'}]}
    def cached(provider, *, scope):
        assert scope == 'server-a'
        return probe, '2026-09-14T12:00:00Z'
    monkeypatch.setattr(access, 'get_probe_result', cached)
    monkeypatch.setattr(access, 'status_source_metadata', lambda **kw: {'freshness': 'current', 'is_current': True})
    config = SimpleNamespace(device_id='server-a', target_candidates=[])
    values = access._last_probe_summary('192.0.2.10', config)
    assert values['observed_ilo_firmware'] == 'iLO 5 v1.37'
    assert values['observed_bios_version'] == 'U32 v1.46'
    assert access._last_probe_summary('192.0.2.11', config)['observed_ilo_firmware'] is None
    probe['source_type'] = 'mock'
    assert access._last_probe_summary('192.0.2.10', config)['observed_bios_version'] is None
