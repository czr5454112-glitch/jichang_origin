"""Private integration scaffolding only; no real native handle is manufactured."""
import builtins
import copy
import dis
import json
from types import SimpleNamespace, CodeType
import pytest
from scripts.experiments.g31_ics_circulation import initial_owner_route_single_capture_integration as i
from scripts.experiments.g31_ics_circulation import initial_owner_route_entry_codec_campaign as campaign
from test_g31_circulation_initial_owner_route_single_capture import fixture, pure_candidate
from test_g31_circulation_initial_owner_route_entry_codec_integration import prepared_root


def changes(a, b):
    assert set(a.__globals__) == set(b.__globals__)
    return {name for name in a.__globals__ if a.__globals__[name] is not b.__globals__[name]}


def test_three_collection_sites_are_exact_private_bindings():
    assert changes(i.call_with_recorded_collection, i.old.call_with_recorded_collection) == {'captured_collection'}
    assert changes(i.COLLECT, i.gated.CapturedRequest.collect) == {'old'}
    assert changes(i.FINAL_REVALIDATE, i.old.CapturedRequest.final_revalidate_and_submit) == {'call_with_recorded_collection'}
    assert i.COLLECT.__globals__['TRACED_COLLECT'] is i.gated.TRACED_COLLECT
    assert i._old_facade.call_with_recorded_collection is i.call_with_recorded_collection
    assert i.CapturedRequest.collect is i.FixedDefaultRequest.collect is i.COLLECT
    assert i.CapturedRequest.final_revalidate_and_submit is i.FINAL_REVALIDATE
    assert i.FixedDefaultRequest.choose is i.previous.FixedDefaultRequest.choose


def invoke_initial(root):
    return adapter.collect_initial_ledger(root.native, root.session, 'A', 'A-initial', accepted=root.accepted)


def invoke_final(root):
    return adapter.collect_initial_ledger(root.native, root.session, 'A', 'A-final', accepted=root.accepted)


def invoke_B(native, session, accepted):
    return adapter.collect_initial_ledger(native, session, 'B', 'B-fixed', accepted=accepted)


@pytest.mark.parametrize('case', range(6))
def test_all_three_wrapper_roles_read_fresh_triplets_and_owned_records(tmp_path, case):
    # This privately substitutes only the prototype's test-only outer handle
    # check. Real public collection rejection is tested separately below.
    native, Session = fixture(tmp_path, case)
    root = SimpleNamespace(native=native, session=Session(), accepted=object(), initial_endpoint_records=[])
    wrapper = i.private(i.call_with_recorded_collection, {'captured_collection': pure_candidate()})
    facade = SimpleNamespace(**{**vars(i.old), 'call_with_recorded_collection': wrapper})
    collect = i.private(i.COLLECT, {'old': facade, 'TRACED_COLLECT': invoke_initial})
    final = i.private(i.FINAL_REVALIDATE, {'call_with_recorded_collection': wrapper,
        'request': SimpleNamespace(InitialOwnerRequest=SimpleNamespace(final_revalidate_and_submit=invoke_final))})
    a, ledger = collect(root)
    assert a['native_delivery_verified'] is True and ledger is not None
    first = json.dumps(root.initial_endpoint_records[0], ensure_ascii=False, allow_nan=False)
    root.session.values['command']['last_delivered_ack']['status'] = 'pending_delivery'
    final_value, final_ledger = final(root)
    assert final_value['native_delivery_verified'] is False and final_ledger is None
    assert len(root.session.calls) == 6
    assert [row['endpoints']['request_id'] for row in root.initial_endpoint_records] == ['A-initial', 'A-final']
    assert json.dumps(root.initial_endpoint_records[0], ensure_ascii=False, allow_nan=False) == first
    b_records = []; b_session = Session()
    wrapper(invoke_B, b_records, native, b_session, object())
    assert len(b_session.calls) == 3 and b_records[0]['endpoints']['owner'] == 'B'
    assert [name for name, _ in b_session.calls] == ['view', 'command', 'received']


def test_original_authority_rejects_scaffold_without_any_query(tmp_path):
    native, Session = fixture(tmp_path); session = Session(); records = []
    result, ledger = i.call_with_recorded_collection(invoke_B, records, native, session, object())
    assert not result['native_delivery_verified'] and ledger is None and session.calls == []
    assert records[0]['capture_failure']['status'] == 'unknown_incomplete_endpoint_collection'


def test_inventory_includes_generated_hooks_without_source_alias():
    proof = i.collection_inventory()
    assert proof['original_authority_and_advance_inventory'] == i.gate.collection_inventory()
    assert proof['generated_template']['ordered_code_hooks'] == ['before', 'after'] * 3
    assert proof['generated_template']['generated_code_sha256'] == i._code_digest(i.single._TEMPLATE)
    assert not proof['generated_template']['source_lookup_for_generated_function_used']
    keys = proof['additional_functions']
    for function in (i.single._Capture.before, i.single._Capture.after, i.single.normalization.normalize,
            i.single.normalization.typed_failure_snapshot, i.single.captured_collection, i.single.collector):
        assert function.__module__ + '.' + function.__qualname__ in keys


def test_template_code_digest_stays_exact_after_instruction_read_and_collection(tmp_path):
    before = i._code_digest(i.single._TEMPLATE)
    native, Session = fixture(tmp_path)
    pure_candidate()([], native, Session(), 'A', 'fresh', accepted=object())
    list(dis.get_instructions(i.single._TEMPLATE))
    assert i._code_digest(i.single._TEMPLATE) == before
    assert i.collection_inventory()['generated_template']['generated_code_sha256'] == before


@pytest.mark.parametrize('defect', ['identity', 'code'])
def test_binding_record_detects_defining_attribute_or_code_drift(defect):
    fn = i.private(i.single._Capture.before, {})
    holder = SimpleNamespace(before=fn)
    expected_code = fn.__code__
    if defect == 'identity': holder.before = i.private(fn, {})
    else: fn.__code__ = (lambda self, name: None).__code__
    with pytest.raises(ValueError, match='source_changed'):
        i._binding_record(holder, 'before', fn, expected_code)


@pytest.mark.parametrize('defect', ['template', 'class', 'proof', 'unhooked'])
def test_template_inventory_fails_closed_on_each_new_path_drift(defect):
    facade = SimpleNamespace(**vars(i.single))
    replacements = {'single': facade}
    if defect == 'template': facade._TEMPLATE = i.private(facade._TEMPLATE, {})
    elif defect == 'class': facade._Capture = type('DifferentCapture', (), {})
    elif defect == 'proof': facade._AST_PROOF = {**facade._AST_PROOF, 'inserted_before_after_hooks': 0}
    else:
        facade._TEMPLATE = i.single._NATIVE
        replacements.update(_TEMPLATE=facade._TEMPLATE, _TEMPLATE_CODE=facade._TEMPLATE.__code__)
    with pytest.raises(ValueError, match='template|identity'):
        i.private(i.generated_template_inventory, replacements)()


def test_complete_integration_proof_is_source_only():
    proof = i.integration_proof()
    assert proof['constructor_class_cell_and_exact_native_checks_preserved']
    assert proof['A_initial_A_final_B_same_fresh_wrapper']
    assert not proof['campaign_ready'] and not proof['failure_aware_saved_verifier_included']
    assert not proof['native_or_predictor_dispatched'] and not proof['performance_or_100ms_claim']


def chain_root():
    fixture_root = prepared_root()
    root = object.__new__(i.CapturedRequest)
    root.__dict__.update(vars(fixture_root))
    root.__dict__.pop('evidence', None)
    root.native, root.accepted = object(), {}
    return root


def test_actual_native_gate_remains_before_inventory_or_queries():
    root = chain_root()
    with pytest.raises(ValueError, match='accepted_session'):
        i.ActualAdvanceChain(root.session, root.client, root, {})
    assert root.session.calls == [] and not hasattr(root, '_observation_advance_chain')


def synthetic_constructor():
    # TEST ONLY: isolate the original remaining method/type/MRO checks after
    # its accepted native-handle check. Production has no replacement hook.
    adapter = SimpleNamespace(**{**vars(i.request.adapter), '_valid_handle': lambda *a: True})
    request = SimpleNamespace(**{**vars(i.request), 'adapter': adapter})
    return i.private(i.ActualAdvanceChain.__init__, {'request': request})


def test_original_class_cell_initializes_recorded_chain_and_exact_drain():
    root = chain_root(); chain = object.__new__(i.ActualAdvanceChain)
    synthetic_constructor()(chain, root.session, root.client, root, {})
    assert root._observation_advance_chain is chain and chain.root is root
    assert chain.collection_source_inventory['generated_template']['ordered_code_hooks'] == ['before', 'after'] * 3
    assert i._actual_root_drain(root, root.session.physical_time)['horizon_complete']
    assert len(chain.calls) == 1 and chain.calls[0]['role'] == 'root_same_timestamp_drain'
    assert i.ActualAdvanceChain.__init__.__closure__ is i.previous.ActualAdvanceChain.__init__.__closure__


@pytest.mark.parametrize('defect', ['old_collect', 'old_drain', 'wrong_observe', 'foreign_session', 'duplicate_chain'])
def test_original_constructor_checks_still_reject_wrong_wiring(defect):
    root = chain_root(); chain = object.__new__(i.ActualAdvanceChain); session = root.session
    if defect == 'old_collect': root.collect = i.previous.CapturedRequest.collect.__get__(root)
    elif defect == 'old_drain': root.drain_and_finish_if_closed = i.previous.TRACKED_DRAIN.__get__(root)
    elif defect == 'wrong_observe': root.observe_after_boundary = i.request.InitialOwnerRequest.observe_after_boundary.__get__(root)
    elif defect == 'foreign_session': session = object()
    else: root._observation_advance_chain = object()
    with pytest.raises(ValueError): synthetic_constructor()(chain, session, root.client, root, {})
    assert root.session.calls == []


@pytest.mark.parametrize('kind', ['old', 'subclass', 'foreign_root'])
def test_root_drain_rejects_nonexact_chain_without_call(kind):
    root = chain_root()
    if kind == 'old': chain = object.__new__(i.previous.ActualAdvanceChain)
    elif kind == 'subclass': chain = object.__new__(type('Other', (i.ActualAdvanceChain,), {}))
    else: chain = object.__new__(i.ActualAdvanceChain)
    chain.root = object() if kind == 'foreign_root' else root
    root._observation_advance_chain = chain
    with pytest.raises(ValueError, match='missing_actual_root_chain'):
        i._actual_root_drain(root, root.session.physical_time)
    assert root.session.calls == []


def test_scheduler_and_complete_evidence_are_unchanged():
    assert changes(i.run_continuation, i.previous.run_continuation) == {'ActualAdvanceChain'}
    assert i.run_continuation.__code__ is i.previous.run_continuation.__code__
    assert i.TRACED_OBSERVE is i.previous.TRACED_OBSERVE
    assert changes(i.TRACKED_DRAIN, i.previous.TRACKED_DRAIN) == {'_actual_root_drain'}
    assert i.EVIDENCE is i.previous.EVIDENCE and i.finish_root is i.previous.finish_root
    assert i.publish_root is i.previous.publish_root
    root = prepared_root(); root.events.append({'stage': 'synthetic', 'value': {'zero': -0.0, 'tuple': (1, 1.)}})
    clock = SimpleNamespace(perf_counter_ns=lambda: 1234567)
    expected = i.private(i.previous.EVIDENCE, {'time': clock})(root)
    actual = i.private(i.EVIDENCE, {'time': clock})(root)
    assert actual.pop('encoded') == expected.pop('encoded')
    assert i.previous.codec.single.exact_tree(actual, expected)


def code_tree(code):
    yield code
    for value in code.co_consts:
        if type(value) is CodeType: yield from code_tree(value)


def test_optional_branch_uses_all_new_paths_with_complete_original_globals():
    branch = i.branch_function()
    assert branch.__code__ is campaign.run_branch.__code__
    assert branch.__closure__ is campaign.run_branch.__closure__
    assert branch.__defaults__ is campaign.run_branch.__defaults__
    assert changes(branch, campaign.run_branch) == {'CapturedRequest', 'FixedDefaultRequest',
        'run_continuation', 'call_with_recorded_collection'}
    for code in code_tree(branch.__code__):
        missing = {instruction.argval for instruction in dis.get_instructions(code)
            if instruction.opname in ('LOAD_GLOBAL', 'LOAD_NAME')
            and instruction.argval not in branch.__globals__ and not hasattr(builtins, instruction.argval)}
        assert missing == set()
    assert branch.__globals__['call_with_recorded_collection'] is i.call_with_recorded_collection
    assert branch.__globals__['_make_client'] is i.make_client
    assert branch.__globals__['request'].FixedContinuationOwner is i.TracedContinuationOwner
    assert i.branch_source_proof(branch)['new_B_wrapper_bound']


@pytest.mark.parametrize('name', ['CapturedRequest', 'FixedDefaultRequest', 'run_continuation', 'call_with_recorded_collection'])
def test_branch_proof_rejects_any_stale_old_global_including_B_wrapper(name):
    branch = i.private(i.branch_function(), {name: campaign.run_branch.__globals__[name]})
    with pytest.raises(ValueError, match='branch_binding'): i.branch_source_proof(branch)


def test_inventory_rejects_final_revalidation_retaining_old_wrapper():
    check = i.private(i.collection_inventory, {'FINAL_REVALIDATE': i.old.CapturedRequest.final_revalidate_and_submit})
    with pytest.raises(ValueError, match='callsite_binding'): check()


def test_old_globals_and_classes_remain_unchanged():
    assert i.old.call_with_recorded_collection.__globals__['captured_collection'] is i.old.captured_collection
    assert i.gated.CapturedRequest.collect.__globals__['old'] is i.old
    assert i.old.CapturedRequest.final_revalidate_and_submit.__globals__['call_with_recorded_collection'] is i.old.call_with_recorded_collection
    assert i.previous.ActualAdvanceChain.__init__.__globals__['gate'] is i.gate
    assert i.previous.run_continuation.__globals__['ActualAdvanceChain'] is i.previous.ActualAdvanceChain
    assert i.single._TEMPLATE.__globals__['_capture'] is None
