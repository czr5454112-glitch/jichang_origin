"""Round8 author checks: comparison scope, fixed order and paid failure work."""
from copy import deepcopy
import os
import subprocess
import sys

import pytest

from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray, Reservation
from scripts.experiments.ics_circulation_v3.runtime import INFINITY
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator
from scripts.experiments.ics_circulation_v3.terminal_capacity_screen import TerminalScreenGenerator
from scripts.experiments.ics_circulation_v3.terminal_screen_performance import PerformanceGenerator
from scripts.experiments.ics_circulation_v3 import run_terminal_screen_performance as run


def snapshot(blocked=False):
    s = Snapshot(0, Network({n: Node(n, 'z', 'p', 1) for n in ('a', 'b', 'c')},
        {'ab': Edge('ab', 'a', 'b', 1)}),
        {'t': Tray('t', 'a', 'loaded', 'bag'), 'other': Tray('other', 'c')},
        {'bag': Bag('bag', 'a', 'b', 0, 100)})
    if blocked:
        s.reservations = (Reservation('node:b', 0, INFINITY, 'other'),)
    return s


def generator():
    return RegionalCandidateGenerator(horizon=10, expansion_limit=3000, deadline_ms=None,
        dynamic_local=True, local_label_limit=3, cache_contract='isolated_replay_v1')


def test_fixed_full_pairs_reverse_order_and_never_select_by_outcome():
    requests = [{'case_id': f'{i:02}', 'cost_ignored': 100-i} for i in reversed(range(27))]
    pairs = run.fixed_pairs(requests)
    assert len(pairs) == 54
    assert [r['case']['case_id'] for r in pairs[:27]] == [f'{i:02}' for i in range(27)]
    for a, b in zip(pairs[:27], pairs[27:]):
        assert a['case'] == b['case'] and a['arms'] == list(reversed(b['arms']))
        assert a['block'] == 0 and b['block'] == 1
    assert run.fixed_pairs(list(reversed(requests))) == pairs


@pytest.mark.parametrize('blocked', [False, True])
def test_new_symmetric_arms_equal_frozen_wrapper_and_fixed_observer_schema(blocked):
    s = snapshot(blocked)
    old = TerminalScreenGenerator(generator())
    expected = old.generate(s, 'bag', 't', 4)
    wrappers = [PerformanceGenerator(generator(), enabled=enabled) for enabled in (False, True)]
    for wrapper in wrappers:
        assert wrapper.generate(s, 'bag', 't', 4) == expected
        row = wrapper.accounting.rows[0]
        assert row['algorithm_cpu_ns'] >= 0 and row['observer_cpu_ns'] >= 0
        assert row['private_cache_before_entry_count'] == 0
    left, right = [w.accounting.rows[0] for w in wrappers]
    assert set(left) == set(right)
    assert run.query_comparison([left], [right])['all_exact']
    assert left['screen_work'] == 0 and not left['certified']
    assert right['certified'] == blocked


def test_screen_skip_cache_history_can_differ_without_next_pool_drift():
    wrappers = [PerformanceGenerator(generator(), enabled=enabled) for enabled in (False, True)]
    for wrapper in wrappers:
        wrapper.generate(snapshot(True), 'bag', 't', 4)
        wrapper.generate(snapshot(False), 'bag', 't', 4)
    assert run.query_comparison(*(w.accounting.rows for w in wrappers))['all_exact']
    assert wrappers[0].accounting.rows[1]['private_cache_before_sha256'] != wrappers[1].accounting.rows[1]['private_cache_before_sha256']


def test_query_comparison_detects_snapshot_and_order_and_count():
    w = PerformanceGenerator(generator(), enabled=False)
    w.generate(snapshot(), 'bag', 't', 4)
    a = w.accounting.rows
    b = deepcopy(a)
    b[0]['public_snapshot_sha256'] = 'different'
    assert not run.query_comparison(a, b)['all_exact']
    b = deepcopy(a)
    b[0]['options'] = ()
    assert not run.query_comparison(a, b)['all_exact']
    assert not run.query_comparison(a, [])['all_exact']


def test_pair_preserves_first_failed_arm_and_still_runs_second(tmp_path, monkeypatch):
    (tmp_path / 'pilot').mkdir()
    calls = []
    def fake_launch(output, stage, pair, arm):
        calls.append(arm)
        return {'arm': arm, 'exit_code': 1, 'receipt': None, 'process_cpu_seconds': None}
    monkeypatch.setattr(run, 'launch_arm', fake_launch)
    result = run.pair_job(tmp_path, 'pilot', {'block': 0, 'case': {'case_id': 'example'}, 'arms': ['off', 'on']})
    assert calls == ['off', 'on'] and not result['all_exact']
    assert set(result['arms']) == {'on', 'off'} and result['comparison_failure']
    assert (tmp_path / 'pilot/b0__example.pair.json').exists()


def test_launch_failure_is_unknown_cpu_and_durable_receipt(tmp_path, monkeypatch):
    (tmp_path / 'pilot').mkdir()
    def fail(*args, **kwargs):
        raise OSError('injected launch failure')
    monkeypatch.setattr(run.subprocess, 'Popen', fail)
    row = run.launch_arm(tmp_path, 'pilot', {'block': 0, 'case': {'case_id': 'example'}}, 'off')
    assert row['launch_failure']['type'] == 'OSError'
    assert row['process_cpu_seconds'] is None and row['receipt'] is None
    assert (tmp_path / 'pilot/b0__example__off.launch.json').exists()


def test_full_child_os_cpu_survives_wait_and_includes_startup():
    with subprocess.Popen([sys.executable, '-c', 'sum(i*i for i in range(50000))'], stdout=subprocess.PIPE) as proc:
        assert proc.wait() == 0
        cpu, reason = run.final_process_cpu(proc)
        if os.name == 'nt':
            assert cpu > 0 and reason is None
        else:
            assert cpu is None and reason


def test_instant_observer_integration_is_detached_and_identical_for_both_arms():
    from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec, build_engine
    from scripts.experiments.ics_circulation_v3.physical_observation import InstantPhysicalCursorSimulation
    from scripts.experiments.ics_circulation_v3.routing_cache_contract import enable_replay_cache
    from scripts.experiments.ics_circulation_v3.terminal_screen_performance import install_performance_probe
    outcomes = []
    for enabled in (False, True):
        base = build_engine(snapshot(), (), (), ControlSpec(planning_horizon=20, predictive=True))
        enable_replay_cache(base)
        engine = InstantPhysicalCursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)
        accounting = install_performance_probe(engine, enabled=enabled)
        engine.advance(1)
        first = deepcopy(engine.instant_physical_ticks[0])
        for tick in range(2, 12):
            engine.advance(tick)
        assert engine.instant_physical_ticks[0] == first
        for row in engine.instant_physical_ticks:
            assert row['completed'] == {k: v for k, v in engine.state.completed.items() if v <= row['time']}
        outcomes.append((engine.instant_physical_ticks, accounting.rows))
    assert outcomes[0][0] == outcomes[1][0]
    assert run.query_comparison(outcomes[0][1], outcomes[1][1])['all_exact']


def test_pair_final_persistence_failure_keeps_arms_and_plain_recovery(tmp_path, monkeypatch):
    (tmp_path / 'pilot').mkdir()
    monkeypatch.setattr(run, 'launch_arm', lambda output, stage, pair, arm:
        {'arm': arm, 'exit_code': 1, 'receipt': None, 'process_cpu_seconds': 0.25})
    monkeypatch.setattr(run, 'write', lambda *args: (_ for _ in ()).throw(OSError('write fault')))
    result = run.pair_job(tmp_path, 'pilot', {'block': 0, 'case': {'case_id': 'one'}, 'arms': ['off', 'on']})
    assert sum(v['process_cpu_seconds'] for v in result['arms'].values()) == 0.5
    assert result['persistence_failure']['recovery_sha256']
    assert not result['all_exact']
