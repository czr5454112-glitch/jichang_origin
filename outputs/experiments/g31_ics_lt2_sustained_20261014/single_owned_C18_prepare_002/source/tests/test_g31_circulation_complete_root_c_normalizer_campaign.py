"""Synthetic full-publisher harness gates; no C load/saved18/model/native."""
import copy
import gzip
import json
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import measure_complete_root_c_normalizer as m
from test_g31_circulation_complete_root_evidence_codec_campaign import fixture_record, synthetic_saved


def sample(record, arm, binding=None):
    method, publish = m.bindings(arm, binding, SimpleNamespace(perf_counter_ns=lambda: 300))
    root = m.legacy.root_from_fixture(record, method); holder = []
    result = publish(root, holder)
    assert holder[0] is result
    return result


def test_A_is_actual_entry_codec_and_B_only_provider_full_output_equal():
    record = fixture_record(); calls = []
    def normalize(value):
        calls.append(list(value)); return m.binding.provider.original.normalize(value)
    bound = m.binding._bind_provider(normalize)
    a, b = sample(record, 'A'), sample(record, 'B', bound)
    assert m.parity.exact(a, b)
    assert m.parity.exact(m.mock.semantic_record(a), m.mock.semantic_record(record))
    assert len(calls) == 1 and calls[0][-1] == 'runtime_query_proof'
    assert m.bindings('A')[0].__code__ is m.binding.frozen.EVIDENCE.__code__
    assert m.binding.frozen.__name__.endswith('initial_owner_route_entry_codec_integration')


def test_payload_preflight_checks_actual_normalization_domain_and_isolation():
    original = m.binding.provider.original.normalize
    value = {'a': (1, -0.0), 'b': {'c': [True]}}
    result, proof = m.check_payload(value, original, original)
    assert result == {'a': [1, -0.0], 'b': {'c': [True]}}
    assert proof['direct_C_supported'] and proof['exact_and_new_owned_tree']
    result['b']['c'].clear()
    assert value['b']['c'] == [True]


@pytest.mark.parametrize('failure', ['unsupported', 'same_input', 'int_float', 'signed_zero', 'order', 'extra', 'alias'])
def test_payload_unsupported_or_nonexact_or_shared_fails(failure):
    original = m.binding.provider.original.normalize
    value = {'n': 1, 'f': -0.0, 'children': [[], []]}
    def attempt(raw):
        if failure == 'unsupported': return NotImplemented
        if failure == 'same_input': return raw
        result = original(raw)
        if failure == 'int_float': result['n'] = 1.0
        elif failure == 'signed_zero': result['f'] = 0.0
        elif failure == 'order': result = dict(reversed(list(result.items())))
        elif failure == 'extra': result['hidden'] = None
        elif failure == 'alias': result['children'][1] = result['children'][0]
        return result
    with pytest.raises(ValueError): m.check_payload(value, attempt, original)


def test_C_support_cannot_be_attested_by_python_fake_builtin():
    with pytest.raises(ValueError, match='builtin_identity'):
        m.direct_support(fixture_record(), SimpleNamespace(_try=lambda value: value, module=SimpleNamespace()))


def test_all_calls_isolated_and_fixture_unchanged():
    record = fixture_record(); before = copy.deepcopy(record)
    b = m.binding._bind_provider(m.binding.provider.original.normalize)
    a, one, two = sample(record, 'A'), sample(record, 'B', b), sample(record, 'B', b)
    one['value']['evidence']['events'].clear()
    assert a['value']['evidence']['events'] and two['value']['evidence']['events']
    assert m.parity.exact(record, before)


def test_candidate_errors_preserved_and_not_silently_fallback():
    failure = ValueError('synthetic-provider-failure')
    def normalize(value): raise failure
    with pytest.raises(ValueError) as error:
        sample(fixture_record(), 'B', m.binding._bind_provider(normalize))
    assert error.value is failure


def test_fixed18_ABBA72_budget_and_no_unknown_arm():
    values = m.declarations([str(n) for n in range(18)])
    assert len(values) == 72 and ''.join(row['arm'] for row in values) == 'ABBA'*18
    assert m.LIMIT == 240.0
    with pytest.raises(ValueError): m.bindings('B')
    with pytest.raises(ValueError): m.bindings('C')


def test_saved_checker_retains_all72_and_negative_cases(tmp_path):
    plan, inputs, _ = synthetic_saved(tmp_path)
    report = m.verify_outputs(tmp_path, plan, inputs)
    assert len(report['samples']) == 72 and len(report['negative_or_equal_root_medians']) == 18
    assert report['summary_ms']['A']['count'] == report['summary_ms']['B']['count'] == 36
    assert report['complete_native_root_100ms_certified'] is False


@pytest.mark.parametrize('mutation', ['missing', 'reorder', 'clock', 'unknown', 'extra'])
def test_saved_ledger_negative(tmp_path, mutation):
    plan, inputs, ledger = synthetic_saved(tmp_path)
    if mutation == 'missing': ledger.pop()
    elif mutation == 'reorder': ledger[0], ledger[1] = ledger[1], ledger[0]
    elif mutation == 'clock': ledger[0]['elapsed_ns'] += 1
    elif mutation == 'unknown': ledger[0]['status'] = 'unknown_in_progress'
    else: ledger[0]['hidden'] = 1
    m.write(tmp_path/'ledger.json', ledger)
    with pytest.raises(ValueError): m.verify_outputs(tmp_path, plan, inputs)


@pytest.mark.parametrize('mutation', ['proof', 'int_float', 'signed_zero', 'order', 'deadline', 'event_clock', 'outer'])
def test_complete_saved_fields_are_not_filtered(tmp_path, mutation):
    plan, inputs, ledger = synthetic_saved(tmp_path); path = tmp_path/'raw/000.json.gz'
    with gzip.open(path, 'rt', encoding='utf8') as stream: saved = json.load(stream)
    value = saved['record']['value']['evidence']; event = value['events'][0]
    if mutation == 'proof': value['runtime_query_proof']['calls'].clear()
    elif mutation == 'int_float': event['value']['n'] = 1.0
    elif mutation == 'signed_zero': event['value']['f'] = 0.0
    elif mutation == 'order': event['value'] = dict(reversed(list(event['value'].items())))
    elif mutation == 'deadline': value['root_deadline_ns'] += 1
    elif mutation == 'event_clock': event['wall_ns'] += 1
    else: saved['record']['unlisted'] = True
    with gzip.open(path, 'wt', encoding='utf8') as stream: json.dump(saved, stream)
    ledger[0]['raw'] = m.legacy.c.reference(path); m.write(tmp_path/'ledger.json', ledger)
    with pytest.raises(ValueError): m.verify_outputs(tmp_path, plan, inputs)


def test_load_only_complete_record_no_field_projection(tmp_path):
    record = fixture_record(); path = tmp_path/'input.json.gz'
    with gzip.open(path, 'wt', encoding='utf8') as stream: json.dump({'root_records': [record]}, stream)
    loaded = m.load_inputs({'input_raw': {'x': m.legacy.c.reference(path)}})
    assert m.parity.exact(loaded['x'], record)
