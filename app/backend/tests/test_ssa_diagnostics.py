import json
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.automation import ssa_diagnostics as ssa
from app.automation.targets import AutomationBlocked


def test_enrollment_is_exact_and_revision_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(ssa, 'ROOT', tmp_path)
    device = str(uuid4())
    with pytest.raises(AutomationBlocked):
        ssa.load_target(device)
    directory = tmp_path / device
    directory.mkdir()
    (directory / 'target.json').write_text(json.dumps({'host':'192.0.2.20','username':'root'}))
    (directory / 'ssh_key').write_text('fixture-only-key')
    (directory / 'known_hosts').write_text('fixture-only-host-key')
    first = ssa.load_target(device)
    assert first[0].host == '192.0.2.20'
    (directory / 'known_hosts').write_text('different-fixture-key')
    assert ssa.load_target(device)[3] != first[3]
    with pytest.raises(AutomationBlocked):
        ssa.load_target('../escape')


@pytest.mark.parametrize('value', ['-oProxyCommand=bad', '{{ lookup("pipe", "bad") }}', '192.0.2.1;bad'])
def test_inventory_address_cannot_inject_options(value):
    with pytest.raises(ValueError):
        ssa.MaintenanceTarget(host=value, username='root')


@pytest.mark.parametrize('failure', ['none', 'runner', 'identity', 'partial', 'oversize'])
def test_runner_requires_complete_identity_bound_evidence(monkeypatch, failure):
    def run(**kwargs):
        host = kwargs['inventory']['all']['hosts']['maintenance']
        assert 'StrictHostKeyChecking=yes' in host['ansible_ssh_common_args']
        assert kwargs['extravars'] == {'expected_serial':'FIXTURE-SERIAL'}
        assert kwargs['playbook'] == 'playbooks/ssa_diagnostics.yml'
        reports = ['Controller Status: OK', 'Fixture configuration']
        if failure == 'partial': reports.pop()
        if failure == 'oversize': reports[0] = 'x' * 65537
        kwargs['event_handler']({'event':'runner_on_ok','event_data':{
            'task':'Export SSA diagnostics','res':{'ansible_stats':{'data':{
                'identity_verified':failure != 'identity','reports':reports}}}}})
        return SimpleNamespace(rc=1 if failure == 'runner' else 0, status='successful')
    monkeypatch.setitem(sys.modules, 'ansible_runner', SimpleNamespace(run=run))
    target = ssa.MaintenanceTarget(host='192.0.2.20', username='root')
    if failure == 'none':
        assert len(ssa.run_ssa(target,b'fixture',b'fixture','FIXTURE-SERIAL')) == 2
    else:
        with pytest.raises(AutomationBlocked):
            ssa.run_ssa(target,b'fixture',b'fixture','FIXTURE-SERIAL')


def test_missing_serial_prevents_runner(monkeypatch):
    monkeypatch.setitem(sys.modules, 'ansible_runner', SimpleNamespace())
    with pytest.raises(AutomationBlocked):
        ssa.run_ssa(ssa.MaintenanceTarget(host='192.0.2.20', username='root'), b'x', b'x', '')


def test_api_mock_mode_does_not_queue(client):
    response = client.post('/api/v1/devices/' + str(uuid4()) + '/maintenance-diagnostics')
    assert response.status_code in {404,409}
