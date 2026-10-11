"""Round8 symmetric observation for opt-in terminal-screen on/off measurement.

This is a new experimental wrapper, not a change to the frozen Round7 wrapper
or any default. Both arms perform exactly the same observer operations. The
algorithm clock includes request checks, dispatch and certificate/search, but
excludes public-state hashing, copies and diagnostic persistence.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from time import process_time_ns, perf_counter_ns

from .terminal_capacity_screen import terminal_capacity_certificate


@dataclass
class PerformanceAccounting:
    rows: list = field(default_factory=list)


def _eligible(state, bag_id, tray_id, destination, k):
    tray = state.trays.get(tray_id)
    return (type(k) is int and k > 0 and tray is not None and tray.node is not None
            and tray_id not in state.plans and tray.available_at <= state.now
            and destination in state.network.nodes
            and not any(f.tray_id == tray_id and f.arrive > state.now for f in state.old_in_transit)
            and ((bag_id is None and tray.mode == 'empty' and tray.bag_id is None)
                 or (bag_id is not None and tray.mode == 'loaded' and tray.bag_id == bag_id)))


class PerformanceGenerator:
    def __init__(self, generator, accounting=None, *, enabled, max_records=200000):
        from .routing import RegionalCandidateGenerator
        if type(enabled) is not bool:
            raise ValueError('enabled must be bool')
        if (type(generator) is not RegionalCandidateGenerator
                or generator.deadline_ms is not None
                or generator.cache_contract != 'isolated_replay_v1'):
            raise ValueError('deterministic regional replay generator required')
        self.generator = generator
        self.accounting = PerformanceAccounting() if accounting is None else accounting
        self.enabled, self.max_records = enabled, max_records
        self.last_expansions = 0
        self.last_search_status = 'not_started'
        self.last_diagnostics = {}

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, 'generator'), name)

    def generate(self, state, bag_id, tray_id, k=4):
        # Destination lookup is timed inside _call, identically for both arms.
        return self._call(state, bag_id, tray_id, None, k)

    def generate_empty(self, state, tray_id, destination, k=1):
        return self._call(state, None, tray_id, destination, k)

    def _call(self, state, bag_id, tray_id, destination, k):
        oc, ow = process_time_ns(), perf_counter_ns()
        row = {'time': state.now, 'version': state.version, 'bag_id': bag_id,
            'tray_id': tray_id, 'destination': destination, 'requested_k': k,
            'public_snapshot_sha256': None, 'private_cache_before_sha256': None,
            'private_cache_before_entry_count': None, 'options': (),
            'phase': 'observer_entered', 'error': None, 'observer_error': None, 'enabled': self.enabled,
            'certified': False, 'screen_status': 'not_entered',
            'screen_work': 0, 'search_work': 0, 'search_status': 'not_entered',
            **{name: 0 for name in ('algorithm_cpu_ns', 'algorithm_wall_ns',
                'screen_cpu_ns', 'screen_wall_ns', 'search_cpu_ns', 'search_wall_ns',
                'observer_cpu_ns', 'observer_wall_ns')}}
        self.accounting.rows.append(row)
        try:
            snapshot_sha = sha256(json.dumps(asdict(state), sort_keys=True,
                separators=(',', ':'), allow_nan=False).encode()).hexdigest()
            cache = self.generator._owned_topology_cache.export()
            row['private_cache_before_sha256'] = sha256(json.dumps(cache, sort_keys=True,
                separators=(',', ':'), allow_nan=False).encode()).hexdigest()
            row['private_cache_before_entry_count'] = len(cache['entries_lru_oldest_first'])
        except BaseException as exc:
            row.update(phase='observer_error', error={'type': type(exc).__name__, 'message': str(exc)},
                observer_cpu_ns=process_time_ns() - oc, observer_wall_ns=perf_counter_ns() - ow)
            raise
        observe_cpu, observe_wall = process_time_ns() - oc, perf_counter_ns() - ow
        start_cpu, start_wall = process_time_ns(), perf_counter_ns()
        screen_cpu = screen_wall = search_cpu = search_wall = 0
        cert = None
        options = ()
        error = None
        search_entered = False
        try:
            if bag_id is not None:
                bag = state.bags.get(bag_id)
                destination = None if bag is None else bag.destination
            eligible = _eligible(state, bag_id, tray_id, destination, k)
            if self.enabled and eligible:
                cc, cw = process_time_ns(), perf_counter_ns()
                try:
                    cert = terminal_capacity_certificate(state, tray_id, destination,
                        self.generator.horizon, max_records=self.max_records)
                finally:
                    screen_cpu, screen_wall = process_time_ns() - cc, perf_counter_ns() - cw
            if cert is not None and cert['certified']:
                self.last_expansions, self.last_search_status = 0, 'terminal_capacity_certificate'
                raw_diagnostics = {'work_units_by_stage': {}, 'candidate_count': 0,
                                   'expansions': 0, 'cache_accounting': None}
            else:
                search_entered = True
                sc, sw = process_time_ns(), perf_counter_ns()
                try:
                    options = (self.generator.generate(state, bag_id, tray_id, k)
                        if bag_id is not None else
                        self.generator.generate_empty(state, tray_id, destination, k))
                finally:
                    search_cpu, search_wall = process_time_ns() - sc, perf_counter_ns() - sw
                    self.last_expansions = self.generator.last_expansions
                    self.last_search_status = self.generator.last_search_status
                    raw_diagnostics = self.generator.last_diagnostics
        except BaseException as exc:
            error = {'type': type(exc).__name__, 'message': str(exc)}
            if not search_entered:
                self.last_expansions, self.last_search_status = 0, 'screen_error'
                raw_diagnostics = {}
            raise
        finally:
            algorithm_cpu, algorithm_wall = process_time_ns() - start_cpu, perf_counter_ns() - start_wall
            oc, ow = process_time_ns(), perf_counter_ns()
            # Commit paid algorithm work before any observational copy can fail.
            row.update({'time': state.now, 'version': state.version, 'bag_id': bag_id,
                'tray_id': tray_id, 'destination': destination, 'requested_k': k,
                'public_snapshot_sha256': snapshot_sha,
                'phase': 'returned' if error is None else 'error', 'error': error,
                'enabled': self.enabled, 'certified': bool(cert and cert['certified']),
                'screen_status': ('disabled' if not self.enabled else
                    'invalid_request_delegate' if cert is None else cert['status']),
                'screen_work': 0 if cert is None else cert['screen_work'],
                'search_work': self.last_expansions, 'search_status': self.last_search_status,
                'algorithm_cpu_ns': algorithm_cpu, 'algorithm_wall_ns': algorithm_wall,
                'screen_cpu_ns': screen_cpu, 'screen_wall_ns': screen_wall,
                'search_cpu_ns': search_cpu, 'search_wall_ns': search_wall,
                'observer_cpu_ns': 0, 'observer_wall_ns': 0})
            try:
                # Identical fixed-field observer operations for both arms.
                self.last_diagnostics = deepcopy(raw_diagnostics)
                row['options'] = deepcopy(options)
            except BaseException as exc:
                row['observer_error'] = {'type': type(exc).__name__, 'message': str(exc)}
                row['phase'] = 'post_observer_error'
                if error is None:
                    raise
            finally:
                row['observer_cpu_ns'] = observe_cpu + process_time_ns() - oc
                row['observer_wall_ns'] = observe_wall + perf_counter_ns() - ow
        return options


class PerformanceFactory:
    def __init__(self, inner_factory, accounting, *, enabled, max_records=200000):
        self.inner_factory, self.accounting = inner_factory, accounting
        self.enabled, self.max_records = enabled, max_records

    def __call__(self, horizon=None):
        return PerformanceGenerator(self.inner_factory(horizon), self.accounting,
            enabled=self.enabled, max_records=self.max_records)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, 'inner_factory'), name)


def install_performance_probe(engine, *, enabled, max_records=200000):
    """After replay-cache and policy installation, before outer accounting."""
    from .network_role_labels import BudgetGenerator, BudgetFactory
    from .terminal_capacity_screen import TerminalScreenGenerator, TerminalScreenFactory
    from .routing_cache_contract import ReplayRegionalFactory
    blocked_g = (PerformanceGenerator, TerminalScreenGenerator, BudgetGenerator)
    blocked_f = (PerformanceFactory, TerminalScreenFactory, BudgetFactory)
    inner = None if engine.slow_controller is None else engine.slow_controller.controller
    if (isinstance(engine._generator, blocked_g)
        or isinstance(engine.generator_factory, blocked_f)
        or (inner is not None and isinstance(inner.generator_factory, blocked_f))):
        raise ValueError('install once before outer accounting')
    if (type(engine.generator_factory) is not ReplayRegionalFactory
        or (inner is not None and type(inner.generator_factory) is not ReplayRegionalFactory)):
        raise ValueError('all factories must be pure replay factories before installation')
    accounting = PerformanceAccounting()
    new_generator = PerformanceGenerator(engine._generator, accounting,
        enabled=enabled, max_records=max_records)
    engine._generator = new_generator
    engine.generator_factory = PerformanceFactory(engine.generator_factory, accounting,
        enabled=enabled, max_records=max_records)
    if inner is not None:
        inner.generator_factory = PerformanceFactory(inner.generator_factory, accounting,
            enabled=enabled, max_records=max_records)
    return accounting
