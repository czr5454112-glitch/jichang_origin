"""Synthetic binding draft only; no extension load or claimed C execution."""
import copy
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import complete_root_evidence_owned_decode_c_binding as c
from scripts.experiments.g31_ics_circulation import root_evidence_mock as mock


def shape(payload):
    return {'root_id': 'synthetic:C-binding', 'state': 'closed_native_default_first_hop',
            'root_started_ns': 100, 'root_deadline_ns': 100000100,
            'decision_cutoff_ns': 60000100, 'choice': 'native_default', 'command_id': None,
            'hop': {'prefix': [0, 1]}, 'events': [{'stage': 'synthetic', 'value': payload}],
            'initial_endpoint_records': {'A': [{'view': [(1, -0.0)]}], 'B': [{'view': [2]}]}}


def synthetic_pair(normalize):
    # This private composition is deliberately NOT c.bind and not C authority.
    reference = c.reference._bind_provider(normalize)
    return reference, c._compose(reference)


def publish(functions, payload):
    ticks = iter((200, 300, 400))
    clock = SimpleNamespace(perf_counter_ns=lambda: next(ticks))
    method = c.owned.private(functions.EVIDENCE, {'time': clock,
        'root_runtime_proof': lambda root: {'synthetic': True, 'source': 'same_stub'}})
    finish = c.owned.private(functions.finish_root, {'time': clock, 'evidence': method})
    publisher = c.owned.private(functions.publish_root, {'time': clock, 'finish_root': finish})
    holder = []
    result = publisher(mock.root_from_evidence(shape(payload), method), holder)
    assert holder == [result]
    return result


def test_source_proof_does_not_claim_C_load_or_execution():
    result = c.source_proof()
    assert result['C_loaded_by_this_module'] is False
    assert result['native_or_performance_dispatched'] is False
    assert result['fixture_direct_C_support_check_still_required'] is True
    assert result['C_binary_or_ABI_acceptance_replaced'] is False
    assert c._REFERENCE_BIND is c.reference.bind


def test_exact_same_facade_callable_and_original_publisher_on_both_arms():
    calls = []
    def normalize(value):
        calls.append(value)
        return c.owned.normalization.normalize(value)
    a, b = synthetic_pair(normalize)
    assert a.EVIDENCE.__globals__['normalization'] is b.EVIDENCE.__globals__['normalization']
    assert a.EVIDENCE.__globals__['normalization'].normalize is normalize
    assert a.finish_root.__code__ is b.finish_root.__code__
    assert a.publish_root.__code__ is b.publish_root.__code__
    assert a.EVIDENCE.__globals__['root_runtime_proof'] is b.EVIDENCE.__globals__['root_runtime_proof']
    assert a.finish_root.__globals__['image'] is b.finish_root.__globals__['image']
    publish(a, None); publish(b, None)
    assert len(calls) == 2 and calls[0] is not calls[1]


@pytest.mark.parametrize('payload', [None, {'z': -0.0, 'a': 1.0}, '\U0001f642',
                                    [(1, 2), {'x': [False, 2**80]}], {'rows': [{'x': 1}]*2}])
def test_synthetic_full_publisher_parity_and_independent_return(payload):
    before = copy.deepcopy(payload)
    a, b = synthetic_pair(c.owned.normalization.normalize)
    old, new = publish(a, payload), publish(b, payload)
    assert c.owned.previous.single.exact_tree(old, new)
    assert old is not new and old['value'] is not new['value']
    new['value']['evidence']['events'].clear()
    assert old['value']['evidence']['events']
    assert payload == before


@pytest.mark.parametrize('error', [MemoryError, ValueError])
def test_provider_failure_propagates_once_per_arm_without_fallback_added(error):
    calls = []
    def fail(value):
        calls.append(value)
        raise error('provider_failure')
    for functions in synthetic_pair(fail):
        with pytest.raises(error, match='provider_failure'): publish(functions, None)
    assert len(calls) == 2


@pytest.mark.parametrize('candidate', [None, object(), SimpleNamespace(normalize=lambda x: x)])
def test_public_binding_rejects_unverified_python_provider(candidate):
    with pytest.raises(ValueError, match='verified_candidate_required'): c.bind(candidate)


@pytest.mark.parametrize('change', ['extra_global', 'wrong_finish', 'extra_facade_field', 'missing_function'])
def test_private_composition_checks_full_reference_chain_and_exact_global_delta(change):
    a = c.reference._bind_provider(c.owned.normalization.normalize)
    if change == 'extra_global':
        a.EVIDENCE = c.owned.private(a.EVIDENCE, {'unexpected': True})
    elif change == 'wrong_finish':
        a.finish_root = c.owned.private(a.finish_root, {'evidence': c.owned.EVIDENCE})
    elif change == 'extra_facade_field':
        a.EVIDENCE.__globals__['normalization'].unexpected = True
    else:
        del a.publish_root
    with pytest.raises(ValueError, match='owned_C_binding:'): c._compose(a)


def test_frozen_provider_and_normalization_globals_unchanged_by_private_composition():
    reference_method = c.reference.frozen.EVIDENCE.__globals__['normalization']
    owned_method = c.owned.EVIDENCE.__globals__['normalization']
    a, b = synthetic_pair(c.owned.normalization.normalize)
    assert c.reference.frozen.EVIDENCE.__globals__['normalization'] is reference_method
    assert c.owned.EVIDENCE.__globals__['normalization'] is owned_method
    assert reference_method is owned_method
    assert a.EVIDENCE.__globals__['normalization'] is not reference_method
    assert b.EVIDENCE.__globals__['normalization'] is a.EVIDENCE.__globals__['normalization']


def test_source_proof_requires_original_C_binder_before_any_provider_validation():
    forbidden = lambda candidate: pytest.fail('changed binder must not be called')
    check = c.owned.private(c.bind, {'reference': SimpleNamespace(bind=forbidden)})
    with pytest.raises(ValueError, match='reference_binder_changed'): check(object())
