"""Synthetic semantic guards only; actual16-row cost work is not invoked."""
from copy import deepcopy
import io
import json
import pytest
from scripts.experiments.g31_ics_circulation import measure_bridge_saved_kernels as m


def row(value, endpoint='protocol_request'):
    return {'ordinal': 27210, 'endpoint': endpoint, 'before': 1.0, 'after': 1.0,
            'args': ['x'], 'kwargs': {'owner': 'A'}, 'result': value}


@pytest.mark.parametrize('a,b', [(1, 1.0), (True, 1), (False, 0), (0.0, -0.0),
    ({'a': 1, 'b': 2}, {'b': 2, 'a': 1}), ([1, 2], [2, 1])])
def test_changed_typed_values_and_order_rejected(a, b):
    assert not m.exact(a, b)
    assert not m.linear.semantic_equal(row(a), row(b))
    assert not m.c_compare(row(a), row(b))


@pytest.mark.parametrize('value', [None, True, 2, 2.0, -0.0, '中文\U0001F642', [],
    {'k': [{'a': 1.0, 'b': -0.0}, True, None], 'end': []}])
def test_json_copy_exact_domain_and_return_independence(value):
    source = m.decoded_tree(value)
    left, right = m.json_copy(value), m.json_copy(value)
    assert m.exact(deepcopy(value), left) and m.exact(left, right)
    assert m.decoded_tree(left).isdisjoint(source)
    assert m.decoded_tree(right).isdisjoint(m.decoded_tree(left))
    assert m.linear.semantic_equal(row(value), row(left)) == m.c_compare(row(value), row(left))


@pytest.mark.parametrize('value', [(1, 2), {0: 1}, float('nan'), float('inf'), '\ud800', '\ud800\udc00'])
def test_non_decoded_domain_rejected(value):
    with pytest.raises((ValueError, TypeError)):
        m.decoded_tree(value)


def test_custom_and_shared_mutable_alias_rejected():
    class D(dict): pass
    with pytest.raises(ValueError): m.decoded_tree(D())
    shared = []
    with pytest.raises(ValueError): m.decoded_tree([shared, shared])
    shared.append(shared)
    with pytest.raises(ValueError): m.decoded_tree(shared)


@pytest.mark.parametrize('text', ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1}{}'])
def test_strict_saved_json_rejects_malformed(text):
    with pytest.raises(ValueError): m.strict_loads(text)


def test_only_advance_native_wall_is_excluded():
    a = row({'wall_seconds': 0.1, 'status': 'reached'}, 'advance_to')
    b = deepcopy(a); b['result']['wall_seconds'] = 99.0
    assert m.linear.semantic_equal(a, b) and m.c_compare(a, b)
    assert 'wall_seconds' in a['result'] and 'wall_seconds' in b['result']
    b['result']['status'] = 'budget'
    assert not m.linear.semantic_equal(a, b) and not m.c_compare(a, b)
    a['endpoint'] = b['endpoint'] = 'protocol_request'
    assert not m.linear.semantic_equal(a, b) and not m.c_compare(a, b)


@pytest.mark.parametrize('wall', [True, -1.0, float('inf')])
def test_invalid_wall_rejected_by_both_existing_functions(wall):
    a = row({'wall_seconds': wall}, 'advance_to')
    with pytest.raises(ValueError): m.linear.semantic_equal(a, a)
    with pytest.raises(ValueError): m.c_compare(a, a)


def synthetic_records():
    records = []; tick = 1
    for kind, count in (('compare', 8), ('copy', 16)):
        for batch, arm in enumerate(m.ARMS):
            for i in range(count):
                item = {'kind': kind, 'batch': batch, 'arm': arm, 'index': i,
                    'ordinal': m.ORDINALS[i % 8], 'side': None if kind == 'compare' else ('old' if i < 8 else 'new'),
                    'started_ns': tick, 'finished_ns': tick+1, 'wall_ns': 1, 'cpu_ns': 1}
                item.update({'equal': True} if kind == 'compare' else {'result_sha256': 'a'*64})
                records.append(item); tick += 2
    return records


def test_exact_denominator_and_serial_clocks():
    summary = m.check_records(synthetic_records())
    assert summary['compare']['A']['batch_ms'] == [8e-6, 8e-6]
    assert summary['copy']['B']['batch_ms'] == [16e-6, 16e-6]


@pytest.mark.parametrize('fault', ['omit', 'reorder', 'bool_clock', 'ordinal', 'failed', 'digest', 'side'])
def test_saved_measurement_tampering_rejected(fault):
    records = synthetic_records()
    if fault == 'omit': records.pop()
    elif fault == 'reorder': records[0], records[1] = records[1], records[0]
    elif fault == 'bool_clock': records[0]['started_ns'] = True
    elif fault == 'ordinal': records[0]['ordinal'] += 1
    elif fault == 'failed': records[0]['error'] = 'failed'
    elif fault == 'digest': records[-1]['result_sha256'] = 'g'*64
    elif fault == 'side': records[-1]['side'] = 'old'
    with pytest.raises(ValueError): m.check_records(records)


def test_measurement_failure_keeps_begun_operation_without_retry(monkeypatch):
    rows = [row({}) for _ in range(16)]
    calls = []
    def fail(*_):
        calls.append(1); raise RuntimeError('first_failure')
    monkeypatch.setattr(m.linear, 'semantic_equal', fail)
    journal = io.StringIO()
    with pytest.raises(RuntimeError, match='first_failure'): m.measure(rows, journal)
    saved = [json.loads(x) for x in journal.getvalue().splitlines()]
    assert calls == [1] and len(saved) == 1
    assert saved[0]['status'] == 'unknown_failed' and saved[0]['index'] == 0


def test_manifest_selector_exact8_and_no_unmanifested_read(tmp_path):
    path = tmp_path/'manifest.jsonl'
    path.write_text(''.join(json.dumps({'path': f'{i:06d}.json.gz'})+'\n' for i in range(27218)))
    selected = m.manifest_entries(path, 27218)
    assert tuple(selected) == m.ORDINALS and len(selected) == 8
    with pytest.raises(ValueError): m.manifest_entries(path, 27219)
