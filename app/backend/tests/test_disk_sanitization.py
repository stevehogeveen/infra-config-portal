from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.api import raid_rebuild
from app.services import disk_sanitization as service
from test_raid_rebuild import rebuild, confirmation, boot_confirmation


@pytest.fixture
def sanitize(client, rebuild, monkeypatch):
    base, device, probe, state, _, _ = rebuild
    state['config'] = SimpleNamespace(host='192.0.2.10')
    probe['storage']['controllers'][0].update(FirmwareVersion='1.0', Status={'Health':'OK'})
    probe['storage']['physical_drives'].pop()
    for i, d in enumerate(probe['storage']['physical_drives']):
        d.update(FirmwareVersion='1.0', hardware_identity_fingerprint_sha256=f'identity-{i}', DiskDriveUse='Unconfigured')
    controller = probe['storage']['controllers'][0]
    approvals = [{'server_identity': state['identity'], 'controller_model':controller['Model'],
                  'controller_firmware':'1.0', 'drive_identity':d['hardware_identity_fingerprint_sha256'],
                  'drive_model':d['Model'], 'drive_firmware':'1.0', 'method':'SanitizeRestrictedOverwrite',
                  'source':'Vendor support fixture', 'reviewed_by':'test',
                  'expires_at':(datetime.now(UTC)+timedelta(days=1)).isoformat()} for d in probe['storage']['physical_drives']]
    monkeypatch.setattr(service, 'read_json_object', lambda p: {'approvals':approvals})
    monkeypatch.setattr(service, 'policy_blockers', lambda d, session=None: [])
    original = raid_rebuild.stage_configuration
    monkeypatch.setattr(raid_rebuild, 'stage_configuration', lambda s,p,**k: original(s,p))
    monkeypatch.setattr(raid_rebuild, 'boot_blockers', lambda: [])
    monkeypatch.setattr(raid_rebuild, 'read_boot_action', lambda s: '/reset')
    monkeypatch.setattr(raid_rebuild, 'start_server', lambda *a: {'status':'waiting','message':'Starting'})
    return (lambda a:base+a+'?device_id='+device), probe, state, approvals


def empty(probe, state):
    state['current'] = {'LogicalDrives':[]}
    state['pending'] = deepcopy(state['current'])
    probe['storage']['logical_drives'] = []


def rejected_fixture(client, sanitize):
    endpoint, probe, state, approvals = sanitize
    empty(probe, state)
    for approval in approvals:
        approval['method'] = 'OnePass'
    review = client.post(endpoint('preview'), json={'operation':'sanitize', 'erase_pattern':'OnePass'}).json()
    assert client.post(endpoint('apply'), json={**confirmation(review), 'physical_erase_confirmed':True}).status_code == 200
    boot = client.post(endpoint('boot-preview')).json()
    assert client.post(endpoint('boot'), json=boot_confirmation(boot)).status_code == 200
    state['current']['@Redfish.Settings'] = {'Time':datetime.now(UTC).isoformat(), 'Messages':[
        {'MessageId':'SmartStorageMessages.2.0.1.PropertyValueEnumNotInList',
         'MessageArgs':['ErasePattern','OnePass'], 'RelatedProperties':['#/Actions/0/ErasePattern']},
        {'MessageId':'SmartStorageMessages.2.0.1.Success'}]}
    state['pending'] = deepcopy(state['current'])
    for drive in probe['storage']['physical_drives']:
        drive.update(ErasePattern=None, EraseCompletionPercentage=None, DiskDriveStatusReasons=['None'])
    return endpoint, probe, state, approvals


def test_confirmed_method_rejection_allows_new_method_not_replay(client, sanitize, monkeypatch):
    endpoint, probe, state, approvals = rejected_fixture(client, sanitize)
    result = client.post(endpoint('verify')).json()
    assert result['status'] == 'failed' and not result['verified']
    status = client.get(endpoint('status')).json()
    assert not status['active'] and status['erase_recovery']['rejected_method'] == 'OnePass'
    same = client.post(endpoint('preview'), json={'operation':'sanitize','erase_pattern':'OnePass'}).json()
    assert not same['apply_enabled']
    assert not next(o for o in same['erase_options']['options'] if o['id']=='OnePass')['selectable']
    assert client.post(endpoint('apply'), json={**confirmation(same),'physical_erase_confirmed':True}).status_code == 409
    for approval in approvals:
        approval['method'] = 'SanitizeRestrictedOverwrite'
    retry = client.post(endpoint('preview'), json={'operation':'sanitize'}).json()
    assert retry['apply_enabled'], retry['blockers']
    assert client.post(endpoint('apply'), json={**confirmation(retry),'physical_erase_confirmed':True}).status_code == 200
    assert client.post(endpoint('apply'), json={**confirmation(retry),'physical_erase_confirmed':True}).status_code == 409
    assert len(state['writes']) == 2


def test_shutdown_after_rejection_requires_same_idle_disks(client, sanitize, monkeypatch):
    endpoint, probe, state, _ = rejected_fixture(client, sanitize)
    assert client.post(endpoint('verify')).json()['status'] == 'failed'
    state['power'] = 'On'
    monkeypatch.setattr(raid_rebuild, 'current_lab_action_policy', lambda: SimpleNamespace(action_blockers=lambda *a: []))
    monkeypatch.setattr(raid_rebuild, 'shutdown_action', lambda s, f: ('/reset', {'ResetType':'PushPowerButton'}))
    review = client.post(endpoint('shutdown-preview'), json={'force':False}).json()
    assert review['apply_enabled'], review
    probe['storage']['physical_drives'][0].update(DiskDriveStatusReasons=['EraseInProgress'], ErasePattern='OnePass')
    blocked = client.post(endpoint('shutdown-preview'), json={'force':False}).json()
    assert not blocked['apply_enabled']
    assert any('active or queued' in b for b in blocked['blockers'])
    assert len(state['writes']) == 1


def legacy_wipe(client, sanitize):
    endpoint, probe, state, _ = sanitize
    empty(probe, state)
    state['current']['@odata.type'] = '#SmartStorageConfig.v2_0_0.SmartStorageConfig'
    state['pending'] = deepcopy(state['current'])
    for drive in probe['storage']['physical_drives']:
        drive['DiskDriveStatusReasons'] = ['None']
    review = client.post(endpoint('preview'), json={'operation':'sanitize'}).json()
    assert client.post(endpoint('apply'), json={**confirmation(review),'physical_erase_confirmed':True}).status_code == 200
    boot = client.post(endpoint('boot-preview')).json()
    assert client.post(endpoint('boot'), json=boot_confirmation(boot)).status_code == 200
    state['current']['@Redfish.Settings'] = {'Time':datetime.now(UTC).isoformat(),
        'Messages':[{'MessageId':'SmartStorageMessages.2.0.1.Success'}]}
    state['pending'] = deepcopy(state['current'])
    for drive in probe['storage']['physical_drives']:
        drive['DiskDriveStatusReasons'] = ['EraseInProgress']
    return endpoint, probe, state


def test_legacy_ilo_without_method_echo_tracks_transition_not_assumed_percentage(client, sanitize):
    endpoint, probe, state = legacy_wipe(client, sanitize)
    result = client.post(endpoint('verify')).json()
    assert all(d['status']=='erasing' and d['observed_active'] and d['percent'] is None for d in result['drives'])
    assert all('accepted wipe request' in d['progress_note'] for d in result['drives'])
    for drive in probe['storage']['physical_drives']:
        drive['DiskDriveStatusReasons'] = ['None']
    assert not client.post(endpoint('verify')).json()['verified']
    for drive in probe['storage']['physical_drives']:
        drive['DiskDriveStatusReasons'] = ['EraseCompleted']
    assert client.post(endpoint('verify')).json()['verified']
    assert len(state['writes']) == 1


@pytest.mark.parametrize('fault',['old_settings','error','pending','wrong_method','old_completion','wrong_schema','missing_inventory'])
def test_legacy_method_association_needs_fresh_success_and_observed_activity(client, sanitize, fault):
    endpoint, probe, state = legacy_wipe(client, sanitize)
    if fault=='old_settings': state['current']['@Redfish.Settings']['Time']='2000-01-01T00:00:00+00:00'
    if fault=='error': state['current']['@Redfish.Settings']['Messages']=[{'MessageId':'Base.1.0.GeneralError'}]
    if fault=='pending': state['pending']['Actions']=[{'Action':'PhysicalDriveErase'}]
    if fault=='wrong_method':
        for drive in probe['storage']['physical_drives']: drive['ErasePattern']='OnePass'
    if fault=='old_completion':
        for drive in probe['storage']['physical_drives']: drive['DiskDriveStatusReasons']=['EraseCompleted']
    if fault=='wrong_schema': state['current']['@odata.type']='#Unknown.v1'
    if fault=='missing_inventory': probe['storage']['physical_drives'].pop()
    result=client.post(endpoint('verify')).json()
    assert not result['verified'] and not any(d['observed_active'] for d in result['drives'])
    assert len(state['writes']) == 1


@pytest.mark.parametrize('fault', ['stale','future','wrong_value','wrong_property','missing_args','extra_error',
    'active','queued','previous_activity','completed','missing_reason','missing_disk','pending','arrays','identity','firmware'])
def test_ambiguous_erase_failure_cannot_enable_retry(client, sanitize, fault):
    endpoint, probe, state, approvals = rejected_fixture(client, sanitize)
    settings = state['current']['@Redfish.Settings']
    disk = probe['storage']['physical_drives'][0]
    if fault == 'stale': settings['Time'] = '2000-01-01T00:00:00+00:00'
    if fault == 'future': settings['Time'] = (datetime.now(UTC)+timedelta(days=1)).isoformat()
    if fault == 'wrong_value': settings['Messages'][0]['MessageArgs'][1] = 'Other'
    if fault == 'wrong_property': settings['Messages'][0]['RelatedProperties'] = ['#/LogicalDrives']
    if fault == 'missing_args': settings['Messages'][0].pop('MessageArgs')
    if fault == 'extra_error': settings['Messages'].append({'MessageId':'Base.1.0.GeneralError'})
    if fault in {'active','queued','previous_activity','completed'}:
        disk.update(ErasePattern='OnePass', DiskDriveStatusReasons=['QueuedForErase' if fault=='queued' else 'EraseCompleted' if fault=='completed' else 'EraseInProgress'])
    if fault == 'previous_activity':
        client.post(endpoint('verify'))
        disk.update(ErasePattern=None, DiskDriveStatusReasons=['None'])
    if fault == 'missing_reason': disk['DiskDriveStatusReasons'] = []
    if fault == 'missing_disk': probe['storage']['physical_drives'].pop()
    if fault == 'pending': state['pending']['Actions'] = [{'Action':'PhysicalDriveErase'}]
    if fault == 'arrays': state['current']['LogicalDrives'] = [{'DataDrives':['1I:1:1']}]
    if fault == 'identity': state['identity'] = 'different-server'
    if fault == 'firmware': disk['FirmwareVersion'] = 'changed'
    result = client.post(endpoint('verify')).json()
    assert result['status'] != 'failed' and not result['verified']
    status = client.get(endpoint('status')).json()
    assert status['active'] and not status['erase_recovery']
    assert len(state['writes']) == 1


def test_sanitization_lifecycle_needs_every_disk_proof(client, sanitize):
    endpoint, probe, state, _ = sanitize
    review = client.post(endpoint('preview'),json={'operation':'sanitize'}).json()
    assert not review['apply_enabled'] and any('Delete the existing' in b for b in review['blockers'])
    assert not state['writes']
    empty(probe,state)
    review = client.post(endpoint('preview'),json={'operation':'sanitize'}).json()
    assert review['apply_enabled'], review
    assert len(review['drives']) == 6 and review['method'] == 'PATCH'
    assert review['payload']['Actions'][0]['PhysicalDriveList'] == [f'1I:1:{i}' for i in range(1,7)]
    body = confirmation(review)
    assert client.post(endpoint('apply'),json=body).status_code == 422
    body['physical_erase_confirmed'] = True
    assert client.post(endpoint('apply'),json=body).status_code == 200
    staged = client.get(endpoint('status')).json()
    assert staged['sanitization'] is None
    assert len(staged['erase_scope']) == 6
    assert all(d['erase_pattern'] == 'SanitizeRestrictedOverwrite' for d in staged['erase_scope'])
    assert client.post(endpoint('apply'),json=body).status_code == 409
    assert not client.post(endpoint('preview'),json={'operation':'create'}).json()['apply_enabled']
    boot = client.post(endpoint('boot-preview')).json()
    assert client.post(endpoint('boot'),json=boot_confirmation(boot)).status_code == 200
    state['current']['@Redfish.Settings'] = {'Time':datetime.now(UTC).isoformat(), 'Messages':[{'MessageId':'Base.1.0.Success'}]}
    state['pending'] = deepcopy(state['current'])
    for d in probe['storage']['physical_drives']:
        d.update(ErasePattern='SanitizeRestrictedOverwrite',DiskDriveStatusReasons=['EraseCompleted'])
    assert not client.post(endpoint('verify')).json()['verified']  # old completion is not proof
    for d in probe['storage']['physical_drives']:
        d.update(DiskDriveStatusReasons=['EraseInProgress'],EraseCompletionPercentage=25)
    progress = client.post(endpoint('verify')).json()
    assert all(d['status']=='erasing' and d['percent']==25 for d in progress['drives'])
    assert progress['power'] == state['power'] and 'pending_changes' in progress
    assert all('percentage reported' in d['progress_note'] for d in progress['drives'])
    for d in probe['storage']['physical_drives'][:-1]:
        d['DiskDriveStatusReasons'] = ['EraseCompleted']
    assert not client.post(endpoint('verify')).json()['verified']
    probe['storage']['physical_drives'][-1]['DiskDriveStatusReasons'] = ['EraseCompleted']
    assert client.post(endpoint('verify')).json()['verified']
    report = client.get(endpoint('sanitization-report')).json()
    assert report['status']=='verified' and report['verified_at'] and len(report['last_check']['drives'])==6
    assert len(state['writes']) == 1


def test_progress_does_not_invent_percentage_or_hide_controller_rejection(client, sanitize):
    endpoint, probe, state, _ = sanitize
    empty(probe, state)
    review = client.post(endpoint('preview'), json={'operation':'sanitize'}).json()
    assert client.post(endpoint('apply'), json={**confirmation(review), 'physical_erase_confirmed':True}).status_code == 200
    boot = client.post(endpoint('boot-preview')).json()
    assert client.post(endpoint('boot'), json=boot_confirmation(boot)).status_code == 200
    state['power'] = 'On'
    state['current']['@Redfish.Settings'] = {'Time':datetime.now(UTC).isoformat(), 'Messages':[{'MessageId':'SmartStorageMessages.2.0.1.PropertyValueEnumNotInList'}]}
    state['pending'] = deepcopy(state['current'])
    result = client.post(endpoint('verify')).json()
    assert result['status'] == 'needs_attention' and not result['verified']
    assert result['power'] == 'On'
    assert all(d['percent'] is None and 'rejected an erase setting' in d['progress_note'] for d in result['drives'])
    disk = probe['storage']['physical_drives'][0]
    disk.update(ErasePattern='SanitizeRestrictedOverwrite', DiskDriveStatusReasons=['EraseInProgress'])
    for percent in (None, True, False, '25', -1, 101, float('nan'), float('inf')):
        disk['EraseCompletionPercentage'] = percent
        result = client.post(endpoint('verify')).json()
        assert result['drives'][0]['status'] == 'erasing'
        assert result['drives'][0]['percent'] is None
        assert 'does not report a percentage' in result['drives'][0]['progress_note']
    for percent in (0, 25, 100):
        disk['EraseCompletionPercentage'] = percent
        result = client.post(endpoint('verify')).json()
        assert result['drives'][0]['percent'] == percent and not result['verified']
    assert len(state['writes']) == 1


@pytest.mark.parametrize('fault',['missing_identity','missing_drive','unapproved','expired','firmware','duplicate_bay','spare','unknown_health','power','warnings'])
def test_preview_fails_closed(client,sanitize,fault):
    endpoint,probe,state,approvals=sanitize
    empty(probe,state)
    d=probe['storage']['physical_drives'][0]
    if fault=='missing_identity':d.pop('hardware_identity_fingerprint_sha256')
    if fault=='missing_drive':probe['storage']['physical_drives']=[]
    if fault=='unapproved':approvals.clear()
    if fault=='expired':approvals[0]['expires_at']='2000-01-01T00:00:00+00:00'
    if fault=='firmware':d['FirmwareVersion']='2.0'
    if fault=='duplicate_bay':d['Location']=probe['storage']['physical_drives'][1]['Location']
    if fault=='spare':d['DiskDriveUse']='Spare'
    if fault=='unknown_health':d['Status']={}
    if fault=='power':state['power']='On'
    if fault=='warnings':probe['storage']['warnings']=['incomplete']
    r=client.post(endpoint('preview'),json={'operation':'sanitize'}).json()
    assert not r['apply_enabled'],r
    assert not state['writes']


def test_policy_not_enabled_by_raid_permissions(monkeypatch):
    monkeypatch.delenv('HPE_SANITIZE_DEVICE_IDS',raising=False)
    assert service.policy_blockers('fixture')


def test_raw_disks_remain_blocked_after_array_deletion(client, sanitize):
    endpoint, probe, state, approvals = sanitize
    empty(probe, state)
    for drive in probe['storage']['physical_drives']:
        drive['DiskDriveUse'] = 'Raw'
    approvals.clear()
    review = client.post(endpoint('preview'), json={'operation':'sanitize'}).json()
    assert not review['apply_enabled'] and not state['writes']
    assert len(review['preparation']['raw_bays']) == 6
    assert len(review['preparation']['support_review_bays']) == 6
    assert review['preparation']['assigned_bays'] == []
    assert not review['raw_preparation']['assignment_verified']
    assert all(any('preparation checks' in b for b in d['blockers']) for d in review['drives'])


def mixed_raw(sanitize):
    endpoint, probe, state, approvals = sanitize
    empty(probe, state)
    controller = probe['storage']['controllers'][0]
    controller.update(Model='HPE Smart Array P408i-a SR Gen10', CurrentOperatingMode='Mixed')
    for approval in approvals:
        approval['controller_model'] = controller['Model']
    for drive in probe['storage']['physical_drives']:
        drive['DiskDriveUse'] = 'Raw'
    state['current'].update({
        '@odata.type':'#SmartStorageConfig.v2_0_0.SmartStorageConfig',
        'PhysicalDrives':[{'Location': d['Location']} for d in probe['storage']['physical_drives']],
        'Ports':[{'PortIndex':0, 'OperatingModeAfterReboot':'Mixed'},
                 {'PortIndex':1, 'OperatingModeAfterReboot':'Mixed'}]})
    state['pending'] = deepcopy(state['current'])
    return endpoint, probe, state, approvals


def test_mixed_raw_disks_use_existing_guarded_sanitize_without_mode_write(client, sanitize):
    endpoint, probe, state, approvals = mixed_raw(sanitize)
    state['power'] = 'On'
    review = client.post(endpoint('preview'), json={'operation':'sanitize'}).json()
    assert review['raw_preparation']['assignment_verified']
    assert not review['apply_enabled'] and any('Shut down' in b for b in review['blockers'])
    assert not state['writes']
    state['power'] = 'Off'
    review = client.post(endpoint('preview'), json={'operation':'sanitize'}).json()
    assert review['apply_enabled'], review['blockers']
    assert all(not d['blockers'] and d['role'] == 'Raw' for d in review['drives'])
    assert not state['writes']
    body = {**confirmation(review), 'physical_erase_confirmed':True}
    assert client.post(endpoint('apply'), json={**body,'confirmation':'wrong'}).status_code == 422
    assert not state['writes']
    assert client.post(endpoint('apply'), json=body).status_code == 200
    assert client.post(endpoint('apply'), json=body).status_code == 409
    assert len(state['writes']) == 1
    payload = state['writes'][0]
    assert set(payload) == {'DataGuard','LogicalDrives','Actions'}
    assert payload['Actions'] == [{'Action':'PhysicalDriveErase','ErasePattern':'SanitizeRestrictedOverwrite',
                                  'PhysicalDriveList':[f'1I:1:{i}' for i in range(1,7)]}]
    boot = client.post(endpoint('boot-preview')).json()
    assert boot['apply_enabled'], boot
    assert client.post(endpoint('boot'), json=boot_confirmation(boot)).status_code == 200


@pytest.mark.parametrize('fault', [
    'hba','unknown_mode','different_family','wrong_schema','missing_bays','duplicate_bay',
    'different_bay','missing_ports','changing_ports','changing_controller_mode',
    'inventory_volume','current_volume','spare','data','missing_approval','pending_action',
])
def test_raw_preparation_never_bypasses_real_requirements(client, sanitize, fault):
    endpoint, probe, state, approvals = mixed_raw(sanitize)
    controller = probe['storage']['controllers'][0]
    if fault == 'hba': controller['CurrentOperatingMode'] = 'HBA'
    if fault == 'unknown_mode': controller.pop('CurrentOperatingMode')
    if fault == 'different_family': controller['Model'] = 'HPE MR fixture'
    if fault == 'wrong_schema': state['current']['@odata.type'] = '#Unknown.v1'
    if fault == 'missing_bays': state['current'].pop('PhysicalDrives')
    if fault == 'duplicate_bay': state['current']['PhysicalDrives'][1] = state['current']['PhysicalDrives'][0]
    if fault == 'different_bay': state['current']['PhysicalDrives'][0]['Location'] = '9I:1:9'
    if fault == 'missing_ports': state['current'].pop('Ports')
    if fault == 'changing_ports': state['pending']['Ports'][0]['OperatingModeAfterReboot'] = 'RAID'
    if fault == 'changing_controller_mode': controller['OperatingModeAfterReboot'] = 'HBA'
    if fault == 'inventory_volume': probe['storage']['logical_drives'] = [{'Id':'new-volume'}]
    if fault == 'current_volume': state['current']['LogicalDrives'] = [{'DataDrives':['1I:1:1']}]
    if fault == 'spare': probe['storage']['physical_drives'][0]['DiskDriveUse'] = 'Spare'
    if fault == 'data': probe['storage']['physical_drives'][0]['DiskDriveUse'] = 'Data'
    if fault == 'missing_approval': approvals.clear()
    if fault == 'pending_action': state['pending']['Actions'] = [{'Action':'FactoryReset'}]
    review = client.post(endpoint('preview'), json={'operation':'sanitize'}).json()
    assert not review['apply_enabled'], review
    assert client.post(endpoint('apply'), json={**confirmation(review),'physical_erase_confirmed':True}).status_code == 409
    assert not state['writes']


def test_raw_preparation_is_rechecked_before_apply_and_boot(client, sanitize):
    endpoint, probe, state, _ = mixed_raw(sanitize)
    review = client.post(endpoint('preview'), json={'operation':'sanitize'}).json()
    state['current']['Ports'][0]['PortIndex'] = 2
    state['pending']['Ports'][0]['PortIndex'] = 2
    body = {**confirmation(review),'physical_erase_confirmed':True}
    assert client.post(endpoint('apply'), json=body).status_code == 409
    assert not state['writes']
    review = client.post(endpoint('preview'), json={'operation':'sanitize'}).json()
    assert client.post(endpoint('apply'), json={**confirmation(review),'physical_erase_confirmed':True}).status_code == 200
    probe['storage']['controllers'][0]['CurrentOperatingMode'] = 'HBA'
    boot = client.post(endpoint('boot-preview')).json()
    assert not boot['apply_enabled'] and any('Raw-drive preparation changed' in b for b in boot['blockers'])


def test_provider_keeps_current_and_pending_controller_modes_separate():
    from app.providers.ilo_redfish import _storage_controller_summary
    result = _storage_controller_summary({'Model':'HPE Smart Array P408i-a SR Gen10',
        'CurrentOperatingMode':'Mixed', 'OperatingModeAfterReboot':'HBA'})
    assert result['CurrentOperatingMode'] == 'Mixed'
    assert result['OperatingModeAfterReboot'] == 'HBA'


def test_selected_one_pass_needs_its_own_approval(client, sanitize):
    endpoint, probe, state, approvals = mixed_raw(sanitize)
    review = client.post(endpoint('preview'), json={'operation':'sanitize','erase_pattern':'OnePass'}).json()
    assert review['erase_options']['options'][1]['selectable']
    assert not review['apply_enabled']
    assert all(d['erase_pattern']=='OnePass' for d in review['drives'])
    for a in approvals:
        a['method']='OnePass'
    review = client.post(endpoint('preview'), json={'operation':'sanitize','erase_pattern':'OnePass'}).json()
    assert review['apply_enabled'] and 'not a purge' in review['assurance']
    assert client.post(endpoint('preview'), json={'operation':'sanitize','erase_pattern':'CryptoErase'}).status_code == 422
    assert not state['writes']


def test_mixed_media_methods_and_completion(client, sanitize):
    endpoint, probe, state, approvals = sanitize
    empty(probe, state)
    disks = probe['storage']['physical_drives']
    disks[-1]['MediaType'] = 'SSD'
    approvals[-1]['method'] = 'SanitizeRestrictedBlockErase'
    review = client.post(endpoint('preview'), json={'operation':'sanitize'}).json()
    assert review['apply_enabled'], review
    assert review['erase_pattern'] == 'auto'
    assert review['payload']['Actions'] == [
        {'Action':'PhysicalDriveErase', 'ErasePattern':'SanitizeRestrictedOverwrite',
         'PhysicalDriveList':[d['Location'] for d in disks[:-1]]},
        {'Action':'PhysicalDriveErase', 'ErasePattern':'SanitizeRestrictedBlockErase',
         'PhysicalDriveList':[disks[-1]['Location']]}]
    assert client.post(endpoint('apply'), json={**confirmation(review), 'physical_erase_confirmed':True}).status_code == 200
    boot = client.post(endpoint('boot-preview')).json()
    assert client.post(endpoint('boot'), json=boot_confirmation(boot)).status_code == 200
    state['current']['@Redfish.Settings'] = {'Time':datetime.now(UTC).isoformat(), 'Messages':[{'MessageId':'Base.1.0.Success'}]}
    state['pending'] = deepcopy(state['current'])
    for disk in disks:
        disk.update(ErasePattern='SanitizeRestrictedOverwrite', DiskDriveStatusReasons=['EraseInProgress'])
    progress = client.post(endpoint('verify')).json()
    assert progress['drives'][-1]['status'] == 'unverified'
    disks[-1]['ErasePattern'] = 'SanitizeRestrictedBlockErase'
    progress = client.post(endpoint('verify')).json()
    assert all(d['status'] == 'erasing' for d in progress['drives'])
    for disk in disks:
        disk['DiskDriveStatusReasons'] = ['EraseCompleted']
    assert client.post(endpoint('verify')).json()['verified']
    report = client.get(endpoint('sanitization-report')).json()
    assert report['drive_methods'][disks[-1]['hardware_identity_fingerprint_sha256']] == 'SanitizeRestrictedBlockErase'
    assert len(state['writes']) == 1


@pytest.mark.parametrize('media,method', [('HDD','SanitizeRestrictedBlockErase'),
    ('SSD','SanitizeRestrictedOverwrite'), ('SSD','OnePass'), ('Unknown','auto'), ('SMR','auto')])
def test_wrong_or_unknown_media_blocks(client, sanitize, media, method):
    endpoint, probe, state, _ = sanitize
    empty(probe, state)
    probe['storage']['physical_drives'][0]['MediaType'] = media
    review = client.post(endpoint('preview'), json={'operation':'sanitize', 'erase_pattern':method}).json()
    assert not review['apply_enabled']
    assert any('media type' in b or 'does not match' in b for b in review['drives'][0]['blockers'])
    assert not state['writes']


def test_media_change_invalidates_review(client, sanitize):
    endpoint, probe, state, _ = sanitize
    empty(probe, state)
    review = client.post(endpoint('preview'), json={'operation':'sanitize'}).json()
    probe['storage']['physical_drives'][0]['MediaType'] = 'SSD'
    assert client.post(endpoint('apply'), json={**confirmation(review), 'physical_erase_confirmed':True}).status_code == 409
    assert not state['writes']


def test_scope_change_never_completes():
    expected={'path':'/drive/1','bay':'1','identity':'a','model':'disk','firmware':'1','capacity_bytes':1,'media':'HDD'}
    snap={'identity':'server','probe':{'storage':{'physical_drives':[]}},'current':{'LogicalDrives':[]},'pending_differs':False}
    result=service.verify(snap,{'identity':'server','drive_scope':[expected],'erase_pattern':'OnePass'},None,datetime.now(UTC))
    assert not result['verified'] and result['status']=='needs_attention'


def test_provider_patch_is_conditional_and_never_retries(monkeypatch):
    import httpx
    from app.providers import hpe_storage_rebuild as provider
    calls=[]
    def send(request):
        calls.append(request)
        raise httpx.ReadTimeout('fixture',request=request)
    monkeypatch.setattr(provider,'client_for',lambda c:httpx.Client(transport=httpx.MockTransport(send)))
    result=provider.stage_configuration({'config':SimpleNamespace(host='192.0.2.10'),
        'path':'/redfish/v1/systems/1/smartstorageconfig/settings/','etag':'"exact"'},
        {'DataGuard':'Disabled','LogicalDrives':[],'Actions':[{'Action':'PhysicalDriveErase','ErasePattern':'SanitizeRestrictedOverwrite','PhysicalDriveList':['1I:1:1']}]},sanitize=True)
    assert result['status']=='uncertain'
    assert len(calls)==1 and calls[0].method=='PATCH' and calls[0].headers['If-Match']=='"exact"'


def test_capability_change_between_preview_and_apply_sends_nothing(client,sanitize):
    endpoint,probe,state,approvals=sanitize
    empty(probe,state)
    review=client.post(endpoint('preview'),json={'operation':'sanitize'}).json()
    approvals[0]['source']='Different vendor review'
    body={**confirmation(review),'physical_erase_confirmed':True}
    assert client.post(endpoint('apply'),json=body).status_code==409
    assert not state['writes']


def test_in_app_authorization_preserves_hardware_guards(client, sanitize):
    endpoint, probe, state, approvals = sanitize
    approvals.clear()
    state['power'] = 'On'
    probe['storage']['physical_drives'][0]['DiskDriveUse'] = 'Data'
    review = client.post(endpoint('preview'), json={'operation':'sanitize'}).json()
    body = {'preview_id':review['preview_id'], 'confirmation':'AUTHORIZE ERASURE '+review['name'],
            'vendor_support_reviewed':True,
            'sources':{d['identity']:'Vendor support case fixture: exact disk and firmware reviewed' for d in review['drives']}}
    invalid = {**body, 'confirmation':'wrong'}
    assert client.post(endpoint('sanitize-authorization'), json=invalid).status_code == 422
    assert client.post(endpoint('sanitize-authorization'), json={**body,'sources':{}}).status_code == 422
    result = client.post(endpoint('sanitize-authorization'), json=body)
    assert result.status_code == 200, result.text
    fresh = client.post(endpoint('preview'), json={'operation':'sanitize'}).json()
    assert fresh['authorization_expires_at']
    assert not any('support has not been reviewed' in b for b in fresh['blockers'])
    assert any('Shut down' in b for b in fresh['blockers'])
    assert any('Delete the existing' in b for b in fresh['blockers'])
    assert any('unconfigured' in b for b in fresh['blockers'])
    assert not fresh['apply_enabled'] and not state['writes']


def test_authorization_rejects_changed_hardware(client, sanitize):
    endpoint, probe, state, _ = sanitize
    review = client.post(endpoint('preview'), json={'operation':'sanitize'}).json()
    probe['storage']['physical_drives'][0]['FirmwareVersion'] = 'new firmware'
    body = {'preview_id':review['preview_id'], 'confirmation':'AUTHORIZE ERASURE '+review['name'],
            'vendor_support_reviewed':True, 'sources':{d['identity']:'Vendor support fixture' for d in review['drives']}}
    assert client.post(endpoint('sanitize-authorization'), json=body).status_code == 409
    assert not state['writes']


def test_enrollment_never_enables_mock_or_readonly(monkeypatch):
    from dataclasses import replace
    from app.providers.action_policy import current_lab_action_policy
    policy = current_lab_action_policy()
    monkeypatch.setattr(service, 'enrollment', lambda session, device: {'identity':'fixture'})
    for mode in ('mock', 'local-readonly'):
        monkeypatch.setattr(service, 'current_lab_action_policy', lambda: replace(policy, provider_mode=mode))
        assert service.policy_blockers('fixture')
