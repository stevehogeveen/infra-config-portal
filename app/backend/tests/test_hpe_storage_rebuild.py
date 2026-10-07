from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest

from app.providers import hpe_storage_rebuild as module
from app.providers.ilo_redfish import IloRedfishConfig


@pytest.fixture
def transport(monkeypatch):
    config=IloRedfishConfig('192.0.2.10','fixture-user','fixture-secret',True,10,device_id='device-a')
    current={'@odata.type':'#SmartStorageConfig.v2_0_0.SmartStorageConfig','Location':'Slot 0','LogicalDrives':[],
             '@Redfish.Settings':{'SettingsObject':{'@odata.id':'/redfish/v1/Systems/1/SmartStorageConfig/Settings/'}}}
    state={'current':current,'pending':deepcopy(current),'etag':'"exact-version"','writes':[], 'gets':[], 'status':200,'body':{'error':{'@Message.ExtendedInfo':[{'MessageId':'iLO.2.0.SystemResetRequired'}]}}}
    probe={'storage':{'controllers':[{'Model':'Fixture SR controller','Location':'Slot 0'}]},
           'systems':[{'@odata.id':'/redfish/v1/Systems/1/','PowerState':'Off'}]}
    monkeypatch.setattr(module,'current_lab_action_policy',lambda:SimpleNamespace(readonly_blockers=lambda:[]))
    monkeypatch.setattr(module,'ilo_config_for_device',lambda s,d:config)
    monkeypatch.setattr(module,'IloRedfishAdapter',lambda **kw:SimpleNamespace(probe=lambda:probe))
    def identity(host,*,scope):
        assert host=='192.0.2.10' and scope=='device-a'
        return SimpleNamespace(identity_fingerprint_sha256='identity'),[]
    monkeypatch.setattr(module,'resolve_ilo_write_target_context',identity)
    def handle(request):
        assert request.url.host=='192.0.2.10'
        if request.method=='GET':
            state['gets'].append(str(request.url))
            settings=request.url.path.endswith('/Settings/')
            headers={'etag':state['etag']} if state['etag'] else {}
            return httpx.Response(200,json=state['pending'] if settings else state['current'],headers=headers)
        assert request.method=='PUT'
        state['writes'].append(request)
        if state.get('timeout'):raise httpx.ReadTimeout('fixture timeout')
        return httpx.Response(state['status'],json=state['body'])
    monkeypatch.setattr(module,'client_for',lambda c:httpx.Client(transport=httpx.MockTransport(handle)))
    return state,probe


def test_preview_only_reads_and_stage_uses_exact_etag_without_reboot(transport):
    state,probe=transport
    snapshot=module.read_snapshot(None,'device-a')
    assert len(state['gets'])==2 and not state['writes']
    result=module.stage_configuration(snapshot,{'DataGuard':'Disabled','LogicalDrives':[]})
    assert result['status']=='pending'
    assert len(state['writes'])==1
    assert state['writes'][0].headers['If-Match']=='"exact-version"'
    assert state['writes'][0].url.path.endswith('/SmartStorageConfig/Settings/')


@pytest.mark.parametrize('fault',['etag','location','endpoint','schema','membership'])
def test_unverified_capabilities_refuse_writes(transport,fault):
    state,probe=transport
    if fault=='etag':state['etag']=None
    elif fault=='location':state['current']['Location']='Slot 1'
    elif fault=='endpoint':state['current']['@Redfish.Settings']['SettingsObject']['@odata.id']='https://elsewhere.invalid/settings'
    elif fault=='schema':state['current']['@odata.type']='#Storage.v1_0_0.Storage'
    else:state['current']['LogicalDrives']=[{'DataDrives':{'DataDriveCount':2}}]
    with pytest.raises(module.StorageRebuildError):module.read_snapshot(None,'device-a')
    assert not state['writes']
    assert all('192.0.2.10' in url for url in state['gets'])


@pytest.mark.parametrize('fault',['timeout','http','semantic'])
def test_uncertain_writes_are_never_retried(transport,fault):
    state,probe=transport
    snapshot=module.read_snapshot(None,'device-a')
    if fault=='timeout':state['timeout']=True
    elif fault=='http':state['status']=412
    else:state['body']={'error':{'@Message.ExtendedInfo':[{'MessageId':'HpeSmartStorageConfig.1.0.InvalidDrive'}]}}
    assert module.stage_configuration(snapshot,{'LogicalDrives':[]})['status']=='uncertain'
    assert len(state['writes'])==1
