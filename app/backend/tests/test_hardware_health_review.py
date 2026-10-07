from datetime import UTC, datetime, timedelta

import pytest

from app.api import firmware_review
from app.services import hardware_health
from app.providers.ilo_redfish import _drive_summary, _logical_drive_summary


def test_power_collection_preserves_feed_evidence_without_raw_oem_or_serial(monkeypatch):
    from app.providers import ilo_redfish as provider
    calls = []
    def get(client, base, path, requests):
        calls.append(path)
        return {"PowerSupplies": [
            {"Model": "Fixture PSU", "SerialNumber": "private-serial", "LineInputVoltage": 0,
             "PowerSupplyType": "AC", "Status": {"Health": "OK", "State": "Enabled"},
             "Oem": {"Hpe": {"BayNumber": 2, "PrivateField": "not-retained",
                             "PowerSupplyStatus": {"State": "Ok"}}}}],
            "Redundancy": [{"Mode": "Failover", "MinNumNeeded": 2,
                            "Status": {"Health": "Warning", "State": "Disabled"}}]}
    monkeypatch.setattr(provider, "_get_json", get)
    power = provider._linked_summaries(None, "https://192.0.2.10",
        [{"_links": {"Power": {"@odata.id": "/chassis/1/power"}}}], "Power", [])
    assert calls == ["/chassis/1/power"]
    row = power[0]["PowerSupplies"][0]
    assert row["Location"] == "2" and row["LineInputVoltage"] == 0
    assert row["PowerSupplyStatus"] == {"State": "Ok"}
    assert "SerialNumber" not in row and "Oem" not in row
    assert "private-serial" not in str(power) and "not-retained" not in str(power)
    assert power[0]["Redundancy"][0]["Status"]["Health"] == "Warning"


def test_missing_power_feed_is_explained_without_claiming_failed_supply():
    probe = {"power": [{"PowerSupplies": [
        {"Location": str(i), "Model": "Fixture PSU", "PowerSupplyType": "AC",
         "LineInputVoltage": voltage, "Status": {"Health": "OK", "State": "Enabled"}}
        for i, voltage in [(1, 117), (2, 0)]],
        "Redundancy": [{"Mode": "Failover", "MinNumNeeded": 2,
                        "Status": {"Health": "Warning", "State": "Disabled"}}]}],
        "systems": [{"Model": "Fixture server", "Status": {"Health": "Warning"}}]}
    supply, redundancy, server = hardware_health.health_issues(probe)
    assert supply["title"] == "Power supply 2: no input power"
    assert supply["health"] == "Warning"
    assert supply["facts"]["Reported supply health"] == "OK"
    assert supply["facts"]["Input voltage"] == "0 V"
    assert "does not by itself prove" in supply["details"][0]
    assert redundancy["title"] == "Power redundancy unavailable"
    assert any("Power supply 2" in d and "not confirmed" in d for d in server["details"])


@pytest.mark.parametrize("voltages", [[117], [117, 117], [0, 0], [None, None]])
def test_supply_count_or_unavailable_input_does_not_invent_power_fault(voltages):
    assert hardware_health.health_issues({"power": [{"PowerSupplies": [
        {"PowerSupplyType": "AC", "LineInputVoltage": v,
         "Status": {"Health": "OK", "State": "Enabled"}} for v in voltages]}]}) == []


def test_empty_power_bay_and_failed_installed_supply_remain_distinct():
    empty, failed = hardware_health.health_issues({"power": [{"PowerSupplies": [
        {"Location": "1", "Status": {"State": "Absent"}},
        {"Location": "2", "Status": {"Health": "Critical", "State": "Enabled"}}]}]})
    assert empty["title"] == "Power supply 1: not installed" and empty["health"] == "Warning"
    assert failed["health"] == "Critical"


def test_controller_diagnostics_do_not_invent_battery_failure():
    from app.providers.ilo_redfish import _storage_controller_summary
    controller = _storage_controller_summary({'Model':'Fixture controller','Status':{'Health':'Warning'},
        'CacheModuleStatus':{'Health':'Warning'},'ControllerBoard':{'Status':{'Health':'OK'},'SerialNumber':'not-retained'},
        'BackupPowerSourceStatus':'Present'})
    assert controller['ControllerBoard'] == {'Status':{'Health':'OK'}}
    issue = hardware_health.health_issues({'storage':{'controllers':[controller]}})[0]
    assert issue['facts']['Cache module health'] == 'Warning'
    assert issue['facts']['Controller board health'] == 'OK'
    assert issue['facts']['Backup power charge'] == 'Unknown (presence only)'
    assert any('not the underlying cause' in detail for detail in issue['details'])
    assert 'Do not wipe RAID' in issue['next_step']


@pytest.mark.parametrize("health", ["Warning", "Critical"])
def test_completed_erase_explained_without_clearing_health(health):
    drive = {"Location": "1I:1:1", "Model": "Fixture drive", "CapacityBytes": 300000000000,
             "Status": {"Health": health, "State": "Enabled"},
             "DiskDriveStatusReasons": ["EraseCompleted"]}
    issue = hardware_health.health_issues({"storage": {"physical_drives": [drive]}})[0]
    assert issue["health"] == health
    assert issue["facts"]["Original iLO health"] == health
    assert "erase completed" in issue["details"][0]
    assert "does not establish" in issue["details"][0]
    assert "Do not repeat the wipe" in issue["next_step"]


def test_completed_erase_does_not_hide_another_drive_fault():
    drive = {"Location": "1I:1:1", "Model": "Fixture drive", "CapacityBytes": 300000000000,
             "Status": {"Health": "Critical"},
             "DiskDriveStatusReasons": ["EraseCompleted", "Failed"]}
    issue = hardware_health.health_issues({"storage": {"physical_drives": [drive]}})[0]
    assert issue["health"] == "Critical"
    assert any("has failed" in d for d in issue["details"])
    assert "post-erase" not in issue["next_step"]


def test_completed_erase_alone_does_not_create_a_health_alert():
    drive = {"Location": "1I:1:1", "Model": "Fixture drive", "CapacityBytes": 300000000000,
             "Status": {"Health": "OK"}, "DiskDriveStatusReasons": ["EraseCompleted"]}
    assert hardware_health.health_issues({"storage": {"physical_drives": [drive]}}) == []


def test_unexplained_aggregate_names_components_without_claiming_causality():
    issues = hardware_health.health_issues({'storage':{'controllers':[{'Model':'Fixture controller','Status':{'Health':'Warning'}}]},
                                          'systems':[{'Model':'Fixture server','Status':{'Health':'Warning'}}]})
    assert 'Cause not established' in issues[0]['details'][0]
    assert 'Cause not established' in issues[1]['details'][0]
    assert any('Fixture controller' in d and 'not confirmed' in d for d in issues[1]['details'])


def test_iml_is_bounded_get_only_history(monkeypatch):
    from app.providers import ilo_redfish as provider
    calls = []
    def get(client, base, path, requests):
        calls.append(path)
        return {'Members':[{'Id':str(i),'Message':'Fixture old event','Severity':'Warning',
                           'Oem':{'Hpe':{'Repaired':True,'RecommendedAction':'Review fixture component'}}} for i in range(30)],
                'Members@odata.nextLink':'https://untrusted.invalid/'}
    monkeypatch.setattr(provider,'_get_json',get)
    result = provider._iml_diagnostics(None,'https://192.0.2.10',[{'@odata.id':'/redfish/v1/Systems/1/'}],[])
    assert calls == ['/redfish/v1/Systems/1/LogServices/IML/Entries/']
    assert len(result['entries']) == 16
    assert result['entries'][0]['Repaired'] is True
    assert result['entries'][0]['HpeRecommendedAction'] == 'Review fixture component'
    assert not result['complete'] and 'not necessarily' not in result['message']
    assert 'not the full log or necessarily the newest' in result['message']


@pytest.mark.parametrize('status, expected', [(403,'access denied'),(404,'not available'),(500,'HTTP 500')])
def test_iml_read_failure_is_explained_without_failing_inventory(monkeypatch,status,expected):
    import httpx
    from app.providers import ilo_redfish as provider
    def get(*args):
        response = httpx.Response(status,request=httpx.Request('GET','https://192.0.2.10/redfish/v1/'))
        response.raise_for_status()
    monkeypatch.setattr(provider,'_get_json',get)
    result=provider._iml_diagnostics(None,'https://192.0.2.10',[{'@odata.id':'/redfish/v1/Systems/1/'}],[])
    assert result['entries']==[] and expected in result['message']


@pytest.fixture
def health_fixture(client, monkeypatch):
    profile = client.post('/api/v1/lab/profiles', json={'name':'Health kit','profile_topology':'custom','subnet_cidr':'192.0.2.0/24'}).json()
    base = '/api/v1/rack-plans/' + profile['id']
    plan = client.put(base, json={'equipment':[{'id':'server','kind':'server','name':'Server','model':'HPE DL360','position':1,'height':1}]}).json()
    device = plan['equipment'][0]['device_id']
    state = {'checked_at':datetime.now(UTC).isoformat(), 'target_matches':True}
    probe = {'status':'ok','target_fingerprint':'target-a','storage':{'physical_drives':[
        {'@odata.id':'/drives/4','Location':'1I:1:4','Model':'Fixture failed drive','CapacityBytes':300e9,'Status':{'Health':'Critical'},'DiskDriveStatusReasons':['CommunicationFailure']},
        {'@odata.id':'/drives/5','Location':'2I:1:5','Model':'Fixture drive','CapacityBytes':1200e9,'DiskDriveUse':'Unconfigured','Status':{'Health':'OK'}},
    ], 'controllers':[{'@odata.id':'/controllers/0','Model':'Fixture controller','Status':{'Health':'Warning'}}]}}
    def read_probe(provider, *, scope):
        assert scope == device
        return probe, state['checked_at']
    monkeypatch.setattr(hardware_health, 'get_probe_result', read_probe)
    monkeypatch.setattr(hardware_health, 'read_ilo_access_settings', lambda *a: {'host':'192.0.2.10','last_probe_is_current':True,'last_probe_target_matches_access_host':state['target_matches']})
    monkeypatch.setattr(firmware_review, 'read_ilo_access_settings', lambda *a: {'host':'192.0.2.10'})
    def assessment(profile_id, device_id, session):
        return {'health_review':hardware_health.read_health_review(session, profile_id, device_id),'metadata_sha256':'metadata',
                'package_file':'fixture-spp.iso','detected_model':'Fixture server','rows':[
                    {'component':'iLO','installed':'1.37','target':'3.19','status':'Update available','reason':'Matched','files':['ilo.fwpkg']}
                ]}
    monkeypatch.setattr(firmware_review, 'firmware_assessment', assessment)
    return base, device, probe, state


def test_vendor_status_reasons_and_unconfigured_are_not_conflated():
    drive = _drive_summary({'Location':'1I:1:4','Status':{'Health':'Critical'},'DiskDriveStatusReasons':['CommunicationFailure'],'DiskDriveUse':'Unconfigured'})
    assert drive['DiskDriveStatusReasons'] == ['CommunicationFailure']
    assert drive['DiskDriveUse'] == 'Unconfigured'
    volume = _logical_drive_summary({'LogicalDriveStatusReasons':['Rebuilding']})
    assert volume['LogicalDriveStatusReasons'] == ['Rebuilding']
    assert hardware_health.health_issues({'storage':{'physical_drives':[{'Model':'Fixture drive','CapacityBytes':300e9,'Status':{'Health':'OK'},'DiskDriveUse':'Unconfigured'}]}}) == []


def test_failed_spare_and_aggregate_health_are_explained_without_guessing():
    issues = hardware_health.health_issues({
        'storage': {'physical_drives': [{'Location':'1I:1:4','CapacityBytes':0,
            'DiskDriveUse':'Spare','DiskDriveStatusReasons':['Failed'],'Status':{'Health':'Critical'}}]},
        'systems': [{'Model':'ProLiant DL360 Gen10','Status':{'Health':'Warning'}}],
        'chassis': [{'Model':'ProLiant DL360 Gen10','Status':{'Health':'Warning'}}],
    })
    assert len(issues) == 2
    drive, server = issues
    assert drive['facts']['DiskDriveUse'] == 'Spare'
    assert drive['health'] == 'Warning'
    assert 'not a confirmed physical-drive failure' in drive['details'][0]
    assert drive['facts']['Original iLO health'] == 'Critical'
    assert 'Failed' in drive['details'][1]
    assert server['facts']['Chassis health'] == 'Warning'
    assert any('not a separate diagnosed fault' in detail for detail in server['details'])


def test_known_failed_drive_remains_critical_and_explicit_absence_is_warning():
    drive = {'Model':'Fixture drive','CapacityBytes':300e9,'Status':{'Health':'Critical'},'DiskDriveStatusReasons':['Failed']}
    assert hardware_health.drive_condition(drive)['health'] == 'Critical'
    assert hardware_health.health_issues({'storage':{'physical_drives':[drive]}})[0]['details'][0].endswith('has failed.')
    drive['Status']['State'] = 'Absent'
    condition = hardware_health.drive_condition(drive)
    assert condition['health'] == 'Warning' and condition['presence'] == 'absent'


def test_acknowledgement_is_bound_to_evidence_and_never_unlocks_execution(client, health_fixture):
    base, device, probe, state = health_fixture
    url = base+'/firmware-upgrade-review?device_id='+device
    review = client.get(url).json()
    assert len(review['health_review']['issues']) == 2
    assert 'cannot communicate' in review['health_review']['issues'][0]['details'][0]
    assert not review['can_save_review'] and not review['apply_enabled']
    for issue in review['health_review']['issues']:
        response = client.post(base+'/health-acknowledgements?device_id='+device,
                               json={'review_token':review['health_review']['review_token'],'issue_id':issue['id']})
        assert response.status_code == 200, response.text
    reviewed = client.get(url).json()
    assert reviewed['can_save_review'] and not reviewed['apply_enabled']
    assert reviewed['health_review']['unacknowledged'] == 0
    assert any('remain unresolved' in b for b in reviewed['blockers'])
    assert client.post(url, json={'review_token':reviewed['review_token']}).status_code == 200
    assert client.post(url, json={'review_token':reviewed['review_token'],'apply_enabled':True}).status_code == 422
    state['checked_at'] = (datetime.now(UTC)+timedelta(seconds=1)).isoformat()
    assert client.get(url).json()['health_review']['unacknowledged'] == 2
    assert client.post(url, json={'review_token':reviewed['review_token']}).status_code == 409
    probe['storage']['physical_drives'][0]['Status']['Health'] = 'OK'
    probe['storage']['physical_drives'][0]['DiskDriveStatusReasons'] = []
    assert len(client.get(url).json()['health_review']['issues']) == 1


def test_missing_stale_retargeted_and_cross_kit_reviews_are_rejected(client, health_fixture):
    base, device, probe, state = health_fixture
    url = base+'/firmware-upgrade-review?device_id='+device
    review = client.get(url).json()
    body = {'review_token':review['health_review']['review_token'],'issue_id':review['health_review']['issues'][0]['id']}
    state['checked_at'] = (datetime.now(UTC)-timedelta(hours=1)).isoformat()
    assert not client.get(url).json()['health_review']['current']
    assert client.post(base+'/health-acknowledgements?device_id='+device,json=body).status_code == 409
    state['target_matches'] = False
    assert client.get(url).json()['health_review']['issues'] == []
    assert client.get(base+'/firmware-upgrade-review?device_id=other-server').status_code == 404
    assert client.post(base+'/health-acknowledgements?device_id=other-server',json=body).status_code == 404
