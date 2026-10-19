"""Request-local static catalog sharing without replacing any old globals.

All dynamic guard functions retain their original code and call order. The
private modules are not installed in sys.modules and confer no native authority.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from types import FunctionType, ModuleType

from . import domain_guard_historical_service
from . import domain_guard_v2
from . import foundation_catalog_copy
from . import live_obligation_delivered_context
from . import live_obligation_domain_guard
from . import live_obligation_historical_service
from . import live_obligation_lifecycle_state_v2
from . import native_host
from . import public_live_obligation_event_projection_v2
from . import public_live_obligation_projection

VERSION = 'g31.foundation.request_local_static_context.v1'


def require(condition, reason):
    if not condition:
        raise ValueError('foundation_request:' + reason)


def clone_function(function, namespace):
    result = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    result.__annotations__ = function.__annotations__
    return result


def clone_module(original, replacements, aliases):
    result = ModuleType(original.__name__ + '.request_local')
    result.__dict__.update(vars(original))
    for name, value in vars(original).items():
        if type(value) is FunctionType:
            if value in aliases:
                result.__dict__[name] = aliases[value]
            elif value.__globals__ is vars(original):
                cloned = clone_function(value, vars(result))
                result.__dict__[name] = cloned
                aliases[value] = cloned
    result.__dict__.update(replacements)
    return result


def path_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class RequestContext:
    def __init__(self):
        public_live_obligation_event_projection_v2.check_sources()
        originals = (public_live_obligation_projection, live_obligation_domain_guard,
            live_obligation_lifecycle_state_v2, domain_guard_v2, live_obligation_historical_service,
            domain_guard_historical_service, live_obligation_delivered_context)
        construction = public_live_obligation_projection.construction
        static_sources = (construction, construction.source_domain, construction.source_domain.prior,
            construction.source_domain.prior.fixture, native_host, public_live_obligation_event_projection_v2,
            foundation_catalog_copy)
        paths = {Path(module.__file__).resolve() for module in originals + static_sources}
        paths.update((Path(__file__).resolve(), Path(native_host.service_aware_potential.__code__.co_filename).resolve()))
        self.source_sha256 = {str(path): path_sha(path) for path in sorted(paths)}
        self.counts = {'static_catalog_builds': 0, 'static_catalog_reads': 0, 'dynamic_later_context_calls': 0}
        catalog = public_live_obligation_projection.inputs()
        self.counts['static_catalog_builds'] += 1
        self.catalog_sha256 = hashlib.sha256(live_obligation_domain_guard.canonical(catalog).encode()).hexdigest()
        def inputs():
            self.counts['static_catalog_reads'] += 1
            return foundation_catalog_copy.isolated_copy(catalog)
        aliases = {}
        self.projection = clone_module(public_live_obligation_projection, {'inputs': inputs}, aliases)
        self.guard = clone_module(live_obligation_domain_guard, {'construction': self.projection}, aliases)
        self.lifecycle = clone_module(live_obligation_lifecycle_state_v2,
            {'old': self.guard, 'construction': self.projection}, aliases)
        self.domain = clone_module(domain_guard_v2, {'old': self.guard, 'lifecycle': self.lifecycle}, aliases)
        private = dict(vars(self.guard))
        private['later_bundle'] = self.lifecycle.later_bundle
        private['validate_later_pair'] = clone_function(self.guard.validate_later_pair, private)
        self.domain._private = private
        self.domain.validate_later_pair = private['validate_later_pair']
        self.domain.validate_collected_endpoints = clone_function(self.guard.validate_collected_endpoints, private)
        self.domain.validate_pair = self.guard.validate_pair
        self.domain.later_bundle = self.lifecycle.later_bundle
        history = clone_module(live_obligation_historical_service, {'base': self.guard}, aliases)
        self.historical = clone_module(domain_guard_historical_service,
            {'old': self.domain, 'lifecycle': self.lifecycle, 'history': history}, aliases)
        self.delivered = clone_module(live_obligation_delivered_context,
            {'initial': self.guard, 'later': self.historical}, aliases)
        later_context = self.delivered.later_context
        def counted_later_context(**kwargs):
            self.counts['dynamic_later_context_calls'] += 1
            return later_context(**kwargs)
        self.delivered.later_context = counted_later_context

    def build_seed(self, factory, evidence):
        path = str(Path(factory.__code__.co_filename).resolve())
        self.source_sha256.setdefault(path, path_sha(path))
        namespace = dict(factory.__globals__)
        namespace.update(delivered=self.delivered, guard=self.guard)
        return clone_function(factory, namespace)(evidence)

    def close(self):
        require(all(path_sha(path) == expected for path, expected in self.source_sha256.items()),
                'request_source_bytes_changed')
        return {'schema': VERSION, 'counts': dict(self.counts), 'static_catalog_sha256': self.catalog_sha256,
            'static_catalog_copy_strategy': foundation_catalog_copy.VERSION,
            'source_sha256': dict(self.source_sha256), 'source_exit_pins_passed': True,
            'source_pin_scope': 'partial_project_files_private_graph_static_construction_and_seed_factory',
            'source_pins_are_full_dependency_proof': False, 'campaign_full_source_pins_required': True,
            'cross_request_cache': False, 'dynamic_guards_skipped': False,
            'native_delivery_verified': False, 'native_execution_authority': False}
