from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from app.api import disk_preparation, raid_rebuild
from app.providers import hpe_storage_rebuild as provider
from app.services.hardware_health import digest


def test_live_scope_allows_only_explicit_raid_action(monkeypatch):
    from dataclasses import replace
    from app.providers.action_policy import current_lab_action_policy, ActionCategory
    policy = replace(current_lab_action_policy(), provider_mode='local-lab-readwrite',
                     lab_environment='isolated-real-lab', acknowledge_real_hardware=True,
                     acknowledge_device_reconfiguration=True, acknowledge_data_loss_risk=True,
                     acknowledge_lab_only=True)
    monkeypatch.setenv('LAB_ALLOWED_WRITE_ACTIONS', 'ilo-redfish.hpe-raid-apply')
    assert policy.action_blockers('ilo-redfish.hpe-raid-apply', ActionCategory.STORAGE_CONFIG) == []
    assert any('scope' in b for b in policy.action_blockers('cisco.configure', ActionCategory.NETWORK_CONFIG))
    assert any('scope' in b for b in policy.action_blockers('ilo.power', ActionCategory.POWER_ACTION))
    monkeypatch.setenv('LAB_ALLOWED_WRITE_ACTIONS', '')
    assert any('scope' in b for b in policy.action_blockers('ilo-redfish.hpe-raid-apply', ActionCategory.STORAGE_CONFIG))
    assert replace(policy, provider_mode='local-readonly').action_blockers('ilo-redfish.hpe-raid-apply', ActionCategory.STORAGE_CONFIG)


@pytest.fixture
def rebuild(client, monkeypatch):
    kit = client.post('/api/v1/lab/profiles', json={'name':'Rebuild kit','profile_topology':'custom','subnet_cidr':'192.0.2.0/24'}).json()
    base = '/api/v1/rack-plans/' + kit['id']
    plan = client.put(base, json={'equipment':[{'id':'s','name':'Server','kind':'server','model':'HPE DL360','position':1,'height':1}]}).json()
    device = plan['equipment'][0]['device_id']
    monkeypatch.setenv('HPE_RAID_RESET_DEVICE_IDS', device)
    ctrl = '/redfish/v1/Systems/1/SmartStorage/ArrayControllers/0/'
    drives = [{'@odata.id':ctrl+'DiskDrives/'+str(i)+'/', 'Location':f'1I:1:{i}', 'Model':'Fixture disk',
               'CapacityBytes':300000000000,'MediaType':'HDD','Status':{'Health':'OK'}} for i in range(1,7)]
    drives.append({'@odata.id':ctrl+'DiskDrives/7/', 'Location':'1I:1:7','CapacityBytes':0,
                   'DiskDriveUse':'Spare','DiskDriveStatusReasons':['Failed'],'Status':{'Health':'Critical'}})
    probe = {'status':'ok','target_fingerprint':'fixture','storage':{'controllers':[{'@odata.id':ctrl,'Model':'Fixture controller','Location':'Slot 0','Status':{'Health':'Warning'}}],
             'physical_drives':drives,'logical_drives':[{'@odata.id':ctrl+'LogicalDrives/1/','Id':'1','RAIDType':'RAID1','CapacityBytes':300000000000}]}}
    config = {'LogicalDrives':[{'LogicalDriveName':'Old volume','Raid':'Raid1','DataDrives':['1I:1:1','1I:1:2']}],
              '@Redfish.Settings':{'Messages':[{'MessageId':'Base.1.0.Success'}]}}
    state = {'current':deepcopy(config),'pending':deepcopy(config),'power':'Off','identity':'identity','writes':[]}
    checked_at=datetime.now(UTC).isoformat()
    monkeypatch.setattr(disk_preparation,'get_probe_result',lambda *a,**k:(probe,checked_at))
    monkeypatch.setattr(disk_preparation,'read_ilo_access_settings',lambda *a:{'host':'192.0.2.10','last_probe_is_current':True,'last_probe_target_matches_access_host':True})
    def snapshot(*a):
        return {**state,'probe':probe,'path':'/redfish/v1/Systems/1/SmartStorageConfig/Settings/',
                'state_digest':digest({'storage':probe['storage'],'current':state['current'],'pending':state['pending'],'power':state['power'],'identity':state['identity']}),
                'pending_differs':provider.logical_signature(state['current'])!=provider.pending_signature(state['pending']) or bool(state['pending'].get('Actions'))}
    monkeypatch.setattr(raid_rebuild,'read_snapshot',snapshot)
    monkeypatch.setattr(raid_rebuild,'write_blockers',lambda:[])
    def stage(s,payload):
        state['writes'].append(deepcopy(payload));state['pending']=deepcopy(payload)
        return {'status':'pending','message':'Staged, not verified.'}
    monkeypatch.setattr(raid_rebuild,'stage_configuration',stage)
    url = base+'/disk-preparation?device_id='+device
    view = client.get(url).json()
    body = {'inventory_token':view['inventory_token'],'boot_drive_ids':[d['id'] for d in view['drives'][:2]],
            'data_drive_ids':[d['id'] for d in view['drives'][2:6]],'data_raid':'RAID5','remove_existing_volumes':True,'data_loss_reviewed':True}
    saved = client.post(url,json=body)
    assert saved.status_code == 200, saved.text
    return base+'/raid-rebuild/', device, probe, state, url, body


def confirmation(review):
    return {'preview_id':review['preview_id'],'confirmation':review['confirmation'],
            'data_loss_confirmed':True,'backups_confirmed':True,'health_reviewed':True,'firmware_reviewed':True,
            'empty_bays_confirmed':review['empty_bays']}


def test_create_preview_identifies_ineligible_drive_without_sending_write(client, rebuild):
    base, device, probe, state, _, _ = rebuild
    probe['storage']['physical_drives'][0]['Status']['Health'] = 'Warning'
    probe['storage']['physical_drives'][0]['DiskDriveStatusReasons'] = ['EraseCompleted']
    response = client.post(base + 'preview?device_id=' + device, json={'operation': 'create'})
    assert response.status_code == 409
    assert '1I:1:1: Warning' in response.json()['detail']
    assert 'Re-saving the same plan does not clear' in response.json()['detail']
    assert state['writes'] == []


def test_shutdown_is_previewed_once_and_force_is_separate(client, rebuild, monkeypatch, db_session):
    from types import SimpleNamespace
    base, device, _, state, _, _ = rebuild
    state['power'] = 'On'
    endpoint = lambda action: base + action + '?device_id=' + device
    monkeypatch.setattr(raid_rebuild, 'current_lab_action_policy', lambda: SimpleNamespace(action_blockers=lambda *a: []))
    monkeypatch.setattr(raid_rebuild, 'shutdown_action', lambda s, force: ('/reset', {'ResetType':'ForceOff' if force else 'PushPowerButton'}))
    sent = []
    monkeypatch.setattr(raid_rebuild, 'request_shutdown', lambda s,p,b: sent.append(b) or {'status':'requested','message':'Requested'})
    assert not client.post(endpoint('shutdown-preview'),json={'force':True}).json()['apply_enabled']
    review = client.post(endpoint('shutdown-preview'),json={'force':False}).json()
    assert review['apply_enabled'] and not sent
    body = {'preview_id':review['preview_id'],'confirmation':review['confirmation'],'downtime_confirmed':True,'data_loss_confirmed':True}
    assert client.post(endpoint('shutdown'),json={**body,'confirmation':'wrong'}).status_code == 422
    assert client.post(endpoint('shutdown'),json=body).status_code == 200
    assert client.post(endpoint('shutdown'),json=body).status_code == 409
    assert sent == [{'ResetType':'PushPowerButton'}]
    assert not client.post(endpoint('shutdown-preview'),json={'force':True}).json()['apply_enabled']
    claim = raid_rebuild.latest_event(db_session,device,'shutdown_attempt')
    claim.created_at = datetime.now(UTC) - timedelta(minutes=3)
    db_session.commit()
    force = client.post(endpoint('shutdown-preview'),json={'force':True}).json()
    assert force['apply_enabled'] and force['confirmation'].startswith('FORCE POWER OFF')
    # Merely reviewing the fallback must never force the server off.
    assert len(sent) == 1


def test_reset_requires_explicit_device_scope(client, rebuild, monkeypatch):
    base, device, _, state, _, _ = rebuild
    monkeypatch.setattr(raid_rebuild, 'reset_blockers', lambda: [])
    monkeypatch.setenv('HPE_RAID_RESET_DEVICE_IDS', 'another-device')
    review = client.post(base+'preview?device_id='+device,json={'operation':'reset'}).json()
    assert not review['apply_enabled']
    assert any('not enabled' in b for b in review['blockers'])
    assert not state['writes']


def test_controller_reset_has_separate_gate_and_exact_payload(client, rebuild, monkeypatch):
    base, device, probe, state, _, _ = rebuild
    endpoint = lambda action: base + action + '?device_id=' + device
    monkeypatch.setattr(raid_rebuild, 'reset_blockers', lambda: ['Controller reset disabled'])
    review = client.post(endpoint('preview'), json={'operation': 'reset'}).json()
    assert not review['apply_enabled']
    assert client.post(endpoint('apply'), json=confirmation(review)).status_code == 409
    assert not state['writes']
    monkeypatch.setattr(raid_rebuild, 'reset_blockers', lambda: [])
    review = client.post(endpoint('preview'), json={'operation': 'reset'}).json()
    assert review['apply_enabled'], review
    assert review['confirmation'] == 'RESET STORAGE CONTROLLER Server'
    assert review['payload'] == {'Actions': [{'Action': 'FactoryReset'}], 'DataGuard': 'Disabled'}
    assert client.post(endpoint('apply'), json=confirmation(review)).status_code == 200
    assert client.post(endpoint('apply'), json=confirmation(review)).status_code == 409
    # iLO may return only the reset action; submission is not proof of reset.
    assert 'LogicalDrives' not in state['pending']
    assert not client.post(endpoint('verify')).json()['verified']
    state['current'] = {'LogicalDrives': [], '@Redfish.Settings': {'Messages': [
        {'MessageId': 'SmartStorageMessages.2.0.Success'}]}}
    state['pending'] = deepcopy(state['current'])
    result = client.post(endpoint('verify')).json()
    assert result['verified'], result
    assert 'health' in result['message']


def test_reset_cannot_bypass_unresolved_delete(client, rebuild, monkeypatch):
    base, device, _, state, _, _ = rebuild
    endpoint = lambda action: base + action + '?device_id=' + device
    monkeypatch.setattr(raid_rebuild, 'reset_blockers', lambda: [])
    review = client.post(endpoint('preview'), json={'operation': 'clear'}).json()
    assert client.post(endpoint('apply'), json=confirmation(review)).status_code == 200
    state['pending'] = deepcopy(state['current'])
    review = client.post(endpoint('preview'), json={'operation': 'reset'}).json()
    assert not review['apply_enabled']
    assert any('previous storage request' in b for b in review['blockers'])
    assert len(state['writes']) == 1


def test_reset_requires_exact_recognized_payload():
    assert provider.requested_layout_matches({'LogicalDrives': []}, {
        'Actions': [{'Action': 'FactoryReset'}], 'DataGuard': 'Disabled'})
    with pytest.raises(provider.StorageRebuildError):
        provider.requested_layout_matches({'LogicalDrives': []}, {
            'Actions': [{'Action': 'SomethingElse'}], 'DataGuard': 'Disabled'})


def test_confirmed_rejection_allows_only_separate_recovery(client, rebuild, monkeypatch, db_session):
    base, device, _, state, _, _ = rebuild
    endpoint = lambda action: base + action + '?device_id=' + device
    monkeypatch.setattr(raid_rebuild, 'reset_blockers', lambda: [])
    review = client.post(endpoint('preview'), json={'operation': 'clear'}).json()
    applied = client.post(endpoint('apply'), json=confirmation(review)).json()
    boot = raid_rebuild.audit(db_session, 'test', 'kit.raid_rebuild.boot_attempt', 'Fixture boot',
                             {'device_id': device, 'attempt_id': applied['attempt_id']})
    boot.created_at = datetime.now(UTC) - timedelta(minutes=2)
    db_session.commit()
    state['pending'] = deepcopy(state['current'])
    state['current']['@Redfish.Settings'] = {
        'Time': (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        'Messages': [{'MessageId': 'SmartStorageMessages.2.0.1.CanCreateEditableConfigControllerStatusNotOK'}]}
    result = client.post(endpoint('verify')).json()
    assert not result['verified']
    status = client.get(endpoint('status')).json()
    assert status['status'] == 'failed' and not status['active']
    assert not client.post(endpoint('preview'), json={'operation': 'clear'}).json()['apply_enabled']
    reset = client.post(endpoint('preview'), json={'operation': 'reset'}).json()
    assert reset['apply_enabled'], reset
    assert len(state['writes']) == 1  # Classification and previews never touch hardware.
    assert raid_rebuild.latest_event(db_session, device, 'failed', applied['attempt_id'])
    assert not raid_rebuild.latest_event(db_session, device, 'verified', applied['attempt_id'])


def test_spare_is_staged_and_verified_with_both_arrays(client, rebuild):
    base, device, probe, state, url, body = rebuild
    probe['storage']['controllers'][0]['Status']['Health'] = 'OK'
    # Match read_snapshot/disk_preparation: unnamed storage containers are not controllers.
    probe['storage']['controllers'].insert(0, {'@odata.id': '/redfish/v1/Systems/1/Storage/'})
    body['inventory_token'] = client.get(url).json()['inventory_token']
    body['data_drive_ids'] = body['data_drive_ids'][:3]
    body['spare_drive_ids'] = [client.get(url).json()['drives'][5]['id']]
    body['spare_for'] = 'data'
    assert client.post(url, json=body).status_code == 200
    state['current'] = {'LogicalDrives':[]}
    state['pending'] = deepcopy(state['current'])
    probe['storage']['logical_drives'] = []
    endpoint = lambda action: base + action + '?device_id=' + device
    review = client.post(endpoint('preview'), json={'operation':'create'}).json()
    assert review['apply_enabled'], review
    volume = review['payload']['LogicalDrives'][1]
    assert volume['SpareDrives'] == ['1I:1:6'] and volume['SpareRebuildMode'] == 'Dedicated'
    assert client.post(endpoint('apply'), json=confirmation(review)).status_code == 200
    state['current'] = {**deepcopy(state['writes'][0]), '@Redfish.Settings':{'Messages':[{'MessageId':'Base.1.0.Success'}]}}
    state['pending'] = deepcopy(state['current'])
    state['current']['LogicalDrives'][1]['SpareRebuildMode'] = 'Roaming'
    assert not client.post(endpoint('verify')).json()['verified']
    state['current']['LogicalDrives'][1]['SpareRebuildMode'] = 'Dedicated'
    assert client.post(endpoint('verify')).json()['verified']


@pytest.mark.parametrize('fault', ['small', 'failed', 'overlap'])
def test_changed_spare_blocks_execution(client, rebuild, fault):
    base, device, probe, state, url, body = rebuild
    body['data_drive_ids'] = body['data_drive_ids'][:3]
    body['spare_drive_ids'] = [client.get(url).json()['drives'][5]['id']]
    assert client.post(url, json=body).status_code == 200
    endpoint = lambda action: base + action + '?device_id=' + device
    review = client.post(endpoint('preview'), json={'operation':'clear'}).json()
    spare = probe['storage']['physical_drives'][5]
    if fault == 'small': spare['CapacityBytes'] = 1
    elif fault == 'failed': spare['Status']['Health'] = 'Critical'
    else: spare['Location'] = '1I:1:1'
    assert client.post(endpoint('apply'), json=confirmation(review)).status_code == 409
    assert state['writes'] == []


def test_clear_verify_then_recreate_and_never_replay(client,rebuild):
    base,device,probe,state,url,body = rebuild
    endpoint=lambda action:base+action+'?device_id='+device
    view=client.get(url).json()
    assert view['drives'][-1]['health']=='Warning' and not view['drives'][-1]['eligible']
    assert len(view['saved_intent']['volumes'])==2
    review=client.post(endpoint('preview'),json={'operation':'clear'}).json()
    assert review['apply_enabled'],review
    assert review['empty_bays']==['1I:1:7']
    assert state['writes']==[]
    bad=confirmation(review);bad['empty_bays_confirmed']=[]
    assert client.post(endpoint('apply'),json=bad).status_code==422
    result=client.post(endpoint('apply'),json=confirmation(review))
    assert result.status_code==200,result.text
    assert result.json()['status']=='pending' and not result.json()['verified']
    assert state['writes'][0]['LogicalDrives']==[]
    assert state['writes'][0]['Actions']==[{'Action':'ClearConfigurationMetadata'}]
    assert client.post(endpoint('apply'),json=confirmation(review)).status_code==409
    assert not client.post(endpoint('preview'),json={'operation':'create'}).json()['apply_enabled']
    state['current']={'LogicalDrives':[],'@Redfish.Settings':{'Messages':[{'MessageId':'Base.1.0.Success'}]}}
    state['pending']=deepcopy(state['current']);probe['storage']['logical_drives']=[]
    assert client.post(endpoint('verify')).json()['verified']
    probe['storage']['controllers'][0]['Status']['Health'] = 'OK'
    create=client.post(endpoint('preview'),json={'operation':'create'}).json()
    assert create['apply_enabled'],create
    assert client.post(endpoint('apply'),json=confirmation(create)).status_code==200
    assert len(state['writes'])==2
    volumes=state['writes'][1]['LogicalDrives']
    assert volumes[0]['Raid']=='Raid1' and volumes[0]['DataDrives']==['1I:1:1','1I:1:2']
    assert volumes[1]['Raid']=='Raid5' and volumes[1]['DataDrives']==['1I:1:3','1I:1:4','1I:1:5','1I:1:6']
    assert not set(volumes[0]['DataDrives']) & set(volumes[1]['DataDrives'])
    assert not client.post(endpoint('verify')).json()['verified']
    state['current']={**deepcopy(state['writes'][1]),'@Redfish.Settings':{'Messages':[{'MessageId':'Base.1.0.Success'}]}}
    state['pending']=deepcopy(state['current'])
    assert client.post(endpoint('verify')).json()['verified']
    state['current']['LogicalDrives'][1]['DataDrives'].pop()
    state['pending']=deepcopy(state['current'])
    assert not client.post(endpoint('verify')).json()['verified']


@pytest.mark.parametrize('change',['drives','identity','power','pending','policy','known_failure'])
def test_preflight_changes_and_policy_block_writes(client,rebuild,monkeypatch,change):
    base,device,probe,state,_,_ = rebuild
    endpoint=lambda action:base+action+'?device_id='+device
    review=client.post(endpoint('preview'),json={'operation':'clear'}).json()
    if change=='drives':probe['storage']['physical_drives'][0]['Model']='Replacement drive'
    elif change=='identity':state['identity']='other-server'
    elif change=='power':state['power']='On'
    elif change=='pending':state['pending']['LogicalDrives']=[]
    elif change=='policy':monkeypatch.setattr(raid_rebuild,'write_blockers',lambda:['Read-only mode'])
    else:probe['storage']['physical_drives'][0]['Status']['Health']='Critical'
    result=client.post(endpoint('apply'),json=confirmation(review))
    assert result.status_code==409,result.text
    assert not state['writes']


def test_bad_confirmation_cross_device_and_overlap_are_rejected(client,rebuild):
    base,device,probe,state,url,body=rebuild
    review=client.post(base+'preview?device_id='+device,json={'operation':'clear'}).json()
    bad=confirmation(review);bad['confirmation']='yes'
    assert client.post(base+'apply?device_id='+device,json=bad).status_code==422
    assert client.post(base+'apply?device_id=other',json=confirmation(review)).status_code==404
    bad=confirmation(review);bad['backups_confirmed']=False
    assert client.post(base+'apply?device_id='+device,json=bad).status_code==422
    body['inventory_token']=client.get(url).json()['inventory_token']
    body['data_drive_ids'][0]=body['boot_drive_ids'][0]
    assert client.post(url,json=body).status_code==422
    assert not state['writes']


def test_timeout_claim_blocks_retry(client,rebuild,monkeypatch):
    base,device,probe,state,_,_=rebuild
    endpoint=lambda action:base+action+'?device_id='+device
    def timeout(s,p):
        state['writes'].append(p)
        return {'status':'uncertain','message':'Response lost. Inspect pending settings.'}
    monkeypatch.setattr(raid_rebuild,'stage_configuration',timeout)
    review=client.post(endpoint('preview'),json={'operation':'clear'}).json()
    assert client.post(endpoint('apply'),json=confirmation(review)).json()['status']=='uncertain'
    assert client.post(endpoint('apply'),json=confirmation(review)).status_code==409
    assert not client.post(endpoint('preview'),json={'operation':'clear'}).json()['apply_enabled']
    assert len(state['writes'])==1


@pytest.fixture
def staged_boot(client, rebuild, monkeypatch):
    base, device, probe, state, _, _ = rebuild
    endpoint = lambda action: base + action + '?device_id=' + device
    review = client.post(endpoint('preview'), json={'operation':'clear'}).json()
    client.post(endpoint('apply'), json=confirmation(review))
    state['power_writes'] = []
    monkeypatch.setattr(raid_rebuild, 'boot_blockers', lambda: [])
    monkeypatch.setattr(raid_rebuild, 'read_boot_action', lambda s: '/redfish/v1/Systems/1/Actions/ComputerSystem.Reset/')
    def start(snapshot, path):
        state['power_writes'].append(path)
        return {'status':'waiting','message':'Waiting for POST'}
    monkeypatch.setattr(raid_rebuild, 'start_server', start)
    return endpoint, state


def boot_confirmation(review):
    return {'preview_id':review['preview_id'], 'confirmation':review['confirmation'],
            'pending_changes_reviewed':True, 'data_loss_confirmed':True, 'maintenance_confirmed':True}


def test_rejected_reset_allows_only_corrected_payload(client, rebuild, monkeypatch):
    base, device, _, state, _, _ = rebuild
    endpoint = lambda action: base + action + '?device_id=' + device
    monkeypatch.setattr(raid_rebuild, 'reset_blockers', lambda: [])
    monkeypatch.setattr(raid_rebuild, 'boot_blockers', lambda: [])
    monkeypatch.setattr(raid_rebuild, 'read_boot_action', lambda s: '/reset')
    monkeypatch.setattr(raid_rebuild, 'start_server', lambda *a: {'status': 'waiting', 'message': 'Waiting'})
    review = client.post(endpoint('preview'), json={'operation': 'reset'}).json()
    assert client.post(endpoint('apply'), json=confirmation(review)).status_code == 200
    boot = client.post(endpoint('boot-preview')).json()
    assert client.post(endpoint('boot'), json=boot_confirmation(boot)).status_code == 200
    state['current']['@Redfish.Settings'] = {'Time': datetime.now(UTC).isoformat(), 'Messages': [
        {'MessageId': 'SmartStorageMessages.2.0.1.PropertyKeyMissing', 'MessageArgs': ['LogicalDrives']},
        {'MessageId': 'SmartStorageMessages.2.0.1.Success'}]}
    state['pending'] = deepcopy(state['current'])
    result = client.post(endpoint('verify')).json()
    assert result['status'] == 'failed' and not result['verified']
    assert 'missing LogicalDrives' in result['message']
    assert client.get(endpoint('status')).json()['status'] == 'failed'
    review = client.post(endpoint('preview'), json={'operation': 'reset'}).json()
    assert review['apply_enabled'], review
    assert review['payload'] == {'Actions': [{'Action': 'FactoryReset'}], 'DataGuard': 'Disabled', 'LogicalDrives': []}
    assert len(state['writes']) == 1
    assert client.post(endpoint('apply'), json=confirmation(review)).status_code == 200
    boot = client.post(endpoint('boot-preview')).json()
    assert client.post(endpoint('boot'), json=boot_confirmation(boot)).status_code == 200
    state['current']['@Redfish.Settings']['Time'] = datetime.now(UTC).isoformat()
    state['pending'] = deepcopy(state['current'])
    assert client.post(endpoint('verify')).json()['status'] == 'failed'
    review = client.post(endpoint('preview'), json={'operation': 'reset'}).json()
    assert not review['apply_enabled']
    assert any('Repeating the same request' in b for b in review['blockers'])


def test_shutdown_cycle_requires_confirmed_intervening_boot(client, rebuild, monkeypatch, db_session):
    from types import SimpleNamespace
    base, device, _, state, _, _ = rebuild
    endpoint = base + 'shutdown-preview?device_id=' + device
    state['power'] = 'On'
    monkeypatch.setattr(raid_rebuild, 'current_lab_action_policy', lambda: SimpleNamespace(action_blockers=lambda *a: []))
    monkeypatch.setattr(raid_rebuild, 'shutdown_action', lambda *a: ('/reset', {'ResetType': 'PushPowerButton'}))
    raid_rebuild.audit(db_session, 'test', 'kit.raid_rebuild.shutdown_attempt', 'test',
                       {'device_id': device, 'identity': state['identity'], 'force': False})
    db_session.commit()
    assert not client.post(endpoint, json={'force': False}).json()['apply_enabled']
    raid_rebuild.audit(db_session, 'test', 'kit.raid_rebuild.boot_attempt', 'test',
                       {'device_id': device, 'identity': state['identity'], 'attempt_id': 'fixture'})
    db_session.commit()
    assert not client.post(endpoint, json={'force': False}).json()['apply_enabled']
    raid_rebuild.audit(db_session, 'test', 'kit.raid_rebuild.boot_result', 'test',
                       {'device_id': device, 'attempt_id': 'fixture', 'status': 'waiting'})
    db_session.commit()
    assert client.post(endpoint, json={'force': False}).json()['apply_enabled']


def test_durable_boot_status_confirmation_and_no_replay(client, staged_boot):
    endpoint, state = staged_boot
    status = client.get(endpoint('status')).json()
    assert status['status'] == 'staged' and status['active']
    review = client.post(endpoint('boot-preview')).json()
    assert review['apply_enabled'] and state['power_writes'] == []
    bad = boot_confirmation(review); bad['confirmation'] = 'yes'
    assert client.post(endpoint('boot'), json=bad).status_code == 422
    bad = boot_confirmation(review); bad['data_loss_confirmed'] = False
    assert client.post(endpoint('boot'), json=bad).status_code == 422
    assert client.post(endpoint('boot'), json=boot_confirmation(review)).status_code == 200
    assert client.get(endpoint('status')).json()['boot_started_at']
    assert client.get(endpoint('status')).json()['status'] == 'waiting'
    assert client.post(endpoint('boot'), json=boot_confirmation(review)).status_code == 409
    assert client.post(endpoint('boot-preview')).status_code == 409
    assert len(state['power_writes']) == 1
    state['current'] = {'LogicalDrives':[], '@Redfish.Settings':{'Messages':[{'MessageId':'Base.1.0.Success'}]}}
    state['pending'] = deepcopy(state['current'])
    assert client.post(endpoint('verify')).json()['verified']
    assert client.get(endpoint('status')).json()['status'] == 'verified'
    assert not client.get(endpoint('status')).json()['active']


@pytest.mark.parametrize('change', ['power', 'identity', 'pending', 'policy', 'expired', 'extra_setting'])
def test_boot_rechecks_every_guard(client, staged_boot, monkeypatch, change):
    endpoint, state = staged_boot
    review = client.post(endpoint('boot-preview')).json()
    if change == 'power': state['power'] = 'On'
    elif change == 'identity': state['identity'] = 'other'
    elif change == 'pending': state['pending']['LogicalDrives'] = state['current']['LogicalDrives']
    elif change == 'extra_setting': state['pending']['UnreviewedSetting'] = True
    elif change == 'policy': monkeypatch.setattr(raid_rebuild, 'boot_blockers', lambda: ['Power disabled'])
    else:
        from datetime import timedelta
        class Future(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(tz) + timedelta(minutes=10)
        monkeypatch.setattr(raid_rebuild, 'datetime', Future)
    assert client.post(endpoint('boot'), json=boot_confirmation(review)).status_code == 409
    assert state['power_writes'] == []


def test_power_timeout_is_durable_and_never_retried(client, staged_boot, monkeypatch):
    endpoint, state = staged_boot
    def uncertain(snapshot, path):
        state['power_writes'].append(path)
        return {'status':'uncertain','message':'Power response lost. Do not retry.'}
    monkeypatch.setattr(raid_rebuild, 'start_server', uncertain)
    review = client.post(endpoint('boot-preview')).json()
    assert client.post(endpoint('boot'), json=boot_confirmation(review)).json()['status'] == 'uncertain'
    assert 'lost' in client.get(endpoint('status')).json()['message']
    assert client.post(endpoint('boot'), json=boot_confirmation(review)).status_code == 409
    assert len(state['power_writes']) == 1


@pytest.mark.parametrize('bad', ['actions', 'guard', 'on', 'identity'])
def test_boot_preview_rejects_unmatched_pending_state(client, staged_boot, bad):
    endpoint, state = staged_boot
    if bad == 'actions': state['pending']['Actions'] = []
    elif bad == 'guard': state['pending']['DataGuard'] = 'Strict'
    elif bad == 'on': state['power'] = 'On'
    else: state['identity'] = 'other'
    assert client.post(endpoint('boot-preview')).status_code == 409
    assert state['power_writes'] == []


@pytest.mark.parametrize('target,values,power,allowed', [
    ('/redfish/v1/Systems/1/Actions/ComputerSystem.Reset/', ['On'], 'Off', True),
    ('https://elsewhere.invalid/reset', ['On'], 'Off', False),
    ('/redfish/v1/Systems/2/Actions/ComputerSystem.Reset/', ['On'], 'Off', False),
    ('/redfish/v1/Systems/1/Actions/ComputerSystem.Reset/', ['ForceRestart'], 'Off', False),
    ('/redfish/v1/Systems/1/Actions/ComputerSystem.Reset/', ['On'], 'On', False),
])
def test_only_advertised_same_system_power_on_is_supported(monkeypatch, target, values, power, allowed):
    import httpx
    from types import SimpleNamespace
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'PowerState':power,'Actions':{'#ComputerSystem.Reset':{
            'target':target,'ResetType@Redfish.AllowableValues':values}}})
    monkeypatch.setattr(provider, 'client_for', lambda c: httpx.Client(transport=httpx.MockTransport(handler)))
    snapshot = {'config':SimpleNamespace(host='192.0.2.10'),'path':'/redfish/v1/Systems/1/SmartStorageConfig/Settings/'}
    if allowed: assert provider.read_boot_action(snapshot) == target
    else:
        with pytest.raises(provider.StorageRebuildError): provider.read_boot_action(snapshot)
    assert len(calls) == 1 and calls[0].method == 'GET'


def test_provider_power_timeout_sends_only_one_on_request(monkeypatch):
    import httpx
    import json
    from types import SimpleNamespace
    calls = []
    def handler(request):
        calls.append(request)
        assert json.loads(request.content) == {'ResetType':'On'}
        raise httpx.ReadTimeout('fixture response lost', request=request)
    monkeypatch.setattr(provider, 'client_for', lambda c: httpx.Client(transport=httpx.MockTransport(handler)))
    result = provider.start_server({'config':SimpleNamespace(host='192.0.2.10')}, '/redfish/v1/Systems/1/Actions/ComputerSystem.Reset/')
    assert result['status'] == 'uncertain' and len(calls) == 1


def test_diagnosis_endpoint_is_read_only_and_device_scoped(client, rebuild, monkeypatch):
    base, device, probe, state, _, _ = rebuild
    monkeypatch.setattr(raid_rebuild, 'read_diagnostic_log', lambda s: {'entries':[], 'complete':False,'message':'Fixture log unavailable'})
    response=client.post(base+'diagnose?device_id='+device)
    assert response.status_code==200, response.text
    assert response.json()['repair_available'] is False
    assert state['writes']==[]
    assert client.post(base+'diagnose?device_id=other').status_code==404


def _event(session, kind, data, minutes_ago):
    event = raid_rebuild.audit(session, "fixture", "kit.raid_rebuild." + kind, kind, {"device_id": "dev", "profile_id": "kit", **data})
    event.created_at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    session.flush()
    return event


@pytest.mark.parametrize("later_verified", [True, False])
def test_an_old_failure_superseded_by_a_later_verified_write_does_not_block(db_session, later_verified):
    # Observed live 2026-09-29: a 09-22 reset failure, then a verified reset; the iLO 3.19 upgrade later
    # changed the manager identity, which made that superseded failure block every new RAID write.
    old = _event(db_session, "attempt", {"operation": "reset", "identity": "before-ilo-upgrade"}, 300)
    _event(db_session, "failed", {"attempt_id": old.id}, 290)
    if later_verified:
        newer = _event(db_session, "attempt", {"operation": "reset", "identity": "before-ilo-upgrade"}, 200)
        _event(db_session, "verified", {"attempt_id": newer.id, "operation": "reset"}, 190)
    snapshot = {"identity": "after-ilo-upgrade", "pending_differs": False, "current": {}}
    result = raid_rebuild.unresolved_attempt(db_session, "dev", snapshot, "fixture")
    if later_verified:
        assert result is None
    else:
        assert result == "Target changed or new pending settings exist after the recorded failure. Diagnose before another write."


def test_a_finished_shutdown_cycle_does_not_block_a_new_one(client, rebuild, monkeypatch, db_session):
    # 09-24: shutdown, boot, verified sanitize; then an iLO update changed the manager identity.
    from types import SimpleNamespace
    base, device, _, state, _, _ = rebuild
    state["power"] = "On"
    monkeypatch.setattr(raid_rebuild, "current_lab_action_policy", lambda: SimpleNamespace(action_blockers=lambda *a: []))
    monkeypatch.setattr(raid_rebuild, "shutdown_action", lambda s, force: ("/reset", {"ResetType": "PushPowerButton"}))
    def event(kind, data, minutes_ago):
        e = raid_rebuild.audit(db_session, "fixture", "kit.raid_rebuild." + kind, kind, {"device_id": device, "profile_id": "kit", **data})
        e.created_at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    event("shutdown_attempt", {"force": False, "identity": "before-ilo-upgrade"}, 300)
    event("boot_attempt", {"identity": "before-ilo-upgrade"}, 290)
    event("verified", {"attempt_id": "old", "operation": "sanitize"}, 280)
    db_session.commit()
    review = client.post(base + "shutdown-preview?device_id=" + device, json={"force": False}).json()
    assert review["apply_enabled"], review["blockers"]
