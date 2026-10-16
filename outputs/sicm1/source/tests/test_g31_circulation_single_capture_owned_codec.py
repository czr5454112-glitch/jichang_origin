"""Synthetic live wiring only. No C load, accepted session or model is made."""
import builtins
import copy
import dis
from types import CodeType, SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import initial_owner_route_single_capture_owned_codec as m


def synthetic(normalize=None):
    # Deliberately bypasses public bind only in this synthetic test. The real
    # public binder rejects every Python callable below as a Candidate.
    normalize = normalize or m.publisher.owned.normalization.normalize
    old = m.publisher.reference._bind_provider(normalize)
    return m._compose(m.publisher._compose(old))


class Session:
    def __init__(self):
        self.physical_time = 4.171
        self.calls = []

    def advance_to(self, now, **kwargs):
        self.calls.append(('drain', now, kwargs))
        return {'status': 'reached', 'physical_time': now, 'horizon_complete': True}


def root(binding, payload=None):
    value = object.__new__(binding.CapturedRequest)
    value.session = Session()
    value.client = m.previous.make_client(value.session)
    value.native, value.accepted = object(), {}
    value.request_id = 'synthetic:owned-codec'
    value.started_ns, value.deadline_ns, value.cutoff_ns = 1, 100_000_001, 60_000_001
    value.choice, value.command_id = 'native_default', None
    value.state = 'closed_native_default_first_hop'
    value.hop = {'from': 0, 'to': 1, 'observed_at': 4.171}
    value.events = [{'stage': 'synthetic', 'value': payload}]
    value.initial_endpoint_records = [{'synthetic_role': 'A_initial'}, {'synthetic_role': 'A_final'}]
    value.B_endpoint_records = [{'synthetic_role': 'B', 'tuple': (1, -0.0)}]
    value.last_boundary = None
    return value


def timed_publish(functions, value):
    ticks = iter((200, 300, 400))
    clock = SimpleNamespace(perf_counter_ns=lambda: next(ticks))
    evidence = m.private(functions.EVIDENCE, {'time': clock})
    finish = m.private(functions.finish_root, {'time': clock, 'evidence': evidence})
    publish = m.private(functions.publish_root, {'time': clock, 'finish_root': finish})
    value.evidence = evidence.__get__(value)
    holder = []
    result = publish(value, holder)
    assert holder[-1] is result
    return result


def test_source_proof_has_no_C_loading_or_campaign_claim():
    proof = m.source_proof()
    assert proof['explicit_verified_candidate_required']
    assert not proof['C_load_or_build_implicit']
    assert not proof['actual_campaign_or_performance_claim']
    assert not proof['per_sample_cycle_cleanup_certified']


@pytest.mark.parametrize('candidate', [None, object(), SimpleNamespace(normalize=lambda x: x)])
def test_public_bind_rejects_python_test_providers(candidate):
    with pytest.raises(ValueError, match='verified_candidate_required'):
        m.bind(candidate)


def test_public_bind_rejects_changed_upstream_before_invocation():
    def forbidden(candidate):
        raise AssertionError('changed provider must not be invoked')
    fake = SimpleNamespace(bind=forbidden)
    check = m.private(m.bind, {'publisher': fake, 'source_proof': lambda: {}})
    with pytest.raises(ValueError, match='verified_binder_changed'):
        check(object())


def test_live_methods_collection_normalizer_and_exact_chain_all_unchanged():
    b = synthetic()
    proof = m.binding_proof(b)
    assert proof['same_exact_chain_constructor_classcell_and_drain']
    assert proof['same_current_native_handle_transport_and_ACK_guards']
    assert not proof['collection_normalization_changed']
    assert not proof['verified_C_claim_from_this_shape_check']
    assert b.ActualAdvanceChain is m.previous.ActualAdvanceChain
    assert b.ActualAdvanceChain.__init__.__closure__ is m.previous.ActualAdvanceChain.__init__.__closure__
    assert b.CapturedRequest.collect is m.previous.COLLECT
    assert b.CapturedRequest.final_revalidate_and_submit is m.previous.FINAL_REVALIDATE
    assert b.FixedDefaultRequest.choose is m.previous.FixedDefaultRequest.choose
    assert b.call_with_recorded_collection.__globals__['captured_collection'] is m.previous.single.captured_collection
    assert b.collection_inventory is m.previous.collection_inventory
    assert m.previous.single.normalization.normalize is m.publisher.reference.provider.original.normalize


@pytest.mark.parametrize('name', ['collect', 'final_revalidate_and_submit', 'observe_after_boundary',
                                  'drain_and_finish_if_closed', '_record', 'evidence'])
def test_request_method_drift_rejected(name):
    b = synthetic()
    setattr(b.CapturedRequest, name, lambda *args: None)
    with pytest.raises(ValueError, match='owned_live_'):
        m.binding_proof(b)


@pytest.mark.parametrize('name', ['ActualAdvanceChain', 'call_with_recorded_collection',
                                  'TracedContinuationOwner', 'make_client', 'collection_inventory'])
def test_original_authority_or_collection_path_drift_rejected(name):
    b = synthetic()
    setattr(b, name, object())
    with pytest.raises(ValueError, match='owned_live_changed'):
        m.binding_proof(b)


def test_real_native_handle_gate_rejects_fixture_before_queries():
    b = synthetic()
    value = root(b)
    with pytest.raises(ValueError, match='accepted_session'):
        b.ActualAdvanceChain(value.session, value.client, value, {})
    assert value.session.calls == []


def synthetic_constructor(binding):
    # Test-only bypass of ONE native admission check, never returned by bind.
    request = m.previous.request
    adapter = SimpleNamespace(**{**vars(request.adapter), '_valid_handle': lambda *a: True})
    facade = SimpleNamespace(**{**vars(request), 'adapter': adapter})
    return m.private(binding.ActualAdvanceChain.__init__, {'request': facade})


def test_unchanged_constructor_accepts_inherited_methods_and_original_exact_drain():
    b = synthetic()
    value = root(b)
    chain = object.__new__(b.ActualAdvanceChain)
    synthetic_constructor(b)(chain, value.session, value.client, value, {})
    assert value._observation_advance_chain is chain and chain.root is value
    assert m.previous._actual_root_drain(value, value.session.physical_time)['horizon_complete']
    assert len(value.session.calls) == 1
    assert chain.collection_source_inventory['generated_template']['ordered_code_hooks'] == ['before', 'after'] * 3


@pytest.mark.parametrize('wrong', ['collect', 'observe_after_boundary', 'drain_and_finish_if_closed'])
def test_unchanged_constructor_still_rejects_wrong_live_method(wrong):
    b = synthetic()
    value = root(b)
    setattr(value, wrong, (lambda self: None).__get__(value))
    with pytest.raises(ValueError):
        synthetic_constructor(b)(object.__new__(b.ActualAdvanceChain), value.session, value.client, value, {})
    assert value.session.calls == []


@pytest.mark.parametrize('payload', [None, {'z': -0.0, 'a': 1, 'f': 1.0}, '\U0001f642',
                                    [(1, 2), {'nested': [False, 2**80]}]])
def test_complete_root_parity_original_proof_B_records_clocks_and_owned_output(payload):
    b = synthetic()
    old_root, new_root = root(b, copy.deepcopy(payload)), root(b, copy.deepcopy(payload))
    old = timed_publish(m.previous, old_root)
    new = timed_publish(b, new_root)
    assert m.publisher.owned.previous.single.exact_tree(old, new)
    proof = new['value']['evidence']['runtime_query_proof']
    assert proof['first_hop_observation_contract'] == m.previous.previous.entry.MARKER
    assert set(proof) >= {'trace', 'calls', 'outbox', 'advance_calls', 'checkpoint'}
    assert len(new['value']['evidence']['initial_endpoint_records']['A']) == 2
    assert len(new['value']['evidence']['initial_endpoint_records']['B']) == 1
    assert new['outside_return_ns'] == 400 and new['warm_caller_elapsed_ns'] == 399
    new['value']['evidence']['events'].clear()
    assert old['value']['evidence']['events'] and new_root.events


@pytest.mark.parametrize('error', [ValueError, MemoryError])
def test_normalizer_error_propagates_once_without_new_fallback(error):
    calls = []
    def fail(value):
        calls.append(value)
        raise error('synthetic_normalizer_failure')
    b = synthetic(fail)
    with pytest.raises(error, match='synthetic_normalizer_failure'):
        b.publish_root(root(b), [])
    assert len(calls) == 1


def test_strict_readback_failure_does_not_publish_or_hide_elapsed_work():
    b = synthetic()
    value = root(b)
    def fail(*args, **kwargs):
        raise ValueError('synthetic_strict_parser_failure')
    value.evidence = m.private(b.EVIDENCE, {'_owned_json_loads': fail}).__get__(value)
    records = []
    with pytest.raises(ValueError, match='synthetic_strict_parser_failure'):
        b.publish_root(value, records)
    assert records == []


def all_codes(code):
    yield code
    for value in code.co_consts:
        if type(value) is CodeType:
            yield from all_codes(value)


def test_branch_all_globals_direct_failure_publisher_and_scheduler_bound():
    b = synthetic()
    branch = m.branch_function(b)
    assert m.branch_source_proof(b, branch)['direct_and_scheduler_publication_both_bound']
    assert branch.__globals__['publish_root'] is b.publish_root
    assert branch.__globals__['run_continuation'] is b.run_continuation
    assert branch.__globals__['call_with_recorded_collection'] is m.previous.call_with_recorded_collection
    assert b.run_continuation.__globals__['publish_root'] is b.publish_root
    assert b.run_continuation.__globals__['ActualAdvanceChain'] is m.previous.ActualAdvanceChain
    assert 'publish_root' in branch.__code__.co_names
    for fn in (branch, b.run_continuation, b.EVIDENCE, b.finish_root, b.publish_root):
        for code in all_codes(fn.__code__):
            assert not {i.argval for i in dis.get_instructions(code)
                if i.opname in ('LOAD_GLOBAL', 'LOAD_NAME')
                and i.argval not in fn.__globals__ and not hasattr(builtins, i.argval)}


@pytest.mark.parametrize('name', ['CapturedRequest', 'FixedDefaultRequest', 'run_continuation',
                                  'publish_root', 'call_with_recorded_collection'])
def test_branch_stale_or_unknown_live_binding_rejected(name):
    b = synthetic()
    branch = m.private(m.branch_function(b), {name: object()})
    with pytest.raises(ValueError):
        m.branch_source_proof(b, branch)


@pytest.mark.parametrize('name', ['root_runtime_proof', '_owned_json_loads', '_owned_pairs', '_codec_encode'])
def test_evidence_proof_parser_or_codec_substitution_rejected(name):
    b = synthetic()
    b.EVIDENCE = m.private(b.EVIDENCE, {name: object()})
    with pytest.raises(ValueError, match='full_globals'):
        m.binding_proof(b)


def test_old_classes_and_module_globals_not_mutated_and_bindings_are_independent():
    a, b = synthetic(), synthetic()
    assert a.CapturedRequest is not b.CapturedRequest
    assert a.EVIDENCE is not b.EVIDENCE
    assert a.ActualAdvanceChain is b.ActualAdvanceChain is m.previous.ActualAdvanceChain
    assert m.previous.CapturedRequest.evidence is m.previous.EVIDENCE
    assert m.previous.run_continuation.__globals__['publish_root'] is m.previous.publish_root
    assert m.publisher.owned.EVIDENCE.__globals__['normalization'] is m.publisher.owned.normalization


def test_source_archive_canonicalizes_absolute_key_and_rejects_duplicate(tmp_path):
    from scripts.experiments.g31_ics_circulation import run_single_capture_owned_codec_pure as runner
    path = tmp_path/'nested/a.py'
    assert runner.canonical_sources({str(path): b'a'}, tmp_path) == {'nested/a.py': b'a'}
    with pytest.raises(ValueError, match='duplicate_canonical_source'):
        runner.canonical_sources({str(path): b'a', 'nested/a.py': b'a'}, tmp_path)


@pytest.mark.parametrize('key', ['../live.py', 'C:/outside/a.py'])
def test_archive_target_rejects_escape_and_absolute_key(tmp_path, key):
    from scripts.experiments.g31_ics_circulation import run_single_capture_owned_codec_pure as runner
    with pytest.raises(ValueError, match='canonical_relative'):
        runner.archive_target(tmp_path, key)


def test_archive_target_is_distinct_and_contained(tmp_path):
    from scripts.experiments.g31_ics_circulation import run_single_capture_owned_codec_pure as runner
    saved = runner.archive_target(tmp_path, 'scripts/a.py')
    assert saved.is_relative_to((tmp_path/'source').resolve())
    assert saved != (runner.ROOT/'scripts/a.py').resolve()


def test_source_closure_rejects_external_file_before_archive_write(tmp_path):
    from scripts.experiments.g31_ics_circulation import run_single_capture_owned_codec_pure as runner
    with pytest.raises(ValueError, match='source_outside_root'):
        runner.canonical_sources({'../outside.py': b'a'}, tmp_path)
