"""Regressions for the independently executed 2026-10-11 audit.

These are API correctness tests, not native G31 or method-innovation claims.
"""
from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from scripts.experiments.ics_circulation_v3.model import (
    Bag, Edge, Leg, Network, Node, RouteCandidate, Snapshot, Tray)
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, Simulation
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator, clear_static_cache
from scripts.experiments.ics_circulation_v3.routing_reference import FullGraphReferenceGenerator
from scripts.experiments.ics_circulation_v3.routing_cache_contract import (
    ReplayRegionalFactory, _unwrap, enable_replay_cache, routing_cache_state)
from scripts.experiments.ics_circulation_v3.storage_contracts import (
    StorageBag, StorageSnapshot, StorageWaypointContract)
from scripts.experiments.ics_circulation_v3.storage_routing import StorageCandidateGenerator
from scripts.experiments.ics_circulation_v3.storage_terminal_screen import StorageTerminalScreenGenerator
from scripts.experiments.ics_circulation_v3.terminal_capacity_screen import (
    TerminalScreenGenerator, install_terminal_screen)
from scripts.experiments.ics_circulation_v3.network_role_labels import (
    BudgetGenerator, SearchBudget, bind_accounting)
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec, build_engine


def storage_counterexample(long_alternative=True):
    nodes = {n: Node(n, 'Z', n, capacity=4) for n in ('S', 'A', 'W', 'X', 'G')}
    edges = [Edge('a-SA', 'S', 'A', 1), Edge('b-SW', 'S', 'W', 1),
             Edge('c-AX', 'A', 'X', 1), Edge('d-WX', 'W', 'X', 1), Edge('e-XG', 'X', 'G', 1)]
    if long_alternative:
        edges.append(Edge('f-WG', 'W', 'G', 4))
    bag = StorageBag('b', 'S', 'G', 0, 20, True, StorageWaypointContract('W', 0, 0))
    return StorageSnapshot(0, Network(nodes, {e.edge_id: e for e in edges}),
                           {'t': Tray('t', 'S', 'loaded', 'b')}, {'b': bag})


def four_paths(kind='ordinary'):
    nodes = {n: Node(n, 'source' if n == 'S' else 'remote', n, capacity=4)
             for n in ('S', 'A', 'B', 'C', 'D', 'G')}
    edges = [e for n in 'ABCD' for e in (Edge('S'+n, 'S', n, 1), Edge(n+'G', n, 'G', 1))]
    bag = Bag('b', 'S', 'G', 0, 30)
    cls = Snapshot
    if kind == 'storage':
        nodes['W'] = Node('W', 'source', 'W', capacity=4)
        edges = [replace(e, source='W') if e.source == 'S' else e for e in edges]
        edges.append(Edge('SW', 'S', 'W', 1))
        bag = StorageBag('b', 'S', 'G', 0, 30, storage=StorageWaypointContract('W', 2, 0))
        cls = StorageSnapshot
    return cls(0, Network(nodes, {e.edge_id: e for e in edges}),
               {'t': Tray('t', 'S') if kind == 'empty' else Tray('t', 'S', 'loaded', 'b')},
               {} if kind == 'empty' else {'b': bag})


def regional(work=200000):
    return RegionalCandidateGenerator(horizon=10, expansion_limit=work, static_path_limit=20,
                                      deadline_ms=None, cache_contract='isolated_replay_v1')


@pytest.mark.parametrize('integer', [False, True])
@pytest.mark.parametrize('long_alternative', [False, True])
@pytest.mark.parametrize('k', [1, 2, 3])
def test_old_reference_rejects_phase_merged_storage_with_valid_earlier_witness(integer, long_alternative, k):
    state = storage_counterexample(long_alternative)
    witness = RouteCandidate('hand', 'b', 't', (Leg('b-SW', 0, 1), Leg('d-WX', 1, 2),
        Leg('e-XG', 2, 3)), 4, 4, state.version, 'hand', True, 'G')
    assert ExecutionValidator().validate(state, witness).accepted
    generator = FullGraphReferenceGenerator(horizon=6, expansion_limit=200000,
                                             deadline_ms=None, integer_ticks=integer)
    with pytest.raises(ValueError, match='^full_graph_reference:storage_contract_not_supported$'):
        generator.generate(state, 'b', 't', k)
    assert generator.last_expansions == 0
    assert generator.last_search_status == 'unsupported_storage_contract'
    assert not generator.last_diagnostics['earliest_arrival_certified']
    assert not generator.last_diagnostics['finite_horizon_exhausted']


@pytest.mark.parametrize('query_kind', ['loaded', 'empty', 'unknown_bag'])
@pytest.mark.parametrize('storage_shell', [False, True])
def test_storage_guard_is_a_model_boundary_and_clears_old_certificate(query_kind, storage_shell):
    generator = FullGraphReferenceGenerator(horizon=6, expansion_limit=200000,
                                             deadline_ms=None, integer_ticks=True)
    assert generator.generate(four_paths(), 'b', 't', 1)
    assert generator.last_diagnostics['earliest_arrival_certified']
    state = storage_counterexample()
    if storage_shell:
        state.bags['b'] = Bag('b', 'S', 'G', 0, 20)
    else:
        # A StorageBag hidden in an ordinary shell is unsupported too.
        state = Snapshot(state.now, state.network, state.trays, state.bags)
    if query_kind == 'empty':
        state.trays['t'] = Tray('t', 'S')
    with pytest.raises(ValueError, match='^full_graph_reference:storage_contract_not_supported$'):
        if query_kind == 'empty':
            generator.generate_empty(state, 't', 'G')
        else:
            generator.generate(state, 'missing' if query_kind == 'unknown_bag' else 'b', 't')
    assert not generator.last_diagnostics['earliest_arrival_certified']
    assert not generator.last_diagnostics['finite_horizon_exhausted']


@pytest.mark.parametrize('k', [1, 3, 256])
def test_ordinary_reference_keeps_earliest_exhaustion_and_budget_meanings(k):
    clear_static_cache()
    generator = FullGraphReferenceGenerator(horizon=2, expansion_limit=200000,
                                             deadline_ms=None, integer_ticks=True)
    options = generator.generate(four_paths(), 'b', 't', k)
    assert options and options[0].legs[-1].arrive == 2
    assert generator.last_diagnostics['earliest_arrival_certified']
    assert generator.last_diagnostics['finite_horizon_exhausted'] is (k > 4)
    empty = four_paths('empty')
    assert generator.generate_empty(empty, 't', 'G', k)
    short = FullGraphReferenceGenerator(horizon=1, deadline_ms=None, integer_ticks=True)
    assert short.generate(four_paths(), 'b', 't', k) == ()
    assert short.last_diagnostics['finite_horizon_exhausted']
    assert not short.last_diagnostics['earliest_arrival_certified']
    clear_static_cache()
    limited = FullGraphReferenceGenerator(horizon=6, expansion_limit=1,
                                          deadline_ms=None, integer_ticks=True)
    assert limited.generate(four_paths(), 'b', 't', k) == ()
    assert limited.last_search_status == 'expansion_budget_exhausted'
    assert not limited.last_diagnostics['finite_horizon_exhausted']


@pytest.mark.parametrize('kind', ['ordinary', 'empty', 'storage'])
@pytest.mark.parametrize('k', [None, 1, 4])
@pytest.mark.parametrize('records', [1, 200000])
@pytest.mark.parametrize('work', [1, 200000])
def test_screen_preserves_whole_ordered_pool_status_work_and_cold_hot_cache(kind, k, records, work):
    state = four_paths(kind)
    if kind == 'storage':
        base = StorageCandidateGenerator(regional(work))
        screen = StorageTerminalScreenGenerator(StorageCandidateGenerator(regional(work)), max_records=records)
    else:
        base, screen = regional(work), TerminalScreenGenerator(regional(work), max_records=records)
    method, args = ('generate_empty', (state, 't', 'G')) if kind == 'empty' else ('generate', (state, 'b', 't'))
    kwargs = {} if k is None else {'k': k}
    for _ in range(2):
        expected = getattr(base, method)(*args, **kwargs)
        actual = getattr(screen, method)(*args, **kwargs)
        assert actual == expected
        assert screen.last_search_status == base.last_search_status
        assert screen.last_expansions == base.last_expansions
        assert _unwrap(screen)._owned_topology_cache.export() == _unwrap(base)._owned_topology_cache.export()
        assert not screen.accounting.rows[-1]['certificate']['certified']
        if work == 200000:
            assert len(actual) == (1 if kind == 'empty' and k is None else (3 if k is None else k))
            assert all(ExecutionValidator().validate(state, candidate).accepted for candidate in actual)
    assert len(screen.accounting.rows) == 2


def instrumented_engine(budgeted=False):
    state = four_paths()
    state.network.edges['GS'] = Edge('GS', 'G', 'S', 1)
    state.trays['returner'] = Tray('returner', 'G')
    state.bags['waiting'] = Bag('waiting', 'S', 'G', 0, 30)
    engine = build_engine(state, (), (), ControlSpec(planning_horizon=10, slow_period=2))
    enable_replay_cache(engine)
    ledger = install_terminal_screen(engine)
    if budgeted:
        bind_accounting(engine, SearchBudget(calls=1000, work=1000000, wall_seconds=300))
    return engine, ledger


def screen_of(generator):
    return generator.generator if isinstance(generator, BudgetGenerator) else generator


def query_fast(engine):
    return engine._generator.generate(engine.state, 'b', 't', 3)


@pytest.mark.parametrize('budgeted', [False, True])
def test_actual_checkpoint_fork_shares_within_branch_and_isolates_siblings_fast_slow_factory_cache(budgeted):
    engine, ledger = instrumented_engine(budgeted)
    expected = query_fast(engine)
    assert expected and len(ledger.rows) == 1
    cached = routing_cache_state(engine)
    checkpoint = engine.checkpoint()
    saved_rows = deepcopy(screen_of(checkpoint.generator).accounting.rows)
    engine.generator_factory().generate(engine.state, 'b', 't', 1)
    engine.slow_controller(engine.state.clone())
    assert len(ledger.rows) >= 3  # fast + factory + actual predictive slow search
    assert screen_of(checkpoint.generator).accounting.rows == saved_rows
    left, right = Simulation.from_checkpoint(checkpoint), Simulation.from_checkpoint(checkpoint)
    assert routing_cache_state(left) == routing_cache_state(right) == cached
    for branch in (left, right):
        account = screen_of(branch._generator).accounting
        assert account is not ledger
        assert account is screen_of(branch.generator_factory()).accounting
        assert account is screen_of(branch.slow_controller.controller.generator_factory()).accounting
        if budgeted:
            assert branch._generator.owner is branch.generator_factory.owner
            assert branch._generator.owner is branch.slow_controller.controller.generator_factory.owner
    assert query_fast(left) == expected
    left.generator_factory().generate(left.state, 'b', 't', 1)
    left.slow_controller(left.state.clone())
    left_ledger = screen_of(left._generator).accounting
    assert len(left_ledger.rows) >= 4
    assert len(screen_of(right._generator).accounting.rows) == 1
    assert screen_of(checkpoint.generator).accounting.rows == saved_rows
    if budgeted:
        assert len(left._generator.owner.rows) == len(left_ledger.rows)
        assert left._generator.owner.work == sum(row['search_work'] for row in left_ledger.rows)
    assert left_ledger.screen_work == sum(row['certificate']['screen_work'] for row in left_ledger.rows)
    _unwrap(left._generator)._owned_topology_cache.entries.clear()
    assert routing_cache_state(right) == cached
    assert routing_cache_state(engine) == cached
    new = left.generator_factory()
    assert not _unwrap(new)._owned_topology_cache.entries
    assert _unwrap(new)._owned_topology_cache is not _unwrap(left._generator)._owned_topology_cache
    # The direct fork API must also retain the within-branch accumulator alias.
    fork = right.fork()
    fork.generator_factory().generate(fork.state, 'b', 't', 1)
    assert len(screen_of(fork._generator).accounting.rows) == 2
    assert len(screen_of(right._generator).accounting.rows) == 1


def test_checkpoint_branch_accounts_delegate_failure_and_budget_exhaustion_without_mutating_saved_ledger(monkeypatch):
    engine, ledger = instrumented_engine()
    checkpoint = engine.checkpoint()
    branch = Simulation.from_checkpoint(checkpoint)
    generator = branch.generator_factory()
    generator.generator.expansion_limit = 1
    assert generator.generate(branch.state, 'b', 't') == ()
    assert generator.accounting.rows[-1]['search_status'] == 'expansion_budget_exhausted'
    failing = branch.generator_factory()

    def fail(*args, **kwargs):
        failing.generator.last_expansions = 7
        failing.generator.last_search_status = 'injected_partial_failure'
        raise RuntimeError('injected partial failure')

    monkeypatch.setattr(failing.generator, 'generate', fail)
    with pytest.raises(RuntimeError, match='injected partial failure'):
        failing.generate(branch.state, 'b', 't')
    rows = screen_of(branch._generator).accounting.rows
    assert len(rows) == 2 and rows[-1]['phase'] == 'error' and rows[-1]['search_work'] == 7
    assert not ledger.rows and not screen_of(checkpoint.generator).accounting.rows


def test_checkpoint_does_not_newly_deepcopy_arbitrary_factory_state():
    class ExternalFactory:
        def __call__(self, horizon=None):
            return regional()

        def __deepcopy__(self, memo):
            raise AssertionError('external callback ownership was not granted')

    factory = ExternalFactory()
    engine = Simulation(four_paths(), generator_factory=factory)
    install_terminal_screen(engine)
    checkpoint = engine.checkpoint()
    assert checkpoint.generator_factory.inner_factory is factory
    assert checkpoint.generator_factory.accounting is checkpoint.generator.accounting
    assert checkpoint.generator.accounting is not engine._generator.accounting
