"""Exact independent-output, event-budget and mutable alias boundaries."""
import copy
import json
import pytest
from scripts.experiments.g31_ics_circulation import public_preference_prefix_context as prefix
from test_g31_circulation_public_native_preference_projection import data as initial_data
from test_g31_circulation_public_native_later_preference_projection import data as later_data


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


@pytest.mark.parametrize('reverse', [False, True])
def test_all32_complete_output_equals_independent_and_order_isolated(reverse):
    bundle, _ = initial_data(); context = prefix.PrefixContext(bundle)
    actions = context.actions()
    if reverse: actions.reverse()
    for action in actions:
        expected = prefix.original.predict(bundle, action)
        assert encoded(context.predict(action)) == encoded(expected)
    assert context.describe()['root_prefixes'] == 8
    assert context.describe()['return_prefixes'] == 16
    assert context.describe()['completed_candidate_results'] == 32


@pytest.mark.parametrize('phase', ['first_return', 'first_reuse_route'])
def test_all4_later_complete_output_preserves_completed_prefix_and_inactive_choice(phase):
    bundle = later_data(phase); context = prefix.LaterPrefixContext(bundle)
    for action in reversed(context.actions()):
        assert encoded(context.predict(action)) == encoded(prefix.later.predict(bundle, action))
    assert context.describe()['candidate_count'] == 4
    assert context.describe()['completed_unique_results'] == (4 if phase == 'first_return' else 2)


def paused():
    bundle, action = initial_data(); cls = prefix._private_class(bundle, is_later=False)
    p = cls(bundle, action); prefix._freeze_static(p)
    seed, step, finish = prefix._run_parts(prefix.original.Projection); seed(p)
    status, p = prefix._advance(p, step, finish, 'return_decision')
    assert status == 'paused'
    return p, step, finish


def test_dynamic_clone_preserves_request_aliases_but_not_cross_branch_mutations():
    p, step, finish = paused(); child = prefix.clone(p)
    assert child.events is not p.events and child.requests is not p.requests
    for request in child.requests:
        assert all(request is not old for old in p.requests)
    last_index = next(i for i, request in enumerate(p.requests) if request is p.last_supply)
    assert child.last_supply is child.requests[last_index]
    for _, _, _, kind, args in child.events:
        if kind in ('ack', 'grant', 'request_delivery'):
            assert any(args[0] is request for request in child.requests)
    for tray in child.trays.values():
        if 'request' in tray: assert any(tray['request'] is r for r in child.requests)
    old = copy.deepcopy(p.requests); child.requests[0]['next_retry'] = 999.
    assert p.requests == old
    child.calendars[0].append((99., 100.)); assert (99., 100.) not in p.calendars[0]
    child.potential[0, 99] = 123.; assert (0, 99) not in p.potential
    child.receipts[0]['at'] = 999.; assert p.receipts[0]['at'] != 999.


def test_static_readonly_and_only_scalar_ticks_share_identity():
    p, _, _ = paused(); child = prefix.clone(p)
    for field in prefix.STATIC: assert getattr(child, field) is getattr(p, field)
    with pytest.raises(TypeError): child.jobs['loaded']['deadline'] = 0.
    with pytest.raises(TypeError): child.nodes[0]['capacity'] = 9
    old_ticks = [e for e in p.events if prefix._scalar_tick(e)]
    assert old_ticks and all(any(t is other for other in child.events) for t in old_ticks)
    assert not prefix._scalar_tick((1., 99, 1, 'tick', ({'mutable': True},)))


def test_pause_keeps_exact_heap_tuple_and_counter_before_consumption():
    p, step, finish = paused(); item = p.events[0]; count = p._prefix_count
    assert item[3] == 'return_decision'
    assert prefix._advance(p, step, finish, 'return_decision') == ('paused', p)
    assert p.events[0] is item and p._prefix_count == count
    step(p)
    assert p._prefix_count == count + 1 and p.returns == 1


def test_budget_and_horizon_are_not_reset_at_resume():
    p, step, finish = paused(); p._prefix_count = 20000
    _, result = prefix._advance(p, step, finish)
    assert result == {'status': 'unknown_event_budget', 'completion': p.completed}
    assert p._prefix_count == 20001
    p, step, finish = paused(); count = p._prefix_count
    p.events = [(41., 99, 100000, 'tick', ())]
    _, result = prefix._advance(p, step, finish)
    assert p.time == 41. and p._prefix_count == count
    assert result['event_count'] == count


def test_caller_result_bundle_and_action_mutations_do_not_poison_cached_prefix():
    bundle, action = initial_data(); expected = prefix.original.predict(bundle, action)
    context = prefix.PrefixContext(bundle); first = context.predict(action)
    first['physical_projection'][0]['at'] = 999.; first['completion']['loaded'] = 999.
    bundle['jobs']['loaded']['deadline'] = 0.; action['later_action'] = 'prefer_8'
    original_action = {**action, 'later_action': 'native_default'}
    assert context.predict(original_action) == expected
    # A fresh output for the other branch must not share physical log dictionaries.
    second = context.predict(action); second['physical_projection'][0]['at'] = 888.
    assert context.predict(original_action) == expected


@pytest.mark.parametrize('kind', ['initial', 'later'])
def test_invalid_input_and_action_reasons_match_original(kind):
    if kind == 'initial':
        b, action = initial_data(); b['trays']['E']['available_at'] = 99.
        c = prefix.PrefixContext(b); predict = prefix.original.predict
    else:
        b = later_data(); action = {'return_delay': 0., 'later_action': 'native_default'}
        b['owner_pending_tray_requests'] = ['pending']; c = prefix.LaterPrefixContext(b); predict = prefix.later.predict
    assert c.predict(action) == predict(b, action)
    bad = {**action, 'return_delay': False}
    assert c.predict(bad) == predict(b, bad)


def test_unreviewed_dependency_revision_rejected(monkeypatch):
    b, _ = initial_data(); monkeypatch.setattr(prefix, 'EXPECTED_LATER', '0' * 64)
    with pytest.raises(ValueError, match='dependency_revision'): prefix.PrefixContext(b)


def test_custom_copy_hooks_are_not_admitted():
    class Hook:
        def __deepcopy__(self, memo): raise AssertionError('must not execute')
    b, _ = initial_data(); b['injected'] = Hook()
    with pytest.raises(TypeError, match='non_builtin'): prefix.PrefixContext(b)
