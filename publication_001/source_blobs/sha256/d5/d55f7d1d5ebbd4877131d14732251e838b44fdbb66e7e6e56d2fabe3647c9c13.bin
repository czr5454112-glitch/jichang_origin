"""One fresh public fixed-input construction per conditional prediction.

The unchanged guards still compare every contract, job and capture. Each inputs
read returns a new deepcopy; endpoint data, validation results and model state
are never cached. Scope construction and private binding belong inside measured
prediction cost. This is a closed, pinned serial-program candidate, not support
for concurrent monkeypatching of public fixture builders.
"""
from __future__ import annotations
import copy
from types import FunctionType, SimpleNamespace

from . import public_live_obligation_lazy_communication_projection as lazy
from . import public_live_obligation_projection as construction
from . import live_obligation_domain_guard as initial
from . import live_obligation_lifecycle_state_v2 as lifecycle
from . import domain_guard_v2 as v2
from . import domain_guard_historical_service as historical
from . import live_obligation_delivered_context as context


def require(value, reason):
    if not value: raise ValueError('scoped_public_inputs:' + reason)


def private(function, namespace):
    value = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    value.__kwdefaults__ = function.__kwdefaults__
    return value


def clone_module(module, replacements):
    """Retain every defining global, privately rebind local function references."""
    namespace = {**vars(module), **replacements}
    for name, function in vars(module).items():
        if name not in replacements and type(function) is FunctionType and function.__module__ == module.__name__:
            namespace[name] = private(function, namespace)
    return SimpleNamespace(**namespace), namespace


class PublicInputScope:
    """Per-invocation public constants with independently owned return values."""
    def __init__(self):
        # Exactly the original constructor, not saved predictions or actual
        # future observations. No import-time/prewarmed/global cache.
        self._inputs = construction.inputs()
        require(type(self._inputs) is dict and tuple(self._inputs) == construction.construction.CASE_IDS,
            'fixed_public_domain')
        self.input_reads = 0
        self.construction, self._construction_namespace = clone_module(construction, {'inputs': self.inputs})
        self.initial, self._initial_namespace = clone_module(initial, {'construction': self.construction})
        self.lifecycle, self._lifecycle_namespace = clone_module(lifecycle, {
            'old': self.initial, 'construction': self.construction,
            'identify_public_case': self.initial.identify_public_case, 'public_input': self.initial.public_input})
        # Recreate exactly the original v2 private namespace with its same one
        # lifecycle substitution, now referring to this scope's public inputs.
        v2_namespace = {**vars(self.initial), 'later_bundle': self.lifecycle.later_bundle}
        v2_namespace['validate_later_pair'] = private(initial.validate_later_pair, v2_namespace)
        v2_namespace['validate_collected_endpoints'] = private(initial.validate_collected_endpoints, v2_namespace)
        self.v2 = SimpleNamespace(**{**vars(v2), 'old': self.initial, 'lifecycle': self.lifecycle,
            '_private': v2_namespace, 'validate_pair': self.initial.validate_pair,
            'later_bundle': self.lifecycle.later_bundle,
            'validate_later_pair': v2_namespace['validate_later_pair'],
            'validate_collected_endpoints': v2_namespace['validate_collected_endpoints']})
        self.historical, self._historical_namespace = clone_module(historical, {
            'old': self.v2, 'lifecycle': self.lifecycle})
        self.context, self._context_namespace = clone_module(context, {
            'initial': self.initial, 'later': self.historical})
        # SuppliedContext stays the exact original data-envelope class. No
        # changed constructor, fabricated native type or relaxed revalidation.
        self.Projection = type('ScopedInputsProjection', (lazy.Projection,), {
            'collect': private(lazy.original.Projection.collect,
                {**lazy.original.Projection.collect.__globals__, 'guard': self.historical})})
        self.predict = private(lazy.predict, {**lazy.predict.__globals__,
            'Projection': self.Projection, 'context': self.context})

    def inputs(self):
        self.input_reads += 1
        return copy.deepcopy(self._inputs)

    def source_proof(self):
        checks = {}
        for label, original, namespace in (
            ('construction', construction, self._construction_namespace),
            ('initial', initial, self._initial_namespace),
            ('lifecycle', lifecycle, self._lifecycle_namespace),
            ('historical', historical, self._historical_namespace),
            ('context', context, self._context_namespace)):
            for name, function in vars(original).items():
                if type(function) is not FunctionType or function.__module__ != original.__name__: continue
                if label == 'construction' and name == 'inputs': continue
                current = namespace[name]
                require(current.__code__ is function.__code__ and current.__closure__ is function.__closure__
                    and current.__defaults__ is function.__defaults__ and current.__kwdefaults__ is function.__kwdefaults__,
                    'changed_guard_or_helper_code:' + label + '.' + name)
                require(set(current.__globals__) == set(function.__globals__), 'defining_globals_lost:' + label + '.' + name)
                checks[label + '.' + name] = True
        require(self.context.SuppliedContext is context.SuppliedContext, 'context_type_changed')
        require(self.predict.__code__ is lazy.predict.__code__ and
            self.Projection.collect.__code__ is lazy.original.Projection.collect.__code__ and
            self.Projection.activate is lazy.Projection.activate and self.Projection.run is lazy.Projection.run,
            'model_code_changed')
        require(self.initial.construction is self.construction and self.lifecycle.old is self.initial
            and self.historical.old is self.v2 and self.v2.old is self.initial
            and self.context.initial is self.initial and self.context.later is self.historical
            and self.predict.__globals__['context'] is self.context
            and self.Projection.collect.__globals__['guard'] is self.historical,
            'scope_binding_changed')
        return {'schema': 'g31.live_obligation.scoped_public_inputs.v1', 'unchanged_functions': checks,
            'original_fixed_input_constructor_calls': 1, 'every_inputs_read_deepcopied': True,
            'all_endpoint_and_lifecycle_guards_retained': True, 'same_model_entry_and_event_code': True,
            'native_authority': False, 'scope_construction_must_be_charged': True,
            'saved_prediction_or_future_observation_cache': False, 'global_cache': False,
            'concurrent_public_builder_mutation_supported': False,
            'removed_repeated_allocation_failures_timing_equivalence_claimed': False}


def predict(supplied_context, action):
    """Fresh scope costs are part of every call, including failed predictions."""
    scope = PublicInputScope()
    return scope.predict(supplied_context, action)
