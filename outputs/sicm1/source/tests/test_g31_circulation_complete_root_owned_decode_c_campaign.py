"""Synthetic harness checks only; no real fixture, extension or model calls."""
import copy
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.experiments.g31_ics_circulation import measure_complete_root_owned_decode_c as m
from test_g31_circulation_complete_root_evidence_codec_campaign import fixture_record, synthetic_saved


def pair(normalize=None):
    normalize = normalize or m.binding.owned.normalization.normalize
    a = m.old.binding._bind_provider(normalize)
    return SimpleNamespace(A=a, B=m.binding._compose(a), proof={'synthetic_not_C_authority': True})


def sample(record, arm, functions):
    method, publish = m.bindings(arm, functions, SimpleNamespace(perf_counter_ns=lambda: 300))
    root = m.legacy.root_from_fixture(record, method); holder = []
    result = publish(root, holder)
    assert holder == [result] and holder[0] is result
    return result


def test_same_normalizer_complete_A_and_B_outputs_and_call_counts():
    calls = []
    def normalize(value):
        calls.append(value)
        return m.binding.owned.normalization.normalize(value)
    functions = pair(normalize); record = fixture_record()
    a, b = sample(record, 'A', functions), sample(record, 'B', functions)
    assert m.parity.exact(a, b) and len(calls) == 2
    assert m.parity.exact(m.mock.semantic_record(a), m.mock.semantic_record(record))
    assert m.bindings('A', functions)[0].__code__ is m.old.binding.frozen.EVIDENCE.__code__
    assert m.bindings('B', functions)[0].__code__ is m.binding.owned.EVIDENCE.__code__


@pytest.mark.parametrize('arm,functions', [('A', None), ('B', None), ('C', None)])
def test_both_arms_require_explicit_pair_and_known_name(arm, functions):
    with pytest.raises(ValueError, match='owned_C_pair_required'): m.bindings(arm, functions)


def test_two_different_provider_facades_are_not_a_fair_pair():
    functions = pair()
    functions.B.EVIDENCE = m.private(functions.B.EVIDENCE,
        {'normalization': SimpleNamespace(normalize=m.binding.owned.normalization.normalize)})
    with pytest.raises(ValueError, match='same_provider'): m.bindings('B', functions)


def test_all_original_worker_code_globals_preflight_and_launcher_retained():
    proof = m.worker_source_proof()
    assert proof['original_worker_code_identity'] and proof['original_launcher_code_identity']
    assert m.worker.__code__ is m.old.worker.__code__
    assert m.worker.__globals__['direct_support'] is m.old.direct_support
    assert m.worker.__globals__['load_inputs'] is m.old.load_inputs
    assert m.worker.__globals__['binding'].bind is m.binding.bind
    assert m.main.__globals__['MODULE'] == m.MODULE
    assert m.main.__globals__['worker'] is m.worker and m.main.__globals__['prepare'] is m.prepare


def test_fixture_alias_and_unknown_state_are_preserved():
    functions = pair(); original = fixture_record(); before = copy.deepcopy(original)
    unknown = copy.deepcopy(original); unknown['value']['evidence']['state'] = 'unknown_collection'
    old, new = sample(unknown, 'A', functions), sample(unknown, 'B', functions)
    assert m.parity.exact(old, new) and new['closed'] is False
    new['value']['evidence']['events'].clear()
    assert old['value']['evidence']['events']
    assert m.parity.exact(original, before)


def test_error_from_provider_is_not_an_optimized_success():
    error = MemoryError('synthetic_provider_resource_failure')
    def fail(value): raise error
    functions = pair(fail)
    for arm in ('A', 'B'):
        with pytest.raises(MemoryError) as got: sample(fixture_record(), arm, functions)
        assert got.value is error


def test_fixed_whole240_ABBA72_and_unchanged_checker():
    rows = m.declarations([str(n) for n in range(18)])
    assert len(rows) == 72 and ''.join(r['arm'] for r in rows) == 'ABBA'*18
    assert [r['position'] for r in rows] == [0, 1, 2, 3]*18 and m.LIMIT == 240.0
    assert m.load_inputs is m.old.load_inputs


def test_saved_all72_full_records_and_negative_medians_remain(tmp_path):
    plan, inputs, ledger = synthetic_saved(tmp_path)
    result = m.verify_outputs(tmp_path, plan, inputs)
    assert len(result['samples']) == 72 and len(result['negative_or_equal_root_medians']) == 18
    assert result['summary_ms']['A']['count'] == result['summary_ms']['B']['count'] == 36
    assert result['complete_native_root_100ms_certified'] is False


@pytest.mark.parametrize('mutation', ['missing', 'reorder', 'clock', 'unknown', 'extra'])
def test_saved_ledger_all_guards_retained(tmp_path, mutation):
    plan, inputs, ledger = synthetic_saved(tmp_path)
    if mutation == 'missing': ledger.pop()
    elif mutation == 'reorder': ledger[0], ledger[1] = ledger[1], ledger[0]
    elif mutation == 'clock': ledger[0]['elapsed_ns'] += 1
    elif mutation == 'unknown': ledger[0]['status'] = 'unknown_in_progress'
    else: ledger[0]['extra'] = True
    m.write(tmp_path/'ledger.json', ledger)
    with pytest.raises(ValueError): m.verify_outputs(tmp_path, plan, inputs)


@pytest.mark.parametrize('mutation', ['proof', 'int_float', 'signed_zero', 'order', 'deadline', 'event_clock', 'outer'])
def test_saved_complete_ordered_scalar_proof_and_clock_checks_retained(tmp_path, mutation):
    plan, inputs, ledger = synthetic_saved(tmp_path); path = tmp_path/'raw/000.json.gz'
    with gzip.open(path, 'rt', encoding='utf8') as stream: data = json.load(stream)
    value = data['record']['value']['evidence']; event = value['events'][0]
    if mutation == 'proof': value['runtime_query_proof']['calls'].clear()
    elif mutation == 'int_float': event['value']['n'] = 1.0
    elif mutation == 'signed_zero': event['value']['f'] = 0.0
    elif mutation == 'order': event['value'] = dict(reversed(list(event['value'].items())))
    elif mutation == 'deadline': value['root_deadline_ns'] += 1
    elif mutation == 'event_clock': event['wall_ns'] += 1
    else: data['record']['unlisted'] = True
    with gzip.open(path, 'wt', encoding='utf8') as stream: json.dump(data, stream)
    ledger[0]['raw'] = m.legacy.c.reference(path); m.write(tmp_path/'ledger.json', ledger)
    with pytest.raises(ValueError): m.verify_outputs(tmp_path, plan, inputs)


def test_verify_saved_calls_one_full_pin_check_and_one_input_load(tmp_path):
    plan, inputs, ledger = synthetic_saved(tmp_path); calls = []
    def pins(output, expected):
        calls.append('pins'); assert expected == 'expected'; return plan
    def load(got):
        calls.append('load'); assert got is plan; return inputs
    check = m.private(m.verify_saved, {'verify_pins': pins, 'load_inputs': load})
    result = check(tmp_path, 'expected')
    assert calls == ['pins', 'load'] and len(result['samples']) == 72


def test_direct_support_still_requires_the_actual_builtin():
    with pytest.raises(ValueError, match='builtin_identity'):
        m.old.direct_support(fixture_record(), SimpleNamespace(_try=lambda value: value, module=SimpleNamespace()))


def test_full_worker_functional_wiring_72_synthetic_rows_without_C(tmp_path):
    calls = {'normalize': 0, 'support': [], 'pins': [], 'bind': 0}
    def normalize(value):
        calls['normalize'] += 1
        return m.binding.owned.normalization.normalize(value)
    functions = pair(normalize)
    inputs = {str(i): fixture_record() for i in range(18)}
    # Construct complete valid unknown records, not merely a mutated state bit.
    for key in ('16', '17'):
        inputs[key]['value']['evidence']['state'] = 'unknown_collection'
        inputs[key] = sample(inputs[key], 'A', functions)
    calls['normalize'] = 0
    plan = {'input_raw': {key: {} for key in inputs}, 'row_order': m.declarations(inputs),
        'source_sha256': {str(Path(mod.__file__).resolve()): 'synthetic'
                         for mod in (m.old.binding.provider.original, m.old.binding.provider.original.wire)},
        'binary': {'path': 'never_loaded.pyd', 'sha256': 'synthetic'}}
    m.write(tmp_path/'ledger.json', [{**row, 'status': 'unknown_unexecuted'} for row in plan['row_order']])
    def pins(output, expected): calls['pins'].append(expected); return plan
    def support(record, candidate):
        calls['support'].append(record)
        return {'direct_C_supported': True, 'exact_and_new_owned_tree': True,
                'synthetic_no_C_called': True}
    def bind(candidate): calls['bind'] += 1; return functions
    provider = SimpleNamespace(original=m.old.binding.provider.original,
        load_candidate=lambda *args: SimpleNamespace(synthetic=True))
    run = m.private(m.worker, {'verify_pins': pins, 'loaded_sources': lambda plan: {},
        'binding': SimpleNamespace(provider=provider, bind=bind), 'direct_support': support,
        'load_inputs': lambda plan: inputs, 'parity': SimpleNamespace(loaded_runtime=lambda plan: {'synthetic': True})})
    run(tmp_path, 'synthetic_expected')
    assert calls['normalize'] == 72 and len(calls['support']) == 18 and calls['bind'] == 1
    assert calls['pins'] == ['synthetic_expected', 'synthetic_expected']
    report = m.read(tmp_path/'report.json')
    assert len(report['samples']) == 72 and report['native_calls'] == report['predictor_calls'] == 0
    assert m.read(tmp_path/'receipt.json')['source_changed'] == []
    for ordinal in (64, 65, 68, 71):
        with gzip.open(tmp_path/'raw'/f'{ordinal:03d}.json.gz', 'rt', encoding='utf8') as stream: data = json.load(stream)
        assert data['record']['closed'] is False


def test_worker_first_provider_failure_keeps_full_unknown_ledger(tmp_path):
    plan = {'source_sha256': {str(Path(mod.__file__).resolve()): 'synthetic'
        for mod in (m.old.binding.provider.original, m.old.binding.provider.original.wire)},
        'binary': {'path': 'never_loaded', 'sha256': 'synthetic'}}
    ledger = [{**row, 'status': 'unknown_unexecuted'} for row in m.declarations([str(i) for i in range(18)])]
    m.write(tmp_path/'ledger.json', ledger)
    def fail(*args): raise MemoryError('synthetic_C_load_failure')
    provider = SimpleNamespace(original=m.old.binding.provider.original, load_candidate=fail)
    run = m.private(m.worker, {'verify_pins': lambda *args: plan, 'loaded_sources': lambda plan: {},
                              'binding': SimpleNamespace(provider=provider)})
    with pytest.raises(MemoryError, match='synthetic_C_load_failure'): run(tmp_path, 'expected')
    assert m.read(tmp_path/'ledger.json') == ledger
    assert m.read(tmp_path/'failure.json')['status'] == 'failed_or_unknown'
    assert not (tmp_path/'receipt.json').exists()
