"""Synthetic fixture/harness/source gate only; no actual18 load or timing run."""
import copy
import gzip
import json
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import measure_complete_root_evidence_codec as m


def fixture_record():
    value = {'root_id': 'synthetic:1', 'state': 'closed_native_default_first_hop',
        'root_started_ns': 100, 'root_deadline_ns': 100000100, 'decision_cutoff_ns': 60000100,
        'choice': 'native_default', 'command_id': None, 'hop': {'prefix': [0, 1]},
        'events': [{'stage': 'synthetic', 'wall_ns': 110, 'value': {'n': 1, 'f': -0.0}}],
        'initial_endpoint_records': {'A': [{'observation': {'x': [1]}}], 'B': [{'received': {'x': [2]}}]}}
    proof = {'schema': 'synthetic_only', 'outbox': {'x': {'ack': {'delivered_at': 1.0}}},
        'trace': {'reads': [{'body_is_new': True, 'ack_changed': True}], 'ack_bodies': [{'status': 'updated'}]},
        'calls': [{'request': {'immutable': 'x'}}], 'advance_calls': [{'ordinal': 1}]}
    clock = SimpleNamespace(perf_counter_ns=lambda: 300)
    fn = m.mock.clone(m.candidate.frozen.EVIDENCE, time=clock, root_runtime_proof=lambda root: proof)
    finish = m.mock.clone(m.candidate.frozen.finish_root, time=clock, evidence=fn)
    publish = m.mock.clone(m.candidate.single.publish_root, time=clock, finish_root=finish)
    root = m.mock.root_from_evidence(value, fn)
    return publish(root, [])


def make_sample(fixture, arm):
    clock = SimpleNamespace(perf_counter_ns=lambda: 300)
    method, publish = m.bindings(arm, clock)
    root = m.root_from_fixture(fixture, method); holder = []
    result = publish(root, holder)
    assert holder[0] is result
    return result


def test_current_gate_fixture_complete_proof_not_old_v3_baseline():
    fixture = fixture_record()
    a, b = make_sample(fixture, 'A'), make_sample(fixture, 'B')
    assert m.candidate.single.exact_tree(a, b)
    assert m.candidate.single.exact_tree(m.mock.semantic_record(a), m.mock.semantic_record(fixture))
    assert b['value']['evidence']['runtime_query_proof']['advance_calls'] == [{'ordinal': 1}]
    assert m.bindings('A')[0].__code__ is m.candidate.frozen.EVIDENCE.__code__
    assert m.bindings('B')[0].__code__ is m.candidate.EVIDENCE.__code__


def test_one_fixture_never_mutated_or_aliased_by_either_arm():
    fixture = fixture_record(); before = copy.deepcopy(fixture)
    a, b = make_sample(fixture, 'A'), make_sample(fixture, 'B')
    a['value']['evidence']['runtime_query_proof']['outbox'].clear()
    assert b['value']['evidence']['runtime_query_proof']['outbox']
    assert m.candidate.single.exact_tree(fixture, before)


def test_missing_complete_query_proof_is_never_silently_reconstructed():
    fixture = fixture_record(); fixture['value']['evidence'].pop('runtime_query_proof')
    for arm in ('A', 'B'):
        with pytest.raises(ValueError, match='runtime_query_proof_missing'):
            m.root_from_fixture(fixture, m.bindings(arm)[0])


def test_fixed_denominator_order_and_shared_budget():
    rows = m.declarations([str(i) for i in range(18)])
    assert len(rows) == 72 and ''.join(x['arm'] for x in rows) == 'ABBA'*18
    assert [x['position'] for x in rows] == [0, 1, 2, 3]*18 and m.LIMIT == 240.
    with pytest.raises(ValueError, match='codec_mock_arm'): m.bindings('unregistered')


def synthetic_saved(directory):
    record = fixture_record()
    inputs = {str(n): copy.deepcopy(record) for n in range(18)}
    plan = {'input_raw': {key: {} for key in inputs}, 'row_order': m.declarations(inputs)}
    ledger = []
    (directory/'raw').mkdir()
    for index, declared in enumerate(plan['row_order']):
        path = directory/'raw'/f'{index:03d}.json.gz'
        with gzip.open(path, 'wt', encoding='utf8') as stream:
            json.dump({'declaration': declared, 'record': record}, stream)
        ledger.append({**declared, 'status': 'saved', 'started_ns': 200, 'finished_ns': 400,
            'elapsed_ns': 200, 'raw': m.c.reference(path), 'gzip_hash_elapsed_ns': 0})
    m.c.write(directory/'ledger.json', ledger)
    return plan, inputs, ledger


def test_saved_all72_full_ordered_semantics_and_negative_medians_retained(tmp_path):
    plan, inputs, ledger = synthetic_saved(tmp_path)
    report = m.verify_outputs(tmp_path, plan, inputs)
    assert len(report['samples']) == 72 and len(report['negative_or_equal_root_medians']) == 18
    assert report['summary_ms']['A']['count'] == report['summary_ms']['B']['count'] == 36
    assert report['native_calls'] == report['predictor_calls'] == 0
    assert report['complete_native_root_100ms_certified'] is False


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'row_order', 'clock', 'unknown', 'extra_field'])
def test_saved_ledger_denominator_order_unknown_and_clocks_fail_closed(tmp_path, mutation):
    plan, inputs, ledger = synthetic_saved(tmp_path)
    if mutation == 'missing': ledger.pop()
    elif mutation == 'extra': ledger.append(ledger[-1])
    elif mutation == 'row_order': ledger[0], ledger[1] = ledger[1], ledger[0]
    elif mutation == 'clock': ledger[0]['elapsed_ns'] += 1
    elif mutation == 'unknown': ledger[0]['status'] = 'unknown_in_progress'
    else: ledger[0]['hidden'] = 'unverified'
    m.c.write(tmp_path/'ledger.json', ledger)
    with pytest.raises(ValueError): m.verify_outputs(tmp_path, plan, inputs)


@pytest.mark.parametrize('mutation', ['query', 'int_float', 'signed_zero', 'key_order', 'event_clock', 'extra_outer'])
def test_saved_every_proof_field_scalar_order_and_historical_clock_checked(tmp_path, mutation):
    plan, inputs, ledger = synthetic_saved(tmp_path)
    path = tmp_path/'raw'/'000.json.gz'
    with gzip.open(path, 'rt', encoding='utf8') as stream: data = json.load(stream)
    value = data['record']['value']['evidence']; event = value['events'][0]
    if mutation == 'query': value['runtime_query_proof']['trace']['reads'].clear()
    elif mutation == 'int_float': event['value']['n'] = 1.0
    elif mutation == 'signed_zero': event['value']['f'] = 0.0
    elif mutation == 'key_order': event['value'] = dict(reversed(list(event['value'].items())))
    elif mutation == 'event_clock': event['wall_ns'] += 1
    else: data['unlisted'] = 1
    with gzip.open(path, 'wt', encoding='utf8') as stream: json.dump(data, stream)
    ledger[0]['raw'] = m.c.reference(path); m.c.write(tmp_path/'ledger.json', ledger)
    with pytest.raises(ValueError): m.verify_outputs(tmp_path, plan, inputs)


def test_loading_keeps_exact_root_record_and_rejects_wrong_hash(tmp_path):
    path = tmp_path/'small.json.gz'; record = fixture_record()
    with gzip.open(path, 'wt', encoding='utf8') as stream: json.dump({'root_records': [record]}, stream)
    plan = {'input_raw': {'fixture': m.c.reference(path)}}
    loaded = m.load_inputs(plan)
    assert m.candidate.single.exact_tree(loaded['fixture'], record)
    plan['input_raw']['fixture']['sha256'] = '0'*64
    with pytest.raises(ValueError, match='input_raw_changed'): m.load_inputs(plan)
