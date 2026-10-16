"""Synthetic draft only: no native, saved fixture, projection or performance.

Fabricated collector authority below is injected only into private test clones.
It is not an accepted native capability and cannot certify physical behavior.
"""
import ast
import copy
import inspect
import json
from types import FunctionType, SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import live_obligation_online_retained_policy as p


def clone(function, namespace):
    result = FunctionType(function.__code__, namespace, function.__name__,
                          function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def vector(later='prefer_8', delay=.5):
    return {'initial_action': 'prefer_2', 'empty_departure': .11,
            'return_delay': delay, 'later_action': later}


def construct(kind=p.OwnerPolicy, owner='B', selected=None):
    session = SimpleNamespace(physical_time=2.)
    client = SimpleNamespace(session=session, rows={}, calls=[])
    client.owned = lambda requested: client.rows if requested == owner else (_ for _ in ()).throw(AssertionError('peer read'))
    selected = vector() if selected is None else selected
    return kind(object(), session, client, owner, object(), None, selected, object())


def restore_metadata(value):
    if type(value) is dict:
        result = {}
        for key, item in value.items():
            target = p.OLD_VECTOR_KEY if key == p.VECTOR_KEY else key
            if key == 'status' and item == p.STATUS: item = p.OLD_STATUS
            elif key == p.EXECUTED_KEY: item = False
            result[target] = restore_metadata(item)
        return result
    if type(value) is list: return [restore_metadata(item) for item in value]
    return value


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()


def synthetic(kind, *, phase='first_reuse_route', supported=True, later='prefer_8',
              returned='physical-id', demand=True, retry=False, broken_target=False,
              quiet=False, submission_error=None):
    owner = 'A' if phase == 'first_return' else 'B'
    instance = construct(kind, owner, vector(later))
    tray = {'tray_id': 'L', 'node': 6 if owner == 'A' else 7,
        'mode': 'empty' if owner == 'A' else 'loaded',
        'business_bag_id': '' if owner == 'A' else 'reuse1',
        'generation': 2, 'traversal_id': 4, 'edge_from': -1, 'edge_to': -1,
        'reception_node': -1, 'committed_prefix': [6 if owner == 'A' else 7],
        'available_at': 1., 'service_ready_at': 20.}
    instance.pending = {'phase': phase, 'at': 1., 'deadline': 3., 'request_id': 'opaque-id',
        'root': 'own-root', 'trigger_tray': copy.deepcopy(tray), 'peer_message': 'opaque-peer',
        'recollection_index': 0, 'policy_quiet_since': 1.}
    view = {'owner_id': owner, 'now': 2., 'trays': [copy.deepcopy(tray)], 'node_contracts': []}
    if broken_target: view['trays'][0]['generation'] += 1
    if quiet: instance.peer_quiet_until = 3.
    instance.client.rows = {'opaque-id': {'ack': {'status': 'delivered'}}}
    trace = []
    information = {'status': 'conditional' if supported else 'unknown',
        'bundle': {'trays': {'L': {'service_ready_at': 20.}}}, 'reasons': ['synthetic_only']}
    def collect(*args, **kwargs):
        trace.append(['collect', args[2], args[3], copy.deepcopy(kwargs['owned_client_rows'])])
        return copy.deepcopy(information)
    fake_adapter = SimpleNamespace(collect_native=collect, json_data=copy.deepcopy,
        is_native_attempt=lambda item: True,
        is_native_collected=lambda item: item.get('status') == 'conditional')
    def screen(*args):
        trace.append(['retry_screen'])
        return {'status': 'conditional_retry_admissible' if retry else 'not_admitted',
                'retained_own_service_bound': 20., 'reason': 'synthetic_only'}
    original = instance.decide_pending.__func__
    fixed = original.__globals__['fixed_choice']
    fixed = clone(fixed, {**fixed.__globals__, 'adapter': fake_adapter})
    prior = SimpleNamespace(return_earliest=p.historical.old.old.prior.return_earliest,
        v1=SimpleNamespace(latest_demand=lambda *_: {'jobs': [{'origin': 7}]} if demand else None))
    decision = clone(original, {**original.__globals__, 'adapter': fake_adapter,
        'fixed_choice': fixed, 'retry_admission': screen, 'prior': prior})
    instance.decide_pending = decision.__get__(instance, type(instance))
    def submit(view, tray, selected, causal):
        trace.append(['submit', selected, copy.deepcopy(causal)])
        if submission_error is not None: raise submission_error
        return returned
    instance.route_tray = submit
    instance.return_tray = lambda view, tray, delivered, delay, causal: submit(view, tray, delay, causal)
    instance.publication = lambda label, causal: trace.append(['publication', label, copy.deepcopy(causal)]) or 'recollection-id'
    return instance, view, trace


def state(instance, trace):
    return {'trace': trace, 'pending': instance.pending, 'attempts': instance.collection_attempts,
            'decisions': instance.decisions, 'quiet': instance.quiet_periods,
            'reply_rows': instance.reply_budget.rows}


def test_source_proof_only_three_metadata_expressions():
    proof = p.source_proof()
    assert [item['metadata_edits'] for item in proof['transforms']] == [['status'], ['key', 'executed']]
    assert all(item['inverse_AST_exact'] for item in proof['transforms'])
    assert not proof['guards_retries_recollection_reply_budget_changed']
    assert not proof['peer_proposal_or_consensus_read']
    assert not proof['later_model_reestimation']
    assert not proof['resource_failure_timing_equivalent']


def test_constructor_keeps_actual_per_owner_adapter_and_original_retry_guard():
    instance = construct()
    decision = instance.decide_pending.__func__
    adapter = decision.__globals__['adapter']
    assert type(adapter) is p.historical.adapter.OwnerCollectionAdapter
    assert adapter._owner == instance.owner and adapter._client is instance.client
    assert adapter._session is instance.session
    assert decision.__globals__['fixed_choice'].__globals__['adapter'] is adapter
    assert decision.__globals__['retry_admission'] is p.historical.old.retry_admission
    assert adapter.collect_native(object(), object(), 'B', 'id')['reasons'] == ['wrong_bound_owner_collection_adapter']


def test_complete_private_globals_and_function_attributes_preserved():
    old = construct(p.historical.OwnerPolicy)
    new = construct()
    of, nf = old.decide_pending.__func__, new.decide_pending.__func__
    assert set(of.__globals__) == set(nf.__globals__)
    for key in of.__globals__:
        if key not in ('adapter', 'fixed_choice'):
            assert of.__globals__[key] is nf.__globals__[key]
    for left, right in ((of, nf), (of.__globals__['fixed_choice'], nf.__globals__['fixed_choice'])):
        assert left.__defaults__ is right.__defaults__
        assert left.__kwdefaults__ is right.__kwdefaults__
        assert left.__closure__ is right.__closure__
    assert p.historical.old.OwnerPolicy.decide_pending.__globals__['adapter'] is not nf.__globals__['adapter']


def test_all_other_policy_methods_are_exactly_inherited():
    for name in ('begin', 'exchange', '_begin_recollection', 'activate', 'return_tray',
                 'route_tray', 'publication', 'hold_new_admissions_after_reply'):
        assert getattr(p.OwnerPolicy, name) is getattr(p.historical.OwnerPolicy, name)
    assert p.OwnerPolicy.__init__.__closure__[0].cell_contents is p.OwnerPolicy


def test_constructor_has_no_peer_or_joint_proposal_parameter():
    names = list(inspect.signature(p.OwnerPolicy.__init__).parameters)
    assert names == ['self', 'native', 'session', 'client', 'owner', 'ledger', 'channel',
                     'selected_vector', 'accepted', 'supply']
    one, two = vector('prefer_8'), vector('native_default', 0.)
    a, b = construct(owner='A', selected=one), construct(owner='B', selected=two)
    assert a.method is one and b.method is two and a.method != b.method
    assert a.decide_pending.__globals__['adapter'] is not b.decide_pending.__globals__['adapter']


@pytest.mark.parametrize('settings,expected', [
    ({}, True),
    ({'later': 'native_default', 'returned': None}, True),
    ({'returned': None}, False),
    ({'supported': False}, False),
    ({'broken_target': True}, False),
    ({'phase': 'first_return'}, True),
    ({'phase': 'first_return', 'demand': False}, False),
    ({'phase': 'first_return', 'supported': False}, False),
])
def test_complete_ordered_state_diff_is_only_declared_metadata(settings, expected):
    old, ov, ot = synthetic(p.historical.OwnerPolicy, **settings)
    new, nv, nt = synthetic(p.OwnerPolicy, **settings)
    old.decide_pending(ov)
    new.decide_pending(nv)
    assert encode(state(old, ot)) == encode(restore_metadata(state(new, nt)))
    row = new.decisions[-1]
    assert row[p.EXECUTED_KEY] is row['selected_action_admitted'] is expected
    assert row['decision'].get('native_model_protection_certified', False) is False
    assert 'predicted_protection' not in row['decision'] or row['decision']['predicted_protection'] is None


def test_unknown_choice_and_no_fabricated_execution_are_preserved():
    new, view, trace = synthetic(p.OwnerPolicy, supported=False, returned='fallback-command')
    new.decide_pending(view)
    row = new.decisions[0]
    assert row['decision'] == {'status': 'unknown_unverified_or_unsupported_input', 'selected_action': None}
    assert row['fallback_used'] and row['native_request_id'] == 'fallback-command'
    assert row[p.EXECUTED_KEY] is False


def test_quiet_early_return_does_not_collect_or_generate_metadata():
    for kind in (p.historical.OwnerPolicy, p.OwnerPolicy):
        instance, view, trace = synthetic(kind, quiet=True)
        instance.decide_pending(view)
        assert trace == [] and instance.decisions == [] and instance.collection_attempts == []


def test_failed_attempt_recollection_uses_original_branch_and_budget():
    old, ov, ot = synthetic(p.historical.OwnerPolicy, supported=False, retry=True)
    new, nv, nt = synthetic(p.OwnerPolicy, supported=False, retry=True)
    old.decide_pending(ov); new.decide_pending(nv)
    assert encode(state(old, ot)) == encode(state(new, nt))
    assert new.pending['recollection_index'] == 1 and new.decisions == []
    assert new.collection_attempts[0]['disposition'] == 'one_fresh_pair_requested'
    with pytest.raises(ValueError, match='recollection_budget'):
        new._begin_recollection(new.pending, {'retained_own_service_bound': 20.}, {}, nv)


@pytest.mark.parametrize('error', [RuntimeError('submission failed'), MemoryError('allocation')])
def test_submission_exception_preserves_original_prefix_and_propagates(error):
    results = []
    for kind in (p.historical.OwnerPolicy, p.OwnerPolicy):
        instance, view, trace = synthetic(kind, submission_error=error)
        with pytest.raises(type(error)) as caught:
            instance.decide_pending(view)
        assert caught.value is error
        assert instance.pending is not None and len(instance.collection_attempts) == 1
        assert instance.decisions == []
        results.append(state(instance, trace))
    assert encode(results[0]) == encode(restore_metadata(results[1]))


def test_fixed_choice_copies_selected_vector_and_keeps_unknown_guard():
    instance = construct()
    function = instance.decide_pending.__globals__['fixed_choice']
    namespace = {**function.__globals__, 'adapter': SimpleNamespace(is_native_collected=lambda value: value is token)}
    function = clone(function, namespace)
    token = object()
    selected = vector()
    result = function(token, selected)
    assert result['status'] == p.STATUS and result['vector'] == selected
    assert result['vector'] is not selected
    result['vector']['return_delay'] = 99.
    assert selected['return_delay'] == .5
    assert function({}, selected) == {'status': 'unknown_unverified_or_unsupported_input', 'selected_action': None}


def test_original_defaults_change_is_not_silently_cloned(monkeypatch):
    monkeypatch.setattr(p._ORIGINAL_CHOICE, '__defaults__', ('changed',))
    with pytest.raises(ValueError, match='original_function_identity'):
        construct()


def test_unexpected_function_cannot_be_used_as_historical_rewrite():
    def fixed_choice(information, vector):
        return {'status': p.OLD_STATUS}
    with pytest.raises(ValueError, match='actual_historical_instance_function'):
        p._rewrite(fixed_choice, 'fixed_choice')


def test_metadata_rewrite_does_not_mutate_old_global_namespace():
    before = {name: value for name, value in p._ORIGINAL_DECIDE.__globals__.items()}
    fixed_before = dict(p._ORIGINAL_CHOICE.__globals__)
    construct(owner='A'); construct(owner='B')
    assert set(before) == set(p._ORIGINAL_DECIDE.__globals__)
    assert all(p._ORIGINAL_DECIDE.__globals__[name] is value for name, value in before.items())
    assert all(p._ORIGINAL_CHOICE.__globals__[name] is value for name, value in fixed_before.items())
