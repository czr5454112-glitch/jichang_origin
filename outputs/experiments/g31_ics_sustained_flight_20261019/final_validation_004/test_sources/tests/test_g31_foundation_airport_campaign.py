"""Full input preparation and fake-endpoint continuation tests, never native."""
import copy
import gzip
import json
import math

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_campaign as campaign
from scripts.experiments.g31_ics_circulation import foundation_airport_protocol as protocol


def test_ast_closure_resolves_delayed_relative_child_and_initializer_imports(tmp_path):
    files = {'pkg/__init__.py': 'from . import init_dependency\n',
        'pkg/main.py': 'import pkg.child\ndef later():\n    from .sub import late\n',
        'pkg/child.py': 'from pkg import leaf\n', 'pkg/leaf.py': '', 'pkg/init_dependency.py': '',
        'pkg/sub/__init__.py': '', 'pkg/sub/late.py': 'from .. import leaf\n',
        'pkg/unrelated.py': 'raise RuntimeError("never import files to discover them")\n'}
    for name, text in files.items():
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
    before = campaign.source_dependency_closure(root=tmp_path, roots=('pkg.main',))
    assert set(before) == {'pkg', 'pkg.main', 'pkg.child', 'pkg.leaf', 'pkg.init_dependency', 'pkg.sub', 'pkg.sub.late'}
    (tmp_path / 'pkg/unrelated.py').write_text('this is deliberately not valid Python and is unrelated')
    assert campaign.source_dependency_closure(root=tmp_path, roots=('pkg.main',)) == before


def test_actual_airport_source_graph_is_closed_and_contains_runtime_branches():
    graph = campaign.source_dependency_closure()
    for module, path in graph.items():
        for target in campaign._import_names(module, path):
            dependency = campaign._local_module(target, campaign.ROOT)
            assert dependency is None or target in graph
    for name in ('foundation_flight_forecaster', 'native027_run_acceptance', 'protocol_control',
                 'original_workload', 'run_original_protocol', 'foundation_airport_protocol'):
        assert 'scripts.experiments.g31_ics_circulation.' + name in graph
    assert 'scripts.eval.run_g4irsf31_nanning_workload' in graph
    assert 'czr005.io.legacy_tasks' in graph
    assert 'scripts.experiments.g31_ics_circulation.foundation_action_value' not in graph


def test_full_input_exactly_reuses_registered_n4_s4_t2_and_all_jobs():
    data, manifest, crosswalk = campaign.build_full_input()
    assert len(data['jobs']) == len(crosswalk) == 28506
    assert manifest['input_sha256'] == campaign.PHYSICAL_INPUT_SHA
    assert len(data['trays']) == 22 and manifest['proxy_contract']['storage_berths'] == 4
    assert data['owner_protocol']['enabled']
    assert data['options']['max_simulation_time'] == 86400.
    assert not any(job.get('allow_suffix_reroute') for job in data['jobs'])
    assert campaign.segment_targets()[-4:] == list(campaign.BOUNDARIES)


def test_planner_hook_keeps_protocol_submit_and_default_configuration(monkeypatch):
    class Session:
        physical_time = 0.
        def advance_to(self, target, **kwargs):
            self.physical_time = target
            return {'status': 'reached', 'horizon_complete': True}
        def result_at(self, target):
            return {'advance': {'status': 'reached', 'horizon_complete': True}}
        def protocol_demand_signature(self, owner):
            return 'same'
    class Client:
        submitted = []
        def __init__(self, session, **kwargs):
            self.state = {'outbox': {}}; self.calls = []
        def refresh(self):
            return []
        def _policy_view(self, owner, **kwargs):
            return {'owner_id': owner, 'now': 0., 'sent': len(self.submitted)}
        def submit(self, owner, kind, payload):
            self.submitted.append((owner, kind, payload))
            return 'real-client-request', {'status': 'pending'}
    monkeypatch.setattr(protocol, 'ProtocolClient', Client)
    monkeypatch.setattr(protocol, '_publish_services', lambda *args, **kwargs: [])
    monkeypatch.setattr(protocol, 'transfer_candidates', lambda *args, **kwargs: {'intents': []})
    ordinary = protocol.run_airport_protocol_control(Session(), ['A'], horizon=0.)
    assert 'planner_identity' not in ordinary['controller_state']['config']
    observed = []
    def planner(observation, **kwargs):
        observed.append(observation)
        return {'intents': [{'tray_id': 'empty'}] if observation['sent'] == 0 else []}
    run = protocol.run_airport_protocol_control(Session(), ['A'], horizon=0., planner=planner, planner_identity='frozen-v1')
    assert Client.submitted == [('A', 'transfer', {'tray_id': 'empty'})]
    assert len(observed) == 2 and observed[-1]['sent'] == 1
    assert run['controller_state']['config']['planner_identity'] == 'frozen-v1'
    with pytest.raises(ValueError, match='state_configuration_mismatch'):
        protocol.run_airport_protocol_control(Session(), ['A'], horizon=0., state=run['controller_state'])
    with pytest.raises(ValueError, match='explicit_planner_identity'):
        protocol.run_airport_protocol_control(Session(), ['A'], horizon=0., planner=planner)


def test_continuous_windows_keep_one_session_and_previous_controller_state(tmp_path, monkeypatch):
    from scripts.experiments.g31_ics_circulation import original_workload
    monkeypatch.setattr(original_workload, 'summarize_execution', lambda data, result: {'offered': len(result['jobs'])})
    class Session:
        physical_time = 0.
        def offline_state_sha256(self):
            return 'warmup-with-backlog-and-inflight'
        def observe_protocol(self, owner):
            return {'now': self.physical_time}
    session = Session(); seen = []
    def controller(actual, owners, *, horizon, state, **kwargs):
        assert actual is session
        assert state is None if not seen else state['next'] == len(seen)
        seen.append(horizon); actual.physical_time = horizon
        return {'status': 'reached', 'controller_state': {'next': len(seen), 'backlog': 'retained'},
            'client_calls': [], 'result': {'jobs': [{'business_bag_id': 'unfinished'}]}}
    data = {'jobs': [{}], 'node_contracts': [{'resource_owner': 'A'}]}
    plan = {'soft_stop_seconds': 120, 'controller': campaign.CONTROLLER, 'protocol_input_semantic_sha256': 'full'}
    raw = campaign.execute_continuous(session, data, plan, tmp_path, controller=controller, clock=lambda: 0.)
    assert seen == campaign.segment_targets()
    assert raw['status'] == 'requested_calibration_end_reached'
    assert raw['session_instance_count'] == 1 and raw['physical_reset_count'] == 0
    assert raw['warmup_native_state_sha256'] == 'warmup-with-backlog-and-inflight'
    assert raw['final_result']['jobs'] == [{'business_bag_id': 'unfinished'}]


def test_event_budget_cut_never_calls_result_at_or_resets(tmp_path, monkeypatch):
    class Session:
        physical_time = 0.
        def observe_protocol(self, owner):
            return {'now': self.physical_time}
        def result_at(self, target):
            raise AssertionError('must not advance past partial timestamp')
    def controller(*args, **kwargs):
        return {'status': 'budget_exhausted', 'controller_state': {'control_boundary_complete': False},
            'client_calls': [], 'result': None}
    raw = campaign.execute_continuous(Session(), {'jobs': [{}, {}], 'node_contracts': [{'resource_owner': 'A'}]},
        {'soft_stop_seconds': 120, 'controller': campaign.CONTROLLER, 'protocol_input_semantic_sha256': 'full'},
        tmp_path, controller=controller, clock=lambda: 0.)
    assert raw['status'] == 'native_event_budget_censored' and len(raw['segments']) == 1
    assert raw['offered_count'] == 2 and raw['final_result'] is None


def paired():
    return {'input_sha256': 'same', 'warmup_native_state_sha256': 'same_native_prefix',
        'status': 'requested_calibration_end_reached',
        'final_physical_time': 60000., 'offered_count': 3, 'final_result': {'physical_clock': 60000., 'jobs': [
            {'business_bag_id': name, 'status': 'completed', 'completed_at': 100.} for name in ('a', 'b', 'c')]}}


def test_all_job_pair_one_ulp_harm_and_unfinished_cannot_be_hidden():
    before = paired(); after = copy.deepcopy(before)
    after['final_result']['jobs'][0]['completed_at'] = 90.
    after['final_result']['jobs'][1]['completed_at'] = math.nextafter(100., math.inf)
    after['final_result']['jobs'][2].update(status='waiting_for_tray', completed_at=-1.)
    assessed = campaign.compare_all_jobs(before, after)
    assert assessed['counts'] == {'improved': 1, 'harmed': 1, 'unknown_incomplete': 1}
    assert not assessed['strict_all_job_nonharm'] and not assessed['strict_improvement']
    assert assessed['uncompleted_jobs_excluded'] == 0 and assessed['comparison_tolerance_s'] == 0.


@pytest.mark.parametrize('field,value', [('input_sha256', 'other'), ('warmup_native_state_sha256', None),
                                        ('final_physical_time', 60001.)])
def test_pair_rejects_changed_flow_reset_prefix_or_observation_clock(field, value):
    before = paired(); after = copy.deepcopy(before); after[field] = value
    with pytest.raises(ValueError):
        campaign.compare_all_jobs(before, after)
