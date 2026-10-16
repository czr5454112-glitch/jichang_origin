"""Exact supplied-input guards and one-request isolation; no NativeSession."""
from copy import deepcopy
import json
from types import MappingProxyType
import pytest
from scripts.experiments.g31_ics_circulation import public_preference_request_context as candidate

original = candidate.original


def bundle(index=0):
    case = original.contract.domain.cases()[index]
    value = original.contract.domain.make_bundle(case)
    static = original.contract.supported_contract(); static.pop('native_semantics')
    value.update(status='conditional_model_input', model_version=original.contract.VERSION, contract=static)
    for key, tray in value['trays'].items():
        ready = 0. if key == 'E' else .1 if key == 'L' else case['blocker_load']
        tray.update(reception_node=-1, tray_id=key, generation=0 if key == 'E' else 1, traversal_id=0,
            committed_prefix=[tray['node']], service_ready_known=True, service_ready_at=ready,
            ready_kind='empty_available_at' if key == 'E' else 'observed_load_completion',
            load_complete_at=-1. if key == 'E' else ready, available_at=ready if key == 'P' else 0.)
    for job in value['jobs'].values():
        job.update(protected_service=True, storage_entered_at=-1., storage_released_at=-1.)
    value['jobs']['loaded']['status'] = 'in_transit'
    value['resources'] = {node['node']: {'node': node['node'],
        'occupancy': sum(t['node'] == node['node'] for t in value['trays'].values()),
        'actual_available': int(node['node'] == 5)} for node in static['node_contracts']}
    return value


def ordered(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


@pytest.mark.parametrize('index', range(6))
def test_all_six_cases_all32_complete_ordered_outputs_exact(index):
    supplied = bundle(index); context = candidate.RequestContext(supplied)
    actions = context.actions()
    assert len(actions) == 32
    for action in actions:
        expected = original.predict(supplied, action)
        assert expected['status'] == 'conditional_prediction'
        assert ordered(context.predict(action)) == ordered(expected)


@pytest.mark.parametrize('defect', ['status','static','pending','resource_missing','resource_alias','resource_bool',
    'resource_wrong_id','occupancy','stock','trays','generation','prefix','moving','unknown_ready','ready_kind',
    'available','load_end_bool','job_bool','service_epoch','protected','job_missing'])
def test_every_guard_still_returns_exact_original_unknown(defect):
    value = bundle(); action = candidate.RequestContext(value).actions()[0]
    if defect == 'status': value['status'] = 'unknown'
    elif defect == 'static': value['contract']['node_contracts'][0]['capacity'] += 1
    elif defect == 'pending': value['owner_pending_tray_requests'] = ['request']
    elif defect == 'resource_missing': value['resources'].pop(9)
    elif defect == 'resource_alias': value['resources']['0'] = deepcopy(value['resources'][0])
    elif defect == 'resource_bool': value['resources'][0]['occupancy'] = True
    elif defect == 'resource_wrong_id': value['resources'][0]['node'] = 1
    elif defect == 'occupancy': value['resources'][3]['occupancy'] = 1
    elif defect == 'stock': value['resources'][5]['actual_available'] = 0
    elif defect == 'trays': value['trays'].pop('E')
    elif defect == 'generation': value['trays']['L']['generation'] = False
    elif defect == 'prefix': value['trays']['L']['committed_prefix'] = [0, 1, 0]
    elif defect == 'moving': value['trays']['E']['edge_to'] = 1
    elif defect == 'unknown_ready': value['trays']['P']['service_ready_known'] = False
    elif defect == 'ready_kind': value['trays']['L']['ready_kind'] = 'empty_available_at'
    elif defect == 'available': value['trays']['E']['available_at'] = 90.
    elif defect == 'load_end_bool': value['trays']['P']['load_end'] = True
    elif defect == 'job_bool': value['jobs']['loaded']['arrival'] = False
    elif defect == 'service_epoch': value['jobs']['loaded']['loaded_at'] = .2
    elif defect == 'protected': value['jobs']['receiver']['protected_service'] = False
    else: value['jobs'].pop('receiver')
    expected = original.predict(value, action)
    assert expected['status'].startswith('unknown')
    assert ordered(candidate.RequestContext(value).predict(action)) == ordered(expected)


@pytest.mark.parametrize('defect', ['bool','nan','inf','extra','missing','initial','later','window','none'])
def test_action_vocabulary_is_checked_on_every_candidate(defect):
    value = bundle(); context = candidate.RequestContext(value); action = context.actions()[0]
    if defect == 'bool': action['return_delay'] = False
    elif defect == 'nan': action['empty_departure'] = float('nan')
    elif defect == 'inf': action['return_delay'] = float('inf')
    elif defect == 'extra': action['extra'] = 1
    elif defect == 'missing': action.pop('later_action')
    elif defect == 'initial': action['initial_action'] = 'forced_1'
    elif defect == 'later': action['later_action'] = 'forced_3'
    elif defect == 'window': action['empty_departure'] += .0001
    else: action = None
    expected = original.predict(value, action)
    assert expected['status'].startswith('unknown')
    assert ordered(context.predict(action)) == ordered(expected)


def test_input_actions_snapshot_and_outputs_cannot_mutate_context():
    value = bundle(); pristine = deepcopy(value); context = candidate.RequestContext(value)
    actions = context.actions(); action = deepcopy(actions[0]); expected = original.predict(pristine, action)
    value['jobs']['loaded']['destination'] = 99
    context.snapshot()['resources'][5]['actual_available'] = 0
    actions[0]['return_delay'] = 99
    first = context.predict(action); first['completion']['loaded'] = -1
    assert ordered(context.predict(action)) == ordered(expected)
    assert context.snapshot() == pristine
    assert context.describe()['online_information_delivered'] is False


def test_guard_and_potential_once_per_request_dynamic_state_per_candidate(monkeypatch):
    supplied = bundle(); counts = {'guard': 0, 'potential': 0}; seen = []
    old_guard = original.contract.supported_contract; old_potential = original.service_aware_potential
    old_run = original.Projection.run
    def guard(): counts['guard'] += 1; return old_guard()
    def potential(*args, **kwargs): counts['potential'] += 1; return old_potential(*args, **kwargs)
    def run(self):
        seen.append(self)
        return old_run(self)
    monkeypatch.setattr(original.contract, 'supported_contract', guard)
    monkeypatch.setattr(original, 'service_aware_potential', potential)
    monkeypatch.setattr(original.Projection, 'run', run)
    context = candidate.RequestContext(supplied)
    for action in context.actions()[:2]: context.predict(action)
    second = candidate.RequestContext(supplied); second.predict(second.actions()[0])
    assert counts == {'guard': 2, 'potential': 2}
    assert seen[0].score_potential is seen[1].score_potential
    assert seen[0].score_potential is not seen[2].score_potential
    for name in ('b', 'jobs', 'trays', 'requests', 'calendars', 'potential', 'events'):
        assert getattr(seen[0], name) is not getattr(seen[1], name)
    with pytest.raises(TypeError): seen[0].score_potential[0][1] = 4
    assert original.Projection.__init__.__globals__['service_aware_potential'] is potential


def test_guard_ast_and_zero_argument_super_closure_preserved():
    _, _, proof = candidate.compile_guards()
    assert proof['status'] == 'exact_input_guard_AST_and_typed_action_guard'
    context = candidate.RequestContext(bundle())
    assert context.predict(context.actions()[0])['status'] == 'conditional_prediction'


def test_custom_container_and_cycles_are_outside_context_domain():
    class Custom(dict): pass
    with pytest.raises(TypeError): candidate.RequestContext(Custom(bundle()))
    value = bundle(); value['cycle'] = value
    with pytest.raises(ValueError): candidate.RequestContext(value)


def test_separate_context_revalidates_mutated_input():
    value = bundle(); first = candidate.RequestContext(value); action = first.actions()[0]
    value['owner_pending_tray_requests'] = ['later']
    second = candidate.RequestContext(value)
    assert first.predict(action)['status'] == 'conditional_prediction'
    assert second.predict(action) == original.predict(value, action)
