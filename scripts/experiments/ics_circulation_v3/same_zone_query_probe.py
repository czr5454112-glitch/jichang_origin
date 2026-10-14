"""Opt-in query observation for offline coverage diagnostics.

Install after normal accounting. The sink sees public query inputs only; no
engine reference or external future tape is retained. Copying/pickling a probe
strips this observational layer and preserves its underlying planner/budget.
No search, parameter change or candidate filtering occurs in this module.
"""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import inspect
import json


def _identity(value):
    return value


def _planner(generator):
    seen = set()
    while id(generator) not in seen:
        seen.add(id(generator))
        if hasattr(generator, 'generator'):
            generator = generator.generator
        elif hasattr(generator, 'inner'):
            generator = generator.inner
        else:
            return generator
    raise ValueError('Generator wrapper cycle')


def _cache(generator):
    planner = _planner(generator)
    cache = getattr(planner, '_owned_topology_cache', None)
    return deepcopy(cache.export()) if cache is not None else None


def _callsite(role):
    # Only names/filenames are copied; never retain frame/local objects, which
    # could contain the event engine and its hidden tape.
    frame = inspect.currentframe()
    names = []
    try:
        frame = frame.f_back
        for _ in range(16):
            if frame is None:
                break
            names.append({'function': frame.f_code.co_name,
                          'filename': frame.f_code.co_filename,
                          'line': frame.f_lineno})
            frame = frame.f_back
    finally:
        del frame
    funcs = {entry['function'] for entry in names}
    if role == 'slow_factory':
        site = 'slow_empty'
    elif '_resume_reactive' in funcs or '_dispatch_empty' in funcs:
        site = 'engine_reactive'
    elif '_resume_empty' in funcs or '_route_empty' in funcs:
        site = 'engine_empty_continuation'
    elif '_resume_loaded' in funcs or '_route_loaded' in funcs:
        site = 'engine_loaded'
    else:
        site = 'unclassified_direct_query'
    return site, names


class QueryProbeGenerator:
    """Transparent generator; sink list records entered/returned/error in place."""
    def __init__(self, generator, sink, role):
        self.generator, self.sink, self.role = generator, sink, role

    def __getattr__(self, name):
        inner = object.__getattribute__(self, 'generator')
        try:
            return getattr(inner, name)
        except AttributeError:
            return getattr(_planner(inner), name)

    def __deepcopy__(self, memo):
        value = deepcopy(self.generator, memo)
        memo[id(self)] = value
        return value

    def __reduce__(self):
        return _identity, (self.generator,)

    def generate(self, snapshot, bag_id, tray_id, k=4):
        return self._call(snapshot, bag_id, tray_id, None, k)

    def generate_empty(self, snapshot, tray_id, destination, k=1):
        return self._call(snapshot, None, tray_id, destination, k)

    def _call(self, snapshot, bag_id, tray_id, destination, k):
        planner = _planner(self.generator)
        site, stack = _callsite(self.role)
        record = {'query_ordinal': len(self.sink), 'phase': 'entered',
                  'generator_role': self.role, 'callsite': site, 'call_stack': stack,
                  'method': 'generate' if bag_id is not None else 'generate_empty',
                  'time': snapshot.now, 'version': snapshot.version,
                  'bag_id': bag_id, 'tray_id': tray_id, 'requested_k': k,
                  'destination': destination if bag_id is None else getattr(snapshot.bags.get(bag_id), 'destination', None),
                  'snapshot': snapshot.clone(),
                  'generator_class': type(planner).__module__ + '.' + type(planner).__qualname__,
                  'generator_settings': {name: getattr(planner, name) for name in
                      ('horizon', 'expansion_limit', 'static_path_limit', 'deadline_ms',
                       'dynamic_local', 'local_label_limit', 'cache_contract') if hasattr(planner, name)}}
        self.sink.append(record)
        original_error = None
        try:
            record['public_snapshot_sha256'] = sha256(json.dumps(asdict(record['snapshot']),
                sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
            record['cache_before'] = _cache(self.generator)
            options = (self.generator.generate(snapshot, bag_id, tray_id, k=k) if bag_id is not None
                       else self.generator.generate_empty(snapshot, tray_id, destination, k=k))
            record.update(options=deepcopy(options), raw_candidate_count=len(options), phase='returned')
        except BaseException as error:
            original_error = error
            record.update(phase='error', error={'type': type(error).__name__, 'message': str(error)})
            raise
        finally:
            # Leave partial diagnostics even when the planner or observer fails.
            try:
                record['last_expansions'] = getattr(planner, 'last_expansions', None)
                record['last_search_status'] = getattr(planner, 'last_search_status', None)
                record['last_diagnostics'] = deepcopy(getattr(planner, 'last_diagnostics', {}))
                record['cache_after'] = _cache(self.generator)
            except BaseException as observer_error:
                record['observation_error'] = {'type': type(observer_error).__name__, 'message': str(observer_error)}
                if original_error is None:
                    record['phase'] = 'measurement_error'
                    raise
        return options


class QueryProbeFactory:
    def __init__(self, inner_factory, sink, role):
        self.inner_factory, self.sink, self.role = inner_factory, sink, role

    def __call__(self, horizon=None):
        return QueryProbeGenerator(self.inner_factory(horizon), self.sink, self.role)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, 'inner_factory'), name)

    def __deepcopy__(self, memo):
        value = deepcopy(self.inner_factory, memo)
        memo[id(self)] = value
        return value

    def __reduce__(self):
        return _identity, (self.inner_factory,)


def _strip(value):
    while isinstance(value, (QueryProbeGenerator, QueryProbeFactory)):
        value = value.generator if isinstance(value, QueryProbeGenerator) else value.inner_factory
    return value


def detach_query_probe(target):
    """Remove only outer probe entrances, in place; engine/checkpoint accepted."""
    if hasattr(target, 'base'):
        target = target.base
    for field in ('_generator', 'generator', 'generator_factory'):
        if hasattr(target, field):
            setattr(target, field, _strip(getattr(target, field)))
    slow = getattr(target, 'slow_controller', None)
    controller = getattr(slow, 'controller', None)
    if controller is not None and hasattr(controller, 'generator_factory'):
        controller.generator_factory = _strip(controller.generator_factory)
    return target


def install_query_probe(engine, sink):
    """Install on known fast/slow entrances after bind_accounting.

    sink must be a list. Its records are mutable until query completion; persist
    after the collector finishes. A sink deliberately cannot be a callback that
    follows the engine into a future tape. Checkpoint deepcopy/pickle strips all
    probe entrances automatically and does not clear or copy the live sink.
    """
    if not isinstance(sink, list):
        raise TypeError('query probe sink must be a list')
    if isinstance(engine._generator, QueryProbeGenerator) or isinstance(engine.generator_factory, QueryProbeFactory):
        raise ValueError('query probe already installed')
    if engine.generator_factory is None:
        raise ValueError('known factory entrance required')
    slow = getattr(engine, 'slow_controller', None)
    controller = getattr(slow, 'controller', None)
    if controller is not None and isinstance(controller.generator_factory, QueryProbeFactory):
        raise ValueError('slow query probe already installed')
    engine._generator = QueryProbeGenerator(engine._generator, sink, 'fast_generator')
    engine.generator_factory = QueryProbeFactory(engine.generator_factory, sink, 'fast_factory')
    if controller is not None:
        controller.generator_factory = QueryProbeFactory(controller.generator_factory, sink, 'slow_factory')
    return {'schema': 'ics_query_probe_v1', 'capture': 'actual public query Snapshot and raw unfiltered options',
            'snapshot_scope': 'generator argument only; no engine/cursor/hidden future tape captured',
            'copy_contract': 'deepcopy/pickle removes only probe, preserves inner budget/cache',
            'candidate_scope': 'raw options; caller must separately retain post-execution-validator opportunity pool'}
