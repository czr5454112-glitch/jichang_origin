"""Quiet suffix correctness and cases where batching is forbidden."""
import copy
import heapq
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import public_preference_quiet_context as quiet
from test_g31_circulation_public_native_preference_projection import data


def state():
    request = {'terminal': True, 'ack': 'received', 'tray': 'E', 'ack_at': 1.}
    return SimpleNamespace(completed={'j': 3.}, jobs={'j': {}}, requests=[request],
        last_supply=request, trays={'E': {'mode': 'empty', 'node': 6}},
        events=[(4., 99, 1, 'tick', ()), (5., 99, 2, 'tick', ())], time=3.)


@pytest.mark.parametrize('mutation', ['nonterminal', 'future_recovery', 'physical_event', 'mutable_tick', 'incomplete_job', 'nonfinite'])
def test_ineligible_tail_cannot_skip_required_events(mutation):
    p = state()
    if mutation == 'nonterminal': p.requests[0]['terminal'] = False
    elif mutation == 'future_recovery':
        p.last_supply.update(ack='rejected', ack_at=1000.)
        p.trays['E']['node'] = 5
    elif mutation == 'physical_event': p.events[1] = (5., 6, 2, 'ack', (p.requests[0],))
    elif mutation == 'mutable_tick': p.events[1] = (5., 99, 2, 'tick', ({},))
    elif mutation == 'incomplete_job': p.jobs['pending'] = {}
    else: p.events[1] = (float('inf'), 99, 2, 'tick', ())
    before = copy.deepcopy(p.__dict__)
    assert quiet.quiet_suffix(p) is False
    assert p.__dict__ == before


@pytest.mark.parametrize('count', [0, 19998, 19999, 20000])
def test_count_overflow_and_heap_consumption_match_original_loop(count):
    p = state(); original = copy.deepcopy(p)
    heapq.heapify(p.events); heapq.heapify(original.events)
    expected_count, exceeded = count, False
    while original.events:
        original.time, _, _, _, _ = heapq.heappop(original.events)
        if original.time > 40.: break
        expected_count += 1
        if expected_count > 20000:
            exceeded = True; break
    assert quiet.quiet_suffix(p)
    assert quiet.consume_quiet_suffix(p, count) == (expected_count, exceeded)
    assert p.__dict__ == original.__dict__


def test_future_horizon_pop_retains_exact_time_and_unconsumed_heap():
    p = state(); p.events = [(40., 99, 1, 'tick', ()), (41., 99, 2, 'tick', ()), (42., 99, 3, 'tick', ())]
    heapq.heapify(p.events)
    assert quiet.consume_quiet_suffix(p, 10) == (11, False)
    assert p.time == 41. and p.events == [(42., 99, 3, 'tick', ())]


def test_all32_full_outputs_and_caller_mutation_isolation():
    bundle, _ = data()
    reference = quiet.base.RequestContext(bundle)
    candidate = quiet.QuietRequestContext(bundle)
    actions = reference.actions()
    assert candidate.actions() == actions and len(actions) == 32
    for action in actions:
        assert candidate.predict(action) == reference.predict(action)
    first = candidate.predict(actions[0]); first['completion']['loaded'] = 999.
    assert candidate.predict(actions[0]) == reference.predict(actions[0])


def test_input_and_action_failure_reasons_retained():
    bundle, action = data(); bundle['trays']['E']['available_at'] = 999.
    assert quiet.QuietRequestContext(bundle).predict(action) == quiet.base.RequestContext(bundle).predict(action)
    bundle, action = data(); action['return_delay'] = False
    assert quiet.QuietRequestContext(bundle).predict(action) == quiet.base.RequestContext(bundle).predict(action)
