"""Author checks for explicitly installed storage terminal screening."""
from copy import deepcopy
from dataclasses import asdict, replace
import pickle

import pytest

from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Tray
from scripts.experiments.ics_circulation_v3.runtime import Simulation
from scripts.experiments.ics_circulation_v3.routing_cache_contract import ReplayRegionalFactory, _unwrap
from scripts.experiments.ics_circulation_v3.storage_contracts import (
    StorageBag, StorageSnapshot, StorageWaypointContract, StorageProgress)
from scripts.experiments.ics_circulation_v3.storage_routing import StorageCandidateGenerator
from scripts.experiments.ics_circulation_v3.storage_terminal_screen import (
    StorageTerminalScreenFactory, StorageTerminalScreenGenerator, install_storage_terminal_screen)


def factory():
    return ReplayRegionalFactory(12, 1000, 12, True, 3)


def scene(*, busy=False, ordinary=False, empty=False):
    net = Network({n: Node(n, 'z', 'p', capacity=1) for n in ('A', 'S', 'D')},
        {'as': Edge('as', 'A', 'S', 1), 'sd': Edge('sd', 'S', 'D', 1)})
    bag = (Bag('b', 'A', 'D', 0, 20) if ordinary else
           StorageBag('b', 'A', 'D', 0, 20, storage=StorageWaypointContract('S', 3, 0)))
    trays = {'t': Tray('t', 'A') if empty else Tray('t', 'A', 'loaded', 'b')}
    if busy:
        trays['parked'] = Tray('parked', 'D')
    return StorageSnapshot(0, net, trays, {} if empty else {'b': bag})


def inner():
    return StorageCandidateGenerator(factory()())


@pytest.mark.parametrize('ordinary,empty', [(False, False), (True, False), (False, True)])
def test_certifies_busy_final_and_does_not_warm_real_cache(ordinary, empty):
    state = scene(busy=True, ordinary=ordinary, empty=empty)
    base = inner()
    screened = StorageTerminalScreenGenerator(base)
    before_state = asdict(state)
    before_cache = deepcopy(_unwrap(screened)._owned_topology_cache.export())
    options = (screened.generate_empty(state, 't', 'D', 1) if empty else screened.generate(state, 'b', 't', 1))
    assert options == ()
    assert screened.last_search_status == 'terminal_capacity_certificate'
    assert screened.last_expansions == 0 and screened.accounting.screen_work > 0
    assert screened.accounting.rows[-1]['certificate']['other_occupancy'] == 1
    assert _unwrap(screened)._owned_topology_cache.export() == before_cache
    assert base.last_search_status == 'not_started'
    assert asdict(state) == before_state


@pytest.mark.parametrize('ordinary,empty', [(False, False), (True, False), (False, True)])
@pytest.mark.parametrize('max_records', [1, 200000])
def test_uncertified_and_record_cap_delegate_exactly(ordinary, empty, max_records):
    state = scene(ordinary=ordinary, empty=empty)
    old = inner()
    screened = StorageTerminalScreenGenerator(deepcopy(old), max_records=max_records)
    args = (state, 't', 'D', 1) if empty else (state, 'b', 't', 1)
    method = 'generate_empty' if empty else 'generate'
    expected = getattr(old, method)(*args)
    actual = getattr(screened, method)(*args)
    assert actual == expected and expected
    assert screened.last_expansions == old.last_expansions
    assert screened.last_search_status == old.last_search_status
    assert _unwrap(screened)._owned_topology_cache.export() == _unwrap(old)._owned_topology_cache.export()
    assert not screened.accounting.rows[-1]['certificate']['certified']
    if max_records == 1:
        assert screened.accounting.rows[-1]['certificate']['status'] == 'screen_record_budget_unknown_delegate'


@pytest.mark.parametrize('case', ['unpublished', 'bad_time', 'bad_policy', 'waypoint_final',
                                  'missing_ingress', 'progress_wrong_tray', 'not_arrived', 'completed', 'bad_k'])
def test_invalid_storage_requests_keep_inner_diagnosis(case):
    state = scene(busy=True)
    bag = state.bags['b']
    k = 1
    if case == 'unpublished':
        state.bags['b'] = replace(bag, storage=replace(bag.storage, published_at=1))
    elif case == 'bad_time':
        state.bags['b'] = replace(bag, storage=replace(bag.storage, release_at=True))
    elif case == 'bad_policy':
        state.bags['b'] = replace(bag, storage=replace(bag.storage, carrier_policy='off_carrier'))
    elif case == 'waypoint_final':
        state.bags['b'] = replace(bag, storage=replace(bag.storage, node_id='D'))
    elif case == 'missing_ingress':
        state.trays['t'] = replace(state.trays['t'], node='S')
    elif case == 'progress_wrong_tray':
        state.storage_progress['b'] = StorageProgress('parked', bag.storage, 0)
    elif case == 'not_arrived':
        state.bags['b'] = replace(bag, arrival=1)
    elif case == 'completed':
        state.completed['b'] = 0
    else:
        k = 0
    old, screened = inner(), StorageTerminalScreenGenerator(inner())
    assert screened.generate(state, 'b', 't', k) == old.generate(state, 'b', 't', k)
    assert screened.last_search_status == old.last_search_status
    assert screened.last_expansions == old.last_expansions
    assert screened.accounting.rows[-1]['certificate']['status'] == 'invalid_request_delegate'


def test_install_factory_checkpoint_and_sibling_ledgers_are_isolated():
    engine = Simulation(scene(busy=True), generator_factory=factory(), search_horizon=12)
    ledger = install_storage_terminal_screen(engine)
    assert engine._generate(engine.state.trays['t']) == ()
    assert len(ledger.rows) == 1
    checkpoint = pickle.loads(pickle.dumps(engine.checkpoint()))
    left, right = Simulation.from_checkpoint(checkpoint), Simulation.from_checkpoint(checkpoint)
    assert isinstance(left._generator, StorageTerminalScreenGenerator)
    assert left._generator.generator is left._generator.inner.generator
    left._generate(left.state.trays['t'])
    assert len(left._generator.accounting.rows) == 2
    assert len(right._generator.accounting.rows) == len(ledger.rows) == 1
    fresh = Simulation(scene(busy=True), generator_factory=left.generator_factory, search_horizon=12)
    assert type(fresh._generator) is StorageTerminalScreenGenerator
    assert fresh._generator.accounting.rows == []
    fresh._generate(fresh.state.trays['t'])
    assert len(fresh._generator.accounting.rows) == 1
    assert len(left._generator.accounting.rows) == 2
    assert len(right._generator.accounting.rows) == 1
    totals = (ledger.screen_work, ledger.screen_cpu_seconds, ledger.observation_cpu_seconds)
    ledger.rows.clear()
    assert totals == (ledger.screen_work, ledger.screen_cpu_seconds, ledger.observation_cpu_seconds)


def test_unspecified_k_retains_inner_default_candidate_tuple():
    state = scene()
    nodes = dict(state.network.nodes)
    edges = {'as': state.network.edges['as']}
    for index in range(4):
        name = 'P' + str(index)
        nodes[name] = Node(name, 'z', 'p', capacity=1)
        edges['s'+name] = Edge('s'+name, 'S', name, 1)
        edges[name+'d'] = Edge(name+'d', name, 'D', 1)
    state.network = Network(nodes, edges)
    old, screened = inner(), StorageTerminalScreenGenerator(inner())
    expected = old.generate(state, 'b', 't')
    assert len(expected) == 3
    assert screened.generate(state, 'b', 't') == expected
    assert screened.last_expansions == old.last_expansions
    assert screened.accounting.rows[-1]['requested_k'] == 3


@pytest.mark.parametrize('bad', ['deadline', 'cache', 'alias'])
def test_mutated_generator_contract_cannot_be_hidden_by_positive_certificate(bad):
    generator = StorageTerminalScreenGenerator(inner())
    if bad == 'deadline':
        generator.inner.generator.deadline_ms = 1
    elif bad == 'cache':
        generator.inner.generator.cache_contract = None
    else:
        generator.inner = inner()
    with pytest.raises(ValueError):
        generator.generate(scene(busy=True), 'b', 't', 1)


def test_unsupported_factory_slow_and_repeat_install_fail_closed():
    with pytest.raises(ValueError):
        StorageTerminalScreenFactory(lambda horizon=None: factory()())
    with pytest.raises(ValueError):
        StorageTerminalScreenGenerator(factory()())
    engine = Simulation(scene(), generator_factory=factory())
    engine.slow_controller = object()
    with pytest.raises(ValueError):
        install_storage_terminal_screen(engine)
    engine.slow_controller = None
    install_storage_terminal_screen(engine)
    with pytest.raises(ValueError):
        install_storage_terminal_screen(engine)
    with pytest.raises(ValueError):
        engine._generator.generate(None, 'b', 't')
