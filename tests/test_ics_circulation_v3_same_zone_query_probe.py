from copy import deepcopy
from dataclasses import asdict
import pickle

import pytest

from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.network_full_cycle import compare_old_result
from scripts.experiments.ics_circulation_v3.network_role_labels import (
    BudgetFactory, BudgetGenerator, SearchAccounting, SearchBudget, bind_accounting)
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec, build_engine
from scripts.experiments.ics_circulation_v3.role_coverage import CursorSimulation
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator
from scripts.experiments.ics_circulation_v3.routing_cache_contract import (
    ReplayRegionalFactory, enable_replay_cache, routing_cache_state)
from scripts.experiments.ics_circulation_v3.same_zone_query_probe import (
    QueryProbeFactory, QueryProbeGenerator, detach_query_probe, install_query_probe)


def state_fixture():
    net = Network({n: Node(n, 'zone', 'owner', 2) for n in ('L', 'J', 'U')},
                  {'LJ': Edge('LJ', 'L', 'J', 2), 'JU': Edge('JU', 'J', 'U', 2),
                   'UL': Edge('UL', 'U', 'L', 2)})
    return Snapshot(0, net, {'tray': Tray('tray', 'L', 'loaded', 'seen')},
                    {'seen': Bag('seen', 'L', 'U', 0, 30)})


def engine_fixture():
    initial = state_fixture()
    base = build_engine(initial, (), (Bag('hidden_later', 'L', 'U', 30, 90),),
                        ControlSpec(planning_horizon=20, predictive=True))
    enable_replay_cache(base)
    engine = CursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)
    owner = bind_accounting(engine, SearchBudget(100, 100000, 30))
    return engine, owner


class FakeGenerator:
    def __init__(self, result=(), error=False):
        self.result, self.error = result, error
        self.last_expansions, self.last_search_status, self.last_diagnostics = 0, 'not_started', {}

    def generate(self, state, bag_id, tray_id, k=4):
        self.last_expansions = 7
        self.last_diagnostics = {'partial_work': 7}
        self.last_search_status = 'injected' if self.error else 'returned'
        if self.error:
            raise RuntimeError('injected query failure')
        return self.result

    def generate_empty(self, state, tray_id, destination, k=1):
        return self.generate(state, None, tray_id, k)


def test_raw_pool_identity_and_input_state_are_unchanged():
    state = state_fixture(); original = asdict(state); pool = ({'payload': 1},)
    inner = FakeGenerator(pool); sink = []
    probe = QueryProbeGenerator(inner, sink, 'fast_generator')
    assert probe.generate(state, 'seen', 'tray', k=4) is pool
    assert asdict(state) == original and len(sink) == 1
    row = sink[0]
    assert row['phase'] == 'returned' and row['requested_k'] == 4
    assert row['raw_candidate_count'] == 1 and row['options'] == pool
    row['options'][0]['payload'] = 9
    row['snapshot'].trays.clear()
    assert pool[0]['payload'] == 1 and state.trays


def test_zero_pool_remains_zero_and_records_budget_not_infeasibility():
    state = state_fixture(); sink = []
    generator = RegionalCandidateGenerator(horizon=20, expansion_limit=1, deadline_ms=None,
        dynamic_local=True, cache_contract='isolated_replay_v1')
    probe = QueryProbeGenerator(generator, sink, 'fast_generator')
    assert probe.generate(state, 'seen', 'tray', 4) == ()
    assert sink[0]['last_search_status'] == 'expansion_budget_exhausted'
    assert sink[0]['raw_candidate_count'] == 0


def test_query_failure_is_rethrown_with_entered_record_and_partial_diagnostics():
    sink = []; probe = QueryProbeGenerator(FakeGenerator(error=True), sink, 'slow_factory')
    with pytest.raises(RuntimeError, match='injected query failure'):
        probe.generate(state_fixture(), 'seen', 'tray')
    assert sink[0]['phase'] == 'error'
    assert sink[0]['last_diagnostics'] == {'partial_work': 7}
    assert sink[0]['last_expansions'] == 7
    assert 'options' not in sink[0]


@pytest.mark.parametrize('copy_kind', ['deepcopy', 'pickle'])
def test_copy_strips_only_probe_and_retains_shared_owner_and_cache(copy_kind):
    owner = SearchAccounting(SearchBudget(100, 100000, 30)); sink = []
    factory = ReplayRegionalFactory(20, 3000, 8, True, 3)
    generator = BudgetGenerator(factory(), owner)
    probe = QueryProbeGenerator(generator, sink, 'fast_generator')
    probe.generate(state_fixture(), 'seen', 'tray', 4)
    probe_factory = QueryProbeFactory(BudgetFactory(factory, owner), sink, 'slow_factory')
    original_cache = generator.generator._owned_topology_cache.export()
    pair = (probe, probe_factory)
    copied = deepcopy(pair) if copy_kind == 'deepcopy' else pickle.loads(pickle.dumps(pair))
    a, b = copied
    assert type(a) is BudgetGenerator and type(b) is BudgetFactory
    assert a.owner is b.owner and a.owner is not owner
    assert a.generator._owned_topology_cache.export() == original_cache
    assert len(owner.rows) == 1 and len(sink) == 1
    assert isinstance(probe, QueryProbeGenerator) and probe.sink is sink


def test_full_small_execution_matches_without_probe_and_excludes_hidden_tape():
    old, old_owner = engine_fixture(); new, new_owner = engine_fixture(); sink = []
    install_query_probe(new, sink)
    old.advance(12); new.advance(12)
    assert compare_old_result(old.result(), new.result())['equal']
    assert old_owner.rows == new_owner.rows
    assert routing_cache_state(old) == routing_cache_state(new)
    assert len(sink) == len(new_owner.rows) > 0
    assert all('hidden_later' not in row['snapshot'].bags for row in sink)
    assert all(row['phase'] == 'returned' for row in sink)
    assert any(row['callsite'] == 'engine_loaded' for row in sink)
    assert all(not hasattr(row['snapshot'], '_arrivals') for row in sink)


def test_checkpoint_clone_drops_sink_and_rebinding_keeps_live_records_separate():
    engine, owner = engine_fixture(); sink = []; captured = []
    install_query_probe(engine, sink)
    engine._decision_callback = lambda current, tray, options: captured.append(current.checkpoint().clone())
    engine.advance(1)
    checkpoint = captured[0]
    assert not isinstance(checkpoint.base.generator, QueryProbeGenerator)
    assert not isinstance(checkpoint.base.generator_factory, QueryProbeFactory)
    assert not isinstance(checkpoint.base.slow_controller.controller.generator_factory, QueryProbeFactory)
    before = len(sink); old_rows = len(owner.rows)
    restored = CursorSimulation.from_checkpoint(checkpoint)
    restored_owner = bind_accounting(restored, SearchBudget(100, 100000, 30))
    restored.advance(12)
    assert len(sink) == before and len(owner.rows) == old_rows
    assert restored_owner.rows


def test_invalid_request_semantics_are_preserved():
    state = state_fixture(); sink = []
    gen = RegionalCandidateGenerator(horizon=20, deadline_ms=None)
    probe = QueryProbeGenerator(gen, sink, 'fast_generator')
    assert probe.generate(state, 'missing', 'tray') == ()
    assert sink[0]['destination'] is None
    assert sink[0]['last_search_status'] == 'invalid_request'


def test_diagnostics_and_configuration_forward_through_budget_wrapper():
    engine, _ = engine_fixture(); sink = []
    install_query_probe(engine, sink)
    assert engine._generator.horizon == 20
    engine._generator.generate(engine.state, 'seen', 'tray', 4)
    assert engine._generator.last_diagnostics == sink[-1]['last_diagnostics']
    assert engine._generator.last_expansions == sink[-1]['last_expansions']


def test_detach_is_idempotent_and_does_not_copy_or_clear_live_sink():
    engine, owner = engine_fixture(); sink = []
    original_generator = engine._generator; original_factory = engine.generator_factory
    install_query_probe(engine, sink); engine.advance(1)
    before = len(sink)
    detach_query_probe(engine); detach_query_probe(engine)
    assert engine._generator is original_generator and engine.generator_factory is original_factory
    assert engine._generator.owner is owner and len(sink) == before


def test_rejected_install_leaves_entrances_unchanged():
    engine, _ = engine_fixture(); original = engine._generator
    with pytest.raises(TypeError):
        install_query_probe(engine, {})
    assert engine._generator is original
    sink = []; install_query_probe(engine, sink); wrapped = engine._generator
    with pytest.raises(ValueError, match='already installed'):
        install_query_probe(engine, sink)
    assert engine._generator is wrapped
