"""A passive callback archive neither invents a query nor changes decisions."""
import gzip
import json

import pytest

from scripts.experiments.g31_ics_circulation.foundation_airport_observations import Recorder, CONTRACT


def test_window_bounds_actual_inputs_same_decision_object_and_residual_calls(tmp_path):
    recorder = Recorder(tmp_path / 'actual.jsonl.gz', branch='C00', business_version='test')
    called = []
    original_decision = {'intents': [{'request': 'unchanged'}], 'includes_wait': True}
    def planner(observation, **options):
        called.append((observation, options))
        return original_decision
    wrapped = recorder.wrap(planner)
    for now in (43199., 43200., 43200., 59400., 59401.):
        observation = {'owner_id': 'A', 'now': now, 'public': ['only_actual']}
        assert wrapped(observation, request_prefix='actual:residual') is original_decision
        assert called[-1][0] is observation
    original_decision['intents'].clear()
    recorder.close()
    rows = [json.loads(line) for line in gzip.decompress(recorder.path.read_bytes()).splitlines()]
    assert len(called) == 5 and len(rows) == 3
    assert [row['now'] for row in rows] == [43200., 43200., 59400.]
    assert [row['sequence'] for row in rows] == [0, 1, 2]
    assert all(row['decision']['intents'] == [{'request': 'unchanged'}] for row in rows)
    assert all(row['policy_options'] == {'request_prefix': 'actual:residual'} for row in rows)
    assert all(row['candidate_conditional_labels'] is None and row['readonly'] for row in rows)
    assert recorder.summary()['record_count'] == 3
    assert CONTRACT['extra_native_queries'] == 0


def test_empty_window_never_calls_extra_policy_and_failed_policy_has_no_fabricated_decision(tmp_path):
    recorder = Recorder(tmp_path / 'empty.jsonl.gz', branch='C10', business_version='test')
    calls = []
    def failing(observation, **options):
        calls.append(observation)
        raise ValueError('actual policy failed')
    with pytest.raises(ValueError, match='actual policy failed'):
        recorder.wrap(failing)({'owner_id': 'A', 'now': 43200.})
    recorder.close()
    assert len(calls) == 1 and recorder.summary()['record_count'] == 0
    assert recorder.path.read_bytes() == b''
