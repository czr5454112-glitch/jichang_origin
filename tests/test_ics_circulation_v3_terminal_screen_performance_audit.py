"""Independent timing-isolation and failure-boundary tests, with no large replay."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts.experiments.ics_circulation_v3 import terminal_screen_performance as perf
from scripts.experiments.ics_circulation_v3 import run_terminal_screen_performance as runner
from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator
from scripts.experiments.ics_circulation_v3.routing_cache_contract import ReplayRegionalFactory


def state():
    graph = Network({n: Node(n, 'zone', 'owner', 3) for n in ('A', 'D')},
                    {'AD': Edge('AD', 'A', 'D', 1)})
    return Snapshot(0, graph, {'tray': Tray('tray', 'A', 'loaded', 'bag')},
                    {'bag': Bag('bag', 'A', 'D', 0, 30)})


def generator(enabled):
    raw = RegionalCandidateGenerator(horizon=5, expansion_limit=100,
        deadline_ms=None, cache_contract='isolated_replay_v1')
    return perf.PerformanceGenerator(raw, enabled=enabled)


def test_algorithm_clock_excludes_identical_observer_work_in_both_arms(monkeypatch):
    clock = [0]
    original_asdict, original_copy = perf.asdict, perf.deepcopy

    def observe(value):
        clock[0] += 13
        return original_asdict(value)

    def copy(value):
        clock[0] += 7
        return original_copy(value)

    def search(self, *args):
        clock[0] += 11
        self.last_expansions, self.last_search_status = 5, 'complete'
        self.last_diagnostics = {'work_units_by_stage': {'labels': 5}}
        return ()

    def certificate(*args, **kwargs):
        clock[0] += 17
        return {'certified': False, 'status': 'not_certified', 'screen_work': 3}

    monkeypatch.setattr(perf, 'process_time_ns', lambda: clock[0])
    monkeypatch.setattr(perf, 'perf_counter_ns', lambda: clock[0])
    monkeypatch.setattr(perf, 'asdict', observe)
    monkeypatch.setattr(perf, 'deepcopy', copy)
    monkeypatch.setattr(RegionalCandidateGenerator, 'generate', search)
    monkeypatch.setattr(perf, 'terminal_capacity_certificate', certificate)
    rows = []
    for enabled in (False, True):
        wrapped = generator(enabled)
        wrapped.generate(state(), 'bag', 'tray', 4)
        rows.append(wrapped.accounting.rows[0])
    for row, expected in zip(rows, (11, 28)):
        assert row['algorithm_cpu_ns'] == row['algorithm_wall_ns'] == expected
        assert row['search_cpu_ns'] == row['search_wall_ns'] == 11
        assert row['observer_cpu_ns'] == row['observer_wall_ns'] == 27
    assert rows[0]['screen_cpu_ns'] == 0 and rows[1]['screen_cpu_ns'] == 17
    assert rows[0]['public_snapshot_sha256'] == rows[1]['public_snapshot_sha256']
    assert rows[0]['private_cache_before_sha256'] == rows[1]['private_cache_before_sha256']


def test_real_delegate_preserves_ordered_candidates_and_reports_actual_cache(monkeypatch):
    snapshot = state()
    before = deepcopy(snapshot)
    off, on = generator(False), generator(True)
    assert off.generate(snapshot, 'bag', 'tray', 4) == on.generate(snapshot, 'bag', 'tray', 4)
    assert snapshot == before
    assert off.accounting.rows[0]['private_cache_before_entry_count'] == 0
    off.generate(snapshot, 'bag', 'tray', 4)
    assert off.accounting.rows[1]['private_cache_before_entry_count'] == 1
    assert off.accounting.rows[0]['private_cache_before_sha256'] != off.accounting.rows[1]['private_cache_before_sha256']


def test_unknown_request_does_not_turn_into_a_screen_certificate():
    for enabled in (False, True):
        wrapped = generator(enabled)
        assert wrapped.generate(state(), 'absent', 'tray', 4) == ()
        row = wrapped.accounting.rows[0]
        assert row['phase'] == 'returned' and not row['certified']
        assert row['search_status'] == 'invalid_request' and row['screen_work'] == 0


def test_search_failure_retains_partial_work_and_is_not_success(monkeypatch):
    def fail(self, *args):
        self.last_expansions, self.last_search_status = 7, 'partial'
        self.last_diagnostics = {'work_units_by_stage': {'labels': 7}}
        raise RuntimeError('search fault')

    monkeypatch.setattr(RegionalCandidateGenerator, 'generate', fail)
    wrapped = generator(False)
    with pytest.raises(RuntimeError, match='search fault'):
        wrapped.generate(state(), 'bag', 'tray')
    row = wrapped.accounting.rows[0]
    assert row['phase'] == 'error' and row['error']['type'] == 'RuntimeError'
    assert row['search_work'] == 7 and row['search_status'] == 'partial'
    assert row['algorithm_cpu_ns'] >= row['search_cpu_ns'] >= 0


def test_pre_observer_failure_is_a_retained_attempt_without_algorithm_work(monkeypatch):
    monkeypatch.setattr(perf, 'asdict', lambda value: (_ for _ in ()).throw(ValueError('hash fault')))
    wrapped = generator(True)
    with pytest.raises(ValueError, match='hash fault'):
        wrapped.generate(state(), 'bag', 'tray')
    row = wrapped.accounting.rows[0]
    assert row['phase'] == 'observer_error' and row['error']['type'] == 'ValueError'
    assert row['algorithm_cpu_ns'] == row['search_work'] == 0


def test_post_observer_failure_preserves_completed_search_work(monkeypatch):
    wrapped = generator(False)

    def fail(value):
        raise ValueError('copy fault')

    monkeypatch.setattr(perf, 'deepcopy', fail)
    with pytest.raises(ValueError, match='copy fault'):
        wrapped.generate(state(), 'bag', 'tray')
    row = wrapped.accounting.rows[0]
    assert row['phase'] == 'post_observer_error'
    assert row['search_work'] == wrapped.generator.last_expansions > 0
    assert row['search_cpu_ns'] >= 0 and row['algorithm_cpu_ns'] >= row['search_cpu_ns']


def test_invalid_slow_factory_rejects_installation_before_mutating_engine():
    raw = generator(False).generator
    factory = ReplayRegionalFactory.from_generator(raw)
    slow = SimpleNamespace(controller=SimpleNamespace(generator_factory=lambda: raw))
    engine = SimpleNamespace(_generator=raw, generator_factory=factory, slow_controller=slow)
    with pytest.raises(ValueError, match='pure replay'):
        perf.install_performance_probe(engine, enabled=True)
    assert engine._generator is raw and engine.generator_factory is factory
    assert engine.slow_controller is slow


def test_pairing_uses_all_cases_and_reverses_order_without_outcome_selection():
    requests = [{'case_id': key, 'known_cost': i} for i, key in enumerate(('c', 'a', 'b'))]
    pairs = runner.fixed_pairs(requests)
    assert [(p['block'], p['case']['case_id']) for p in pairs] == [
        (block, name) for block in (0, 1) for name in ('a', 'b', 'c')]
    for i in range(3):
        assert pairs[i]['arms'] == list(reversed(pairs[i + 3]['arms']))
    for request in requests:
        request['known_cost'] *= -1000
    assert runner.fixed_pairs(requests) == pairs


def test_query_comparison_cannot_hide_changed_public_state_or_candidate_order():
    row = {key: None for key in runner.QUERY_IDENTITY}
    row['public_snapshot_sha256'], row['options'] = 'original', ['a', 'b']
    for key, replacement in [('public_snapshot_sha256', 'changed'), ('options', ['b', 'a'])]:
        changed = dict(row, **{key: replacement})
        result = runner.query_comparison([row], [changed])
        assert not result['all_exact'] and key in result['mismatches'][0]['fields']


def test_failed_first_launch_still_attempts_and_preserves_second_arm(monkeypatch, tmp_path):
    calls = []

    def launch(output, stage, pair, arm):
        calls.append(arm)
        if arm == 'off':
            raise OSError('receipt fault')
        return {'exit_code': 1, 'receipt': None, 'process_cpu_seconds': 0.25}

    monkeypatch.setattr(runner, 'launch_arm', launch)
    (tmp_path / 'pilot').mkdir()
    result = runner.pair_job(tmp_path, 'pilot', {'block': 0, 'case': {'case_id': 'one'}, 'arms': ['off', 'on']})
    assert calls == ['off', 'on']
    assert not result['all_exact'] and result['arms']['on']['process_cpu_seconds'] == 0.25
    assert result['arms']['off']['process_cpu_seconds'] is None
