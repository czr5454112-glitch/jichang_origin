"""Explicit central storage-aware terminal screen, with separate work ledger.

The unchanged search budget belongs to the inner generator. Screening work is
additional and explicitly measured, not silently called the same total budget.
The necessary condition concerns full witnesses in the current public calendar;
it never certifies permanent task infeasibility or permits release of peers.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from time import process_time

from .model import Snapshot
from .routing import RegionalCandidateGenerator
from .routing_cache_contract import IsolatedTopologyCache, ReplayRegionalFactory
from .storage_contracts import (StorageBag, StorageSnapshot, effective_storage_progress,
                                storage_contract_failure)
from .storage_routing import StorageCandidateGenerator
from .terminal_capacity_screen import (ScreenAccounting, TerminalScreenGenerator,
                                       terminal_capacity_certificate)


def _check_inner(inner):
    if type(inner) is not StorageCandidateGenerator:
        raise ValueError('storage terminal screen requires an unwrapped storage generator')
    regional = inner.generator
    if (type(regional) is not RegionalCandidateGenerator
            or regional.deadline_ms is not None
            or regional.cache_contract != 'isolated_replay_v1'
            or not isinstance(regional._owned_topology_cache, IsolatedTopologyCache)):
        raise ValueError('storage terminal screen requires deterministic regional replay contract')
    return regional


def _check_factory(factory):
    # Both accepted factories are frozen, configuration-only dataclasses. They
    # own no mutable accounting or cache, so checkpoint's shared factory is safe.
    from .business_runtime import BusinessGeneratorFactory
    if type(factory) not in (ReplayRegionalFactory, BusinessGeneratorFactory):
        raise ValueError('unsupported storage terminal screen factory')


def _check_limit(max_records):
    if type(max_records) is not int or max_records < 1:
        raise ValueError('positive integer screen record limit required')


class StorageTerminalScreenGenerator(StorageCandidateGenerator):
    """Screen outside a complete StorageCandidateGenerator, never inside it.

Subclass identity makes Simulation._make_generator preserve the screen layer.
``generator`` and ``inner.generator`` alias one Regional delegate; deepcopy
preserves this relationship, including its real private cache state.
"""
    def __init__(self, inner, accounting=None, *, max_records=200000):
        regional = _check_inner(inner)
        _check_limit(max_records)
        super().__init__(regional)
        self.inner = inner
        self.accounting = ScreenAccounting() if accounting is None else accounting
        if type(self.accounting) is not ScreenAccounting:
            raise ValueError('known screen accounting required')
        self.max_records = max_records

    # Reuse the existing ledger implementation, not a forged Regional type.
    _record = TerminalScreenGenerator._record

    def generate(self, state, bag_id, tray_id, k=3):
        if not isinstance(state, Snapshot):
            raise ValueError('snapshot required')
        bag = state.bags.get(bag_id)
        return self._call(state, bag_id, tray_id, None if bag is None else bag.destination, k)

    def generate_empty(self, state, tray_id, destination, k=1):
        return self._call(state, None, tray_id, destination, k)

    def _eligible(self, state, bag_id, tray_id, destination, k):
        tray = state.trays.get(tray_id)
        if (type(k) is not int or k < 1 or tray is None or tray.node is None
                or tray_id in state.plans or tray.available_at > state.now
                or destination not in state.network.nodes
                or any(f.tray_id == tray_id and f.arrive > state.now for f in state.old_in_transit)):
            return False
        if bag_id is None:
            return tray.mode == 'empty' and tray.bag_id is None
        bag = state.bags.get(bag_id)
        if (bag is None or tray.mode != 'loaded' or tray.bag_id != bag_id
                or bag.arrival > state.now or bag_id in state.completed):
            return False
        if isinstance(bag, StorageBag):
            # A screen must not turn malformed storage requests into successful
            # certificates. Delegate them to preserve the original diagnosis.
            try:
                if storage_contract_failure(state, bag_id):
                    return False
                contract = bag.storage
                progress = effective_storage_progress(state, bag_id)
                visited = progress is not None and progress.arrived_at is not None
                departed = progress is not None and progress.departed_at is not None
                if (contract is None or (progress is not None and
                        (progress.tray_id != tray_id or progress.contract != contract
                         or (progress.arrived_at is not None and progress.arrived_at > state.now)
                         or (progress.departed_at is not None and progress.departed_at > state.now)))
                        or (visited and not departed and tray.node != contract.node_id)
                        or (departed and not visited)
                        or (tray.node == contract.node_id and not visited)):
                    return False
            except (ValueError, TypeError, AttributeError, KeyError):
                return False
        return True

    def _call(self, state, bag_id, tray_id, destination, k):
        if not isinstance(state, Snapshot):
            raise ValueError('snapshot required')
        regional = _check_inner(self.inner)
        if self.generator is not regional:
            raise ValueError('storage terminal screen delegate alias changed')
        _check_limit(self.max_records)
        observed_cpu = process_time()
        snapshot_sha = sha256(json.dumps(asdict(state), sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        observed_cpu = process_time() - observed_cpu
        certificate = (terminal_capacity_certificate(state, tray_id, destination,
            self.horizon, max_records=self.max_records)
            if self._eligible(state, bag_id, tray_id, destination, k) else
            {'certified': False, 'status': 'invalid_request_delegate', 'screen_work': 0,
             'screen_cpu_seconds': 0., 'scope': 'Original generator handles invalid request.'})
        if certificate['certified']:
            options = ()
            self.last_expansions = 0
            self.last_search_status = 'terminal_capacity_certificate'
            self.last_diagnostics = {
                'work_units_by_stage': {}, 'candidate_count': 0, 'expansions': 0,
                'search_skipped_with_sufficient_certificate': True,
                'missing_candidate_is_not_future_task_infeasibility': True,
                'cache_accounting': None,
                'budget_scope': 'unchanged_inner_search_budget_plus_separately_measured_screen_work'}
        else:
            try:
                options = (self.inner.generate(state, bag_id, tray_id, k) if bag_id is not None
                           else self.inner.generate_empty(state, tray_id, destination, k))
            except BaseException as error:
                self.last_expansions = self.inner.last_expansions
                self.last_search_status = self.inner.last_search_status
                self.last_diagnostics = deepcopy(self.inner.last_diagnostics)
                self.last_diagnostics['terminal_screen'] = certificate
                self._record(state, bag_id, tray_id, destination, k, certificate, (), snapshot_sha,
                    observed_cpu, phase='error', error={'type': type(error).__name__, 'message': str(error)})
                raise
            self.last_expansions = self.inner.last_expansions
            self.last_search_status = self.inner.last_search_status
            self.last_diagnostics = deepcopy(self.inner.last_diagnostics)
        self.last_diagnostics['terminal_screen'] = certificate
        self._record(state, bag_id, tray_id, destination, k, certificate, options, snapshot_sha, observed_cpu)
        return options


@dataclass(frozen=True)
class StorageTerminalScreenFactory:
    """Pure factory: every newly made generator owns independent screen totals."""
    inner_factory: object
    max_records: int = 200000

    def __post_init__(self):
        _check_factory(self.inner_factory)
        _check_limit(self.max_records)

    def __call__(self, horizon=None):
        _check_factory(self.inner_factory)
        regional = self.inner_factory(horizon=horizon)
        return StorageTerminalScreenGenerator(StorageCandidateGenerator(regional), max_records=self.max_records)


def install_storage_terminal_screen(engine, *, max_records=200000):
    """Install once on a known central storage engine; return its live ledger.

Unknown wrappers and slow controllers are explicitly unsupported. Configure
them through a separately audited integration rather than silently bypassing
one planner. Streaming may clear accounting.rows, never cumulative counters.
"""
    from .runtime import Simulation
    if not isinstance(engine, Simulation) or not isinstance(engine.state, StorageSnapshot):
        raise ValueError('central storage Simulation required')
    if engine.slow_controller is not None:
        raise ValueError('storage terminal screen does not support slow controllers')
    _check_factory(engine.generator_factory)
    _check_inner(engine._generator)
    _check_limit(max_records)
    screen = StorageTerminalScreenGenerator(engine._generator, max_records=max_records)
    factory = StorageTerminalScreenFactory(engine.generator_factory, max_records=max_records)
    engine._generator, engine.generator_factory = screen, factory
    return screen.accounting
