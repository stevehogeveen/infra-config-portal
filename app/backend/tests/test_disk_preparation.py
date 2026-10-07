from datetime import datetime, UTC
import pytest
from app.api import disk_preparation as module


@pytest.fixture
def disk_fixture(client, monkeypatch):
    kit=client.post('/api/v1/lab/profiles',json={'name':'Storage kit','profile_topology':'custom','subnet_cidr':'192.0.2.0/24'}).json()
    base='/api/v1/rack-plans/'+kit['id']
    saved=client.put(base,json={'equipment':[{'id':'s','name':'Server','kind':'server','model':'HPE DL360','position':1,'height':1}]}).json()
    device=saved['equipment'][0]['device_id']
    controller='/redfish/v1/Systems/1/SmartStorage/ArrayControllers/0/'
    probe={'status':'ok','target_fingerprint':'fixture','storage':{'controllers':[{'@odata.id':controller,'Model':'Fixture controller','Status':{'Health':'OK'}}],
           'physical_drives':[{'@odata.id':controller+'DiskDrives/'+str(i)+'/', 'Location':f'1I:1:{i+1}','Model':'Fixture drive','CapacityBytes':300000000000,'MediaType':'HDD','Status':{'Health':'OK' if i<2 else 'Critical'}} for i in range(3)],
           'logical_drives':[{'@odata.id':controller+'LogicalDrives/1/','Id':'1','RAIDType':'RAID1','CapacityBytes':300000000000}]}}
    monkeypatch.setattr(module,'get_probe_result',lambda *a,**kw:(probe,now))
    monkeypatch.setattr(module,'read_ilo_access_settings',lambda *a:{'host':'192.0.2.10','last_probe_is_current':True,'last_probe_target_matches_access_host':True})
    now=datetime.now(UTC).isoformat()
    return base+'/disk-preparation?device_id='+device,probe


def test_review_and_save_without_hardware_calls(client,disk_fixture):
    url,probe=disk_fixture
    view=client.get(url).json()
    assert not view['apply_enabled']
    assert len(view['health_issues'])==1
    assert not view['drives'][2]['eligible']
    body={'inventory_token':view['inventory_token'],'boot_drive_ids':[d['id'] for d in view['drives'][:2]],'remove_existing_volumes':True,'data_loss_reviewed':True}
    saved=client.post(url,json=body)
    assert saved.status_code==200,saved.text
    assert saved.json()['intent']['volumes'][0]['drive_bays']==['1I:1:1','1I:1:2']
    assert 'No disks changed' in saved.json()['message']
    body['data_loss_reviewed']=False
    assert client.post(url,json=body).status_code==422
    body['data_loss_reviewed']=True
    body['boot_drive_ids'][1]=view['drives'][2]['id']
    assert client.post(url,json=body).status_code==422


def test_mirror_verification_requires_exact_members(client,disk_fixture):
    url,probe=disk_fixture
    view=client.get(url).json()
    body={'inventory_token':view['inventory_token'],'boot_drive_ids':[d['id'] for d in view['drives'][:2]],'remove_existing_volumes':True,'data_loss_reviewed':True}
    assert client.post(url,json=body).status_code==200
    assert not client.get(url).json()['boot_mirror_matches']
    volume=probe['storage']['logical_drives'][0]
    volume['Status']={'Health':'OK'}
    volume['physical_drive_paths']=body['boot_drive_ids']
    assert client.get(url).json()['boot_mirror_matches']
    volume['physical_drive_paths']=[body['boot_drive_ids'][0]]
    assert not client.get(url).json()['boot_mirror_matches']


def test_stale_or_changed_inventory_rejected(client,disk_fixture,monkeypatch):
    url,probe=disk_fixture
    view=client.get(url).json()
    body={'inventory_token':view['inventory_token'],'boot_drive_ids':[d['id'] for d in view['drives'][:2]],'remove_existing_volumes':True,'data_loss_reviewed':True}
    probe['storage']['physical_drives'][0]['CapacityBytes']=100
    assert client.post(url,json=body).status_code==409
    monkeypatch.setattr(module,'get_probe_result',lambda *a,**kw:(probe,'2000-01-01T00:00:00+00:00'))
    assert not client.get(url).json()['current']
    assert client.post(url,json=body).status_code==409


def test_mismatched_capacity_and_cross_kit_server_are_rejected(client,disk_fixture):
    url,probe=disk_fixture
    probe['storage']['physical_drives'][1]['CapacityBytes']=600000000000
    view=client.get(url).json()
    body={'inventory_token':view['inventory_token'],'boot_drive_ids':[d['id'] for d in view['drives'][:2]],'remove_existing_volumes':True,'data_loss_reviewed':True}
    assert client.post(url,json=body).status_code==422
    assert client.get(url.split('?')[0]+'?device_id=not-in-this-kit').status_code==404


@pytest.mark.parametrize('spare_for', ['boot', 'data'])
def test_save_all_drive_roles_together(client, disk_fixture, spare_for):
    from copy import deepcopy
    url, probe = disk_fixture
    drives = probe['storage']['physical_drives']
    template = deepcopy(drives[0])
    drives[:] = [{**deepcopy(template), '@odata.id':template['@odata.id'] + str(i), 'Location':f'1I:1:{i}'} for i in range(1, 7)]
    view = client.get(url).json()
    body = {'inventory_token':view['inventory_token'], 'boot_drive_ids':[d['id'] for d in view['drives'][:2]],
            'data_drive_ids':[d['id'] for d in view['drives'][2:5]], 'data_raid':'RAID5',
            'spare_drive_ids':[view['drives'][5]['id']], 'spare_for':spare_for,
            'remove_existing_volumes':True, 'data_loss_reviewed':True}
    result = client.post(url, json=body)
    assert result.status_code == 200, result.text
    saved = client.get(url).json()['saved_intent']['volumes']
    protected = saved[0 if spare_for == 'boot' else 1]
    assert protected['spare_bays'] == ['1I:1:6']
    assert protected['spare_rebuild_mode'] == 'Dedicated'
    assert saved[0]['drive_bays'] == ['1I:1:1', '1I:1:2']
    assert saved[1]['drive_bays'] == ['1I:1:3', '1I:1:4', '1I:1:5']


@pytest.mark.parametrize('fault', ['overlap', 'missing', 'small', 'media', 'failed', 'foreign_controller', 'no_array', 'two_spares'])
def test_invalid_spare_is_rejected(client, disk_fixture, fault):
    url, probe = disk_fixture
    drives = probe['storage']['physical_drives']
    drives[2]['Status']['Health'] = 'OK'
    if fault == 'small': drives[2]['CapacityBytes'] = 1000
    if fault == 'media': drives[2]['MediaType'] = 'SSD'
    if fault == 'failed': drives[2]['Status']['Health'] = 'Critical'
    if fault == 'foreign_controller': drives[2]['@odata.id'] = '/redfish/v1/Systems/other/Drives/3/'
    view = client.get(url).json()
    body = {'inventory_token':view['inventory_token'], 'boot_drive_ids':[d['id'] for d in view['drives'][:2]],
            'spare_drive_ids':[view['drives'][2]['id']], 'spare_for':'boot', 'remove_existing_volumes':True, 'data_loss_reviewed':True}
    if fault == 'overlap': body['spare_drive_ids'] = [body['boot_drive_ids'][0]]
    if fault == 'missing': body['spare_drive_ids'] = ['missing']
    if fault == 'no_array': body['spare_for'] = 'data'
    if fault == 'two_spares': body['spare_drive_ids'] *= 2
    assert client.post(url, json=body).status_code == 422


def test_stale_read_is_shown_for_display_only(client, disk_fixture, monkeypatch):
    url, probe = disk_fixture
    volume = probe['storage']['logical_drives'][0]
    volume['physical_drive_paths'] = [d['@odata.id'] for d in probe['storage']['physical_drives'][:2]]
    fresh = client.get(url).json()
    assert fresh['last_read'] is None
    assert fresh['volumes'][0]['bays'] == ['1I:1:1', '1I:1:2']
    monkeypatch.setattr(module, 'get_probe_result', lambda *a, **kw: (probe, '2000-01-01T00:00:00+00:00'))
    stale = client.get(url).json()
    assert not stale['current'] and stale['drives'] == [] and stale['volumes'] == []
    assert [d['location'] for d in stale['last_read']['drives']] == ['1I:1:1', '1I:1:2', '1I:1:3']
    assert stale['last_read']['volumes'][0]['bays'] == ['1I:1:1', '1I:1:2']
