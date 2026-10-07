from app.services.storage_diagnostics import diagnose_storage
from app.providers.ilo_redfish import _resource_summary


def test_battery_health_uses_explicit_system_evidence():
    for health in ['OK', 'Warning', 'Critical']:
        system = _resource_summary({'Oem': {'Hpe': {'AggregateHealthStatus': {
            'SmartStorageBattery': {'Status': {'Health': health}}}}}})
        s = snapshot()
        s['probe']['systems'] = [system]
        result = diagnose_storage(s, {'entries': [], 'complete': True, 'message': 'Read'})
        assert result['battery_health'] == health + ' (reported by iLO system health)'
        assert any(f['id'] == 'storage-battery' for f in result['findings']) == (health != 'OK')


def snapshot():
    return {'probe':{'storage':{'controllers':[{'Model':'Fixture controller','Status':{'Health':'Warning'},'BackupPowerSourceStatus':'Present'}],
        'physical_drives':[{'Location':'1I:1:1','Model':'Fixture','CapacityBytes':300000000000,'Status':{'Health':'OK'}}]}},
        'current':{'LogicalDrives':[{'Raid':'Raid1','DataDrives':['1I:1:1','Unknown:0:Unknown'],'SpareDrives':['1I:1:2']}],
        '@Redfish.Settings':{'Messages':[{'MessageId':'SmartStorageMessages.2.0.1.CanCreateEditableConfigControllerStatusNotOK'}]}},'pending_differs':False}


def test_diagnosis_separates_current_failure_from_cache_history():
    log={'entries':[{'message':'1795 Write-back cache mismatch','created':'2020-01-01T00:00:00Z','repaired':True}], 'complete':True,'message':'History only'}
    result=diagnose_storage(snapshot(), log)
    findings={f['id']:f for f in result['findings']}
    assert result['status']=='needs_attention' and not result['repair_available']
    assert result['healthy_drives']==1
    assert findings['missing-members']['evidence']==['Unknown:0:Unknown']
    assert findings['cache']['source']=='Historical IML evidence'
    assert 'alone cannot prove' in findings['cache']['detail']
    assert result['battery_health']=='Not determined from backup-power presence'


def test_healthy_controller_does_not_make_missing_member_safe():
    s=snapshot();s['probe']['storage']['controllers'][0]['Status']['Health']='OK';s['current']['@Redfish.Settings']['Messages']=[]
    assert diagnose_storage(s,{'entries':[],'complete':False,'message':'Access denied'})['status']=='needs_attention'


def test_empty_controller_with_no_current_fault_does_not_claim_repair_authorization():
    s=snapshot();s['probe']['storage']['controllers'][0]['Status']['Health']='OK';s['current']={'LogicalDrives':[]}
    r=diagnose_storage(s,{'entries':[],'complete':False,'message':'Access denied'})
    assert r['status']=='no_current_storage_blocker' and not r['log_complete']
    assert 'not approval' in r['summary']
    s['pending_differs']=True
    assert diagnose_storage(s,{'entries':[],'complete':True,'message':'History'})['status']=='needs_attention'
