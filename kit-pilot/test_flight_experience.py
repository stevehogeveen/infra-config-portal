"""Outcome, scope, event and approval tests; simulated kit only."""
import threading
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
import chaos
from engine import Engine
from flight_log import completion, report_legs, timeline_section, unknowns
from pilot import Pilot
from test_pilot import lab, make_pilot, wait  # noqa: F401  (lab is a pytest fixture)


def test_results_preserve_requests_and_distinguish_choice():
    kit = chaos.FakeKit()
    engine = Engine(chaos.ChaosApi(kit, {}, threading.Event()), chaos.P, chaos.SERVERS, chaos.SWITCHES, clock=lambda _: None, skip={'acceptance'})
    results = []
    engine.fly(0, lambda i, r: results.append(dict(id=engine.legs[i].id, title=engine.legs[i].title, **r)))
    assert results[-1]['reason'] == 'skipped_by_choice'
    assert 'Windows proof was skipped' in completion(results)
    assert report_legs(results)[-1]['state'] == 'omitted'
    assert not any('acceptance/start' in name for name, _ in kit.writes)


def test_absent_devices_are_not_applicable():
    kit = chaos.FakeKit()
    engine = Engine(chaos.ChaosApi(kit, {}, threading.Event()), chaos.P, [], [], clock=lambda _: None)
    results = []
    engine.fly(0, lambda i, r: results.append(r))
    assert all(r['reason'] == 'not_applicable' for r in results if r['state'] != 'running')
    assert not kit.writes


def test_progress_dedup_and_report_escaping():
    p = Pilot(None)
    with p.lock:
        p.event('progress', '<reading>')
        stamp = p.state['last_progress']
        p.event('progress', '<reading>')
    assert len(p.state['events']) == 1
    assert p.state['last_progress'] == stamp
    assert '&lt;reading&gt;' in timeline_section({}, [], p.state)
    assert p.state['events'][0]['elapsed'] == 0


def test_unknowns_are_plan_qualified_and_scope_aware():
    result = unknowns({'server': {'id':'s', 'esxi':{'addressing':'dhcp'}}, 'switch':{'id':'w','setup':{'mode':'dhcp'}}}, {'items':[]}, {'skip':['acceptance']})
    assert any('after ESXi' in x for x in result)
    assert any('switch address arrives from DHCP' in x for x in result)
    assert any('skipped by choice' in x for x in result)
    assert not any('live checked' in x for x in result)


def test_flight_report_and_already_verified(lab, tmp_path, monkeypatch):
    p = make_pilot(lab, tmp_path, monkeypatch)
    p.check(); p.state['options']['skip'] = ['acceptance']; p.ask_approval(); p.approve()
    state = wait(p, 'done')
    assert state['legs'][1]['reason'] == 'already_verified'
    assert state['legs'][-1]['note'] == 'skipped by choice'
    assert 'Windows proof was skipped' in state['message']
    report = Path(state['report']).read_text(encoding='utf-8')
    assert 'Flight log' in report and 'skipped by choice' in report
    assert 'Prove it works · already done' not in report
    assert any(e['kind'] == 'leg_start' for e in state['events'])
    assert all('at' in e and 'elapsed' in e for e in state['events'])

def test_check_observer_does_not_change_request_sequence():
    from flight_log import CheckedApi
    def run(observe):
        kit = chaos.FakeKit()
        api = chaos.ChaosApi(kit, {}, threading.Event())
        checked = []
        engine = Engine(CheckedApi(api, lambda: checked.append(True)) if observe else api, chaos.P, chaos.SERVERS, chaos.SWITCHES, clock=lambda _: None)
        engine.fly(0, lambda *_: None)
        return api.n, kit.writes, checked
    plain = run(False)
    watched = run(True)
    assert watched[:2] == plain[:2]
    assert watched[2]

def test_stop_and_continue_events(lab, tmp_path, monkeypatch):
    lab.volumes = True
    p = make_pilot(lab, tmp_path, monkeypatch)
    p.check(); p.ask_approval(); p.approve()
    wait(p, 'needs_you')
    assert any(e['kind'] == 'needs_you' for e in p.state['events'])
    lab.volumes = False
    p.resume(); wait(p, 'done')
    assert any(e['kind'] == 'continue' for e in p.state['events'])


def test_pause_request_is_timestamped():
    p = Pilot(None)
    p.state['phase'] = 'flying'
    p.pause()
    assert p.stop.is_set()
    assert p.state['events'][-1]['kind'] == 'pause'
    assert p.state['events'][-1]['at']
