"""C3 internal read-only snapshot reuse; public view isolation is unchanged."""
from copy import deepcopy
import json
import os

import pytest

from scripts.experiments.g31_ics_circulation.analytic_control import transfer_candidates
from scripts.experiments.g31_ics_circulation.event_protocol_control import run_event_protocol_control
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle
from scripts.experiments.g31_ics_circulation.protocol_control import ProtocolClient, _publish_services


@pytest.fixture(scope='module')
def native():
    return load_native(os.environ['G31_CIRCULATION_BINARY'])


def scene(protocol=None):
    data=tiny_cycle();data['transfers']=[]
    for job in data['jobs']:
        job['allow_suffix_reroute']=True
    data['owner_protocol']={'enabled':True,'timeout':.2,'ack_delay':0.,**(protocol or {})}
    data['owner_notifications']={'enabled':True}
    return data


OPTIONS=dict(control_period=1.,command_delay=0.,publication_delay=0.,retry_period=.5)


def calls(run):
    return [{k:v for k,v in c.items() if k!='submit_compute_ms'} for c in run['client_calls']]


@pytest.mark.parametrize('protocol',[{}, {'drop_ack_packets':2},
    {'duplicate_acks':True,'duplicate_ack_delay':0.},
    {'owner_outages':[{'owner':'B','start':.2,'end':12.}]}])
@pytest.mark.parametrize('compact',[True,False])
def test_reuse_and_fresh_views_preserve_requests_physics_and_checkpoint(native,protocol,compact):
    a,b=native.NativeSession(scene(protocol)),native.NativeSession(scene(protocol))
    reused=run_event_protocol_control(a,['A','B'],horizon=30.,compact=compact,**OPTIONS)
    fresh=run_event_protocol_control(b,['A','B'],horizon=30.,compact=compact,
        _reuse_service_observation=False,**OPTIONS)
    assert calls(reused)==calls(fresh)
    assert reused['controller_state']==fresh['controller_state']
    assert a.offline_state_sha256()==b.offline_state_sha256()
    assert not any(r['observation_reused'] for r in fresh['control_records'])
    assert any(r['observation_reused'] for r in reused['control_records'])==compact
    for row in reused['control_records']:
        if any(action['kind']!='route_not_proposed' for action in row['service_actions']):
            assert not row['observation_reused']


def test_both_snapshot_consumers_leave_nested_observation_unchanged(native):
    data=scene();data['jobs'][0]['load_seconds']=30.
    session=native.NativeSession(data);session.advance_to(0.)
    client=ProtocolClient(session)
    snapshot=client.view('A');before=deepcopy(snapshot)
    _publish_services(client,'A',{'routes':{},'forecasts':{}},command_delay=0.,
        publication_delay=0.,routes=True,forecasts=True,lease_seconds=5.,observation=snapshot)
    transfer_candidates(snapshot,predictive=True,message_delay=0.,respect_service_forecasts=True)
    assert snapshot==before
    other=client.view('A')
    snapshot['node_contracts'][0]['capacity']=-999
    snapshot['trays'][0]['committed_prefix'].append(-999)
    assert other['node_contracts'][0]['capacity']!=-999
    assert -999 not in other['trays'][0]['committed_prefix']


def test_json_resume_can_switch_reuse_flag_without_policy_state_change(native):
    data=scene({'drop_ack_packets':1})
    continuous=native.NativeSession(data)
    full=run_event_protocol_control(continuous,['A','B'],horizon=30.,**OPTIONS)
    split=native.NativeSession(data)
    prefix=run_event_protocol_control(split,['A','B'],horizon=7.37,
        _reuse_service_observation=False,**OPTIONS)
    state=json.loads(json.dumps(prefix['controller_state']))
    fork=split.fork()
    resumed=run_event_protocol_control(fork,['A','B'],horizon=30.,state=state,**OPTIONS)
    assert calls(prefix)+calls(resumed)==calls(full)
    assert resumed['controller_state']==full['controller_state']
    assert fork.offline_state_sha256()==continuous.offline_state_sha256()


def test_rejected_submission_still_prevents_internal_snapshot_reuse(native):
    class RejectFirstForecast:
        def __init__(self, session):
            self.session, self.rejected = session, False
        def __getattr__(self, name):
            return getattr(self.session, name)
        def submit_protocol_command(self, payload):
            if payload['kind'] == 'service_forecast' and not self.rejected:
                self.rejected = True
                return {'status': 'rejected', 'reason': 'test_injected_submission_rejection'}
            return self.session.submit_protocol_command(payload)
    data=scene();data['jobs'][0]['load_seconds']=30.
    session=RejectFirstForecast(native.NativeSession(data))
    run=run_event_protocol_control(session,['A','B'],horizon=.5,**OPTIONS)
    rejected=[row for row in run['control_records'] if any(
        action.get('reply',{}).get('status')=='rejected' for action in row['service_actions'])]
    assert rejected and all(not row['observation_reused'] for row in rejected)


def test_budget_cut_and_resume_with_reuse_matches_uninterrupted_fresh(native):
    data=scene({'drop_ack_packets':1})
    original=native.NativeSession(data)
    full=run_event_protocol_control(original,['A','B'],horizon=30.,
        _reuse_service_observation=False,**OPTIONS)
    session=native.NativeSession(data);state=None;combined=[]
    for _ in range(2000):
        piece=run_event_protocol_control(session,['A','B'],horizon=30.,state=state,
            event_budget=1,max_activations=1,**OPTIONS)
        combined.extend(calls(piece));state=json.loads(json.dumps(piece['controller_state']))
        if piece['status']=='reached':break
        session=session.fork()
    else:
        pytest.fail('budget continuation did not converge')
    assert combined==calls(full)
    assert state==full['controller_state']
    assert session.offline_state_sha256()==original.offline_state_sha256()
