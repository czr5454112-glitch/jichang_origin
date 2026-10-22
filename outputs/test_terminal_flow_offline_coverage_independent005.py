"""Independent synthetic calendar coverage cases; never reads/writes campaign ledger."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).with_name('terminal_flow_offline_budget.py')
spec = importlib.util.spec_from_file_location('independent_offline_coverage', MODULE)
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
EPOCH = datetime(2026, 10, 21, tzinfo=timezone.utc)


def at(seconds):
    return EPOCH + timedelta(seconds=seconds)


def snapshot(tmp_path, intervals, cutoff=70, end=200):
    events = []
    for index, (opened, closed) in enumerate(intervals):
        events.append(dict(at=at(opened).isoformat(), event='runner_open', runner_id=str(index)))
        if closed is not None:
            events.append(dict(at=at(closed).isoformat(), event='runner_close', runner_id=str(index)))
    events.sort(key=lambda item: item['at'])
    path = tmp_path / 'synthetic_ledger.jsonl'
    raw = ''.join(json.dumps(event) + '\n' for event in events).encode()
    path.write_bytes(raw)
    result = w.ledger_snapshot(path, at(end), coverage_cutoff=at(cutoff))
    assert path.read_bytes() == raw
    return result


@pytest.mark.parametrize('intervals,covered,gap', [
    ([], 0, 130),
    ([(-100, 50)], 0, 130),
    ([(50, 100)], 30, 100),
    ([(80, 110), (140, 170)], 60, 70),
    ([(50, None)], 130, 0),
    ([(20, 90), (120, None)], 100, 30),
    ([(70, 100), (100, 200)], 130, 0),
])
def test_clipped_interval_union_and_no_native_debit(tmp_path, intervals, covered, gap):
    result = snapshot(tmp_path, intervals)
    assert result['post_cutoff_calendar_seconds'] == 130
    assert result['post_cutoff_runner_covered_seconds'] == covered
    assert result['post_cutoff_uncovered_calendar_seconds'] == gap
    assert result['native_starts'] == 0


def test_cutoff_equal_snapshot_has_zero_new_reserve(tmp_path):
    result = snapshot(tmp_path, [(10, None)], cutoff=200)
    assert result['post_cutoff_uncovered_calendar_seconds'] == 0
    assert result['post_cutoff_runner_covered_seconds'] == 0


@pytest.mark.parametrize('rows', [
    [(80, 'runner_open', 'a'), (79, 'runner_close', 'a')],
    [(80, 'runner_open', 'a'), (90, 'runner_open', 'b')],
    [(80, 'runner_close', 'a')],
    [(201, 'runner_open', 'a')],
])
def test_malformed_time_or_interval_rejected(tmp_path, rows):
    path = tmp_path / 'synthetic_invalid_ledger.jsonl'
    path.write_text(''.join(json.dumps(dict(at=at(t).isoformat(), event=event, runner_id=runner)) + '\n'
                            for t, event, runner in rows), encoding='utf-8')
    with pytest.raises(ValueError):
        w.ledger_snapshot(path, at(200), coverage_cutoff=at(70))


def test_future_cutoff_rejected(tmp_path):
    with pytest.raises(ValueError):
        snapshot(tmp_path, [], cutoff=201)
