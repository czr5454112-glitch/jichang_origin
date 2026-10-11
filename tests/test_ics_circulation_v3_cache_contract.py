"""Observable cache isolation, exact budget boundaries and replay ownership."""
from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Reservation, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator, clear_static_cache
from scripts.experiments.ics_circulation_v3.routing_cache_contract import (
    CACHE_CONTRACT, IsolatedTopologyCache, ReplayRegionalFactory, capture_routing_cache,
    enable_replay_cache, restore_routing_cache, routing_cache_state)
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, Simulation
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec, build_engine
from scripts.experiments.ics_circulation_v3.label_stability import sustained_scenes
from scripts.experiments.ics_circulation_v3.role_coverage import (
    CursorSimulation, RoleQuota, branch_role_decision, collect_role_decisions)


def tiny_state(complex=False):
    nodes = {n: Node(n, 'z', 'p') for n in ('A', 'B')}
    edges = {'AB': Edge('AB', 'A', 'B', 1)}
    if complex:
        nodes.update(C=Node('C', 'z', 'p', can_wait=False), D=Node('D', 'z', 'q'))
        edges.update(AC=Edge('AC', 'A', 'C', 1), CB=Edge('CB', 'C', 'B', 1),
                     AD=Edge('AD', 'A', 'D', 2), DB=Edge('DB', 'D', 'B', 1))
    state = Snapshot(0, Network(nodes, edges), {'t': Tray('t', 'A', 'loaded', 'b')},
                     {'b': Bag('b', 'A', 'B', 0, 20)})
    if complex:
        state.trays['other'] = Tray('other', 'B')
        state.reservations = [Reservation('edge:AB', 0, 3, 'other'),
                              Reservation('edge:CB', 0, 3, 'other')]
    return state


def generator(limit=1000, dynamic=True, *, isolated=True):
    return RegionalCandidateGenerator(horizon=8, expansion_limit=limit, deadline_ms=None,
        dynamic_local=dynamic, cache_contract=CACHE_CONTRACT if isolated else None)


def query(g, state, k=4):
    candidates = g.generate(state, 'b', 't', k=k)
    assert all(ExecutionValidator().validate(state, candidate).accepted for candidate in candidates)
    return {'candidates': [asdict(c) for c in candidates], 'status': g.last_search_status,
            'work': g.last_expansions, 'stages': deepcopy(g.last_diagnostics['work_units_by_stage'])}


@pytest.mark.parametrize('dynamic', [False, True])
def test_legacy_global_warmth_counterexample_is_retained(dynamic):
    clear_static_cache()
    cold = query(generator(5, dynamic, isolated=False), tiny_state(), 1)
    query(generator(1000, dynamic, isolated=False), tiny_state(), 1)
    warm = query(generator(5, dynamic, isolated=False), tiny_state(), 1)
    assert len(cold['candidates']) == 0 and len(warm['candidates']) == 1
    assert cold['work'] == warm['work'] == 5


@pytest.mark.parametrize('dynamic', [False, True])
@pytest.mark.parametrize('complex', [False, True])
def test_every_cutoff_has_identical_candidates_order_status_and_work(dynamic, complex):
    state = tiny_state(complex)
    warm = generator(dynamic=dynamic)
    high = query(warm, state)
    assert high['candidates']
    # Include each possible preprocessing/search cutoff and one successful end.
    for budget in range(1, high['work'] + 2):
        warm.expansion_limit = budget
        assert query(warm, state) == query(generator(budget, dynamic), state), budget
    accounting = warm.last_diagnostics['cache_accounting']
    assert sum(accounting['reused_preprocessing_work'].values()) > 0
    assert not accounting['actual_preprocessing_work']


def test_interleaved_foreign_queries_partial_builds_and_graph_changes_are_isolated():
    state = tiny_state(True)
    original = generator(1)
    query(original, state)
    assert not original._owned_topology_cache.entries  # incomplete edge build
    original.expansion_limit = 1000
    expected = query(original, state)
    cache_before = deepcopy(original._owned_topology_cache.export())
    query(generator(isolated=False), state)
    other = generator()
    query(other, state)
    other._owned_topology_cache.entries.clear()
    clear_static_cache()
    assert original._owned_topology_cache.export() == cache_before
    assert query(original, state) == expected
    changed = state.clone()
    changed.network.edges['AB'] = replace(changed.network.edges['AB'], capacity=0)
    assert query(original, changed) == query(generator(), changed)
    assert query(original, state) == expected
    original._owned_topology_cache = IsolatedTopologyCache(capacity=1)
    query(original, changed)
    query(original, state)
    assert len(original._owned_topology_cache.entries) == 1


def test_wall_cutoffs_unsupported_generators_and_late_enable_are_rejected():
    with pytest.raises(ValueError, match='deadline_ms=None'):
        RegionalCandidateGenerator(cache_contract=CACHE_CONTRACT)
    changed = generator()
    changed.deadline_ms = 1
    with pytest.raises(ValueError, match='deadline_ms=None'):
        query(changed, tiny_state())
    legacy = generator(isolated=False)
    query(legacy, tiny_state())
    with pytest.raises(ValueError, match='before the first'):
        legacy.enable_cache_contract()
    from scripts.experiments.ics_circulation_v3.routing_reference import FullGraphReferenceGenerator
    with pytest.raises(ValueError, match='RegionalCandidateGenerator only'):
        FullGraphReferenceGenerator(deadline_ms=None).enable_cache_contract()
    scene = sustained_scenes()[0]
    engine = build_engine(scene.initial, scene.forecasts, scene.future_bags, ControlSpec())
    engine.slow_controller.controller.planning_budget_ms = 10
    with pytest.raises(ValueError, match='planning_budget_ms=None'):
        enable_replay_cache(engine)
    assert engine._generator.cache_contract is None


def test_empty_queries_have_the_same_cutoff_contract():
    state = tiny_state(True)
    state.trays['t'] = Tray('t', 'A')
    state.bags.clear()
    warm = generator()
    assert warm.generate_empty(state, 't', 'B', k=3)
    full_work = warm.last_expansions
    for budget in range(1, full_work + 2):
        cold = generator(budget)
        warm.expansion_limit = budget
        assert warm.generate_empty(state, 't', 'B', k=3) == cold.generate_empty(state, 't', 'B', k=3)
        assert (warm.last_search_status, warm.last_expansions) == (cold.last_search_status, cold.last_expansions)
        assert warm.last_diagnostics['work_units_by_stage'] == cold.last_diagnostics['work_units_by_stage']


def test_full_checkpoint_explicit_restore_and_factory_are_independent():
    engine = Simulation(tiny_state(), generator_factory=lambda horizon: generator(), reactive_empty_dispatch=False)
    enable_replay_cache(engine)
    expected = query(engine._generator, engine.state)
    warm = routing_cache_state(engine)
    checkpoint = engine.checkpoint()
    explicit = capture_routing_cache(engine)
    branch = Simulation.from_checkpoint(checkpoint)
    sibling = Simulation.from_checkpoint(checkpoint)
    engine._generator._owned_topology_cache.entries.clear()
    assert routing_cache_state(branch) == warm == routing_cache_state(sibling)
    assert query(branch._generator, branch.state) == expected
    branch._generator._owned_topology_cache.entries.clear()
    assert routing_cache_state(sibling) == warm
    restore_routing_cache(engine, explicit)
    assert routing_cache_state(engine) == warm
    engine._generator._owned_topology_cache.entries.clear()
    restore_routing_cache(engine, explicit)
    assert routing_cache_state(engine) == warm
    engine._generator.expansion_limit += 1
    with pytest.raises(ValueError, match='configuration mismatch'):
        restore_routing_cache(engine, explicit)
    a, b = checkpoint.generator_factory(), checkpoint.generator_factory()
    query(a, tiny_state())
    assert not b._owned_topology_cache.entries


class WrappedGenerator:
    def __init__(self, generator):
        self.generator = generator


class WrappedFactory:
    def __init__(self, inner_factory):
        self.inner_factory = inner_factory

    def __call__(self, **kwargs):
        return WrappedGenerator(self.inner_factory(**kwargs))


@pytest.mark.parametrize('wrap_generator', [False, True])
def test_idempotent_enable_keeps_instrumentation_factory_and_private_cache(wrap_generator):
    scene = sustained_scenes()[0]
    engine = build_engine(scene.initial, scene.forecasts, scene.future_bags, ControlSpec())
    settings = enable_replay_cache(engine)
    if wrap_generator:
        engine._generator = WrappedGenerator(engine._generator)
    engine.generator_factory = WrappedFactory(engine.generator_factory)
    engine.slow_controller.controller.generator_factory = WrappedFactory(engine.slow_controller.controller.generator_factory)
    fast, slow = engine.generator_factory, engine.slow_controller.controller.generator_factory
    assert enable_replay_cache(engine) == settings
    assert engine.generator_factory is fast and engine.slow_controller.controller.generator_factory is slow
    assert routing_cache_state(engine)['schema'] == CACHE_CONTRACT


def physical(result):
    return (result.final_snapshot, result.cost_components, result.trace, result.total_cost)


def test_cursor_replay_propagates_cache_preserves_phase_and_interleaving_cost():
    scene = replace(sustained_scenes()[0], horizon=9)
    spec = ControlSpec(planning_horizon=20)
    found = collect_role_decisions(scene, spec, quota=RoleQuota(max_samples=1), cache_contract=CACHE_CONTRACT)
    sample = found.samples[0]
    assert found.metadata['routing_cache_contract'] == CACHE_CONTRACT
    assert sample['routing_cache_checkpoint']['schema'] == CACHE_CONTRACT
    engine = CursorSimulation.from_checkpoint(sample['checkpoint'])
    before = routing_cache_state(engine)
    context = engine.visible_decision_context()
    assert context.cache_contract == CACHE_CONTRACT
    projected = CursorSimulation.from_visible(engine.state, context, (), spec,
        tuple(f for f in scene.forecasts if f.published_at <= engine.state.now))
    assert projected._generator.cache_contract == CACHE_CONTRACT
    assert projected.slow_controller.next_trigger_at == context.next_slow_trigger_at
    assert isinstance(projected.slow_controller.controller.generator_factory, ReplayRegionalFactory)
    a = branch_role_decision(sample['checkpoint'], sample['pool'][0], (), 20)
    query(generator(isolated=False), tiny_state(True))
    query(generator(), tiny_state(True))
    b = branch_role_decision(sample['checkpoint'], sample['pool'][0], (), 20)
    assert physical(a) == physical(b)
    assert routing_cache_state(CursorSimulation.from_checkpoint(sample['checkpoint'])) == before
