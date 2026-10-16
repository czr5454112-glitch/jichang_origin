"""SOURCE-ONLY cold inventory binding for the closed single-capture program.

This is not a native-session or observation cache. The original chain constructor
executes all dynamic checks, in the same order. Only its two static inventory
providers are private replacements. Their original source/AST/code inspections
run once at explicit binding; fixed in-memory program boundaries are checked on
each use. Disk/source and complete import-closure entry/exit pins remain the job
of a future campaign, which is deliberately NOT supplied here.

Supported lifetime: serial, version-closed, non-adversarial Python program.
Arbitrary plugins, concurrent mutation, restored authority and identical resource
failure timing are not claimed. Cold setup, warm checking and proof copies must
all be charged. Neither a speedup nor attribution of the measured residual to
these inventories has been established.
"""
from __future__ import annotations

import copy
import struct
from types import FunctionType, SimpleNamespace

from . import initial_owner_route_single_capture_owned_codec as owned

SCHEMA = 'g31.initial_owner.static_inventory_binding.v1'
integration = owned.previous
private, require = owned.private, owned.require


def _shape(value, active=None):
    """No user equality/iteration hooks; identity leaves for opaque objects.

Only explicit static containers are traversed. Module namespaces are separately
checked shallowly and are never recursively expanded into the entire process.
Shared references are allowed; current-chain cycles are represented by identity.
This is a mutation detector for pinned program data, not a JSON normalizer.
"""
    if active is None:
        active = set()
    kind = type(value)
    if kind in (dict, list, tuple):
        identity = id(value)
        if identity in active:
            return ('cycle', identity)
        active.add(identity)
        try:
            if kind is dict:
                body = tuple((_shape(k, active), _shape(v, active)) for k, v in value.items())
            else:
                body = tuple(_shape(v, active) for v in value)
            return (kind.__name__, identity, body)
        finally:
            active.remove(identity)
    if kind is float:
        # hex() collapses different NaN payloads. Exact built-in float avoids
        # conversion hooks; IEEE bytes preserve payload, sign and signed zero.
        return ('float', struct.pack('>d', value))
    if value is None or kind in (str, bytes, int, bool):
        return (kind.__name__, value)
    # Immutable code, function, type, module, bound method and provider objects
    # are retained by the owning records. Their user equality is never invoked.
    return ('identity', id(value))


def _class_functions(cls):
    """Do not invoke descriptors while inventorying their Python code.

The original method inventory intentionally selects ordinary functions only.
This additional static boundary also covers exact builtin descriptors, rather
than claiming that their underlying functions are checked by that original.
"""
    for value in vars(cls).values():
        if type(value) is FunctionType:
            yield value
        elif type(value) in (staticmethod, classmethod):
            if type(value.__func__) is FunctionType:
                yield value.__func__
        elif type(value) is property:
            for accessor in (value.fget, value.fset, value.fdel):
                if type(accessor) is FunctionType:
                    yield accessor


class _ProgramBoundary:
    """Fixed dependency records; no sys.modules/file scan on a warm request."""
    def __init__(self, *, functions=(), classes=(), locations=(), containers=()):
        classes = tuple({id(cls): cls for cls in classes}.values())
        functions = (*functions, *(fn for cls in classes for fn in _class_functions(cls)))
        functions = tuple({id(fn): fn for fn in functions}.values())
        require(all(type(fn) is FunctionType for fn in functions), 'static_function_domain')
        self.functions = []
        namespaces = {}
        for fn in functions:
            cells = tuple((cell, cell.cell_contents) for cell in (fn.__closure__ or ()))
            self.functions.append((fn, fn.__code__, fn.__defaults__, fn.__kwdefaults__,
                fn.__closure__, cells, _shape(fn.__defaults__), _shape(fn.__kwdefaults__),
                tuple(_shape(v) for _, v in cells), _shape(fn.__dict__)))
            namespaces[id(fn.__globals__)] = fn.__globals__
        # Full defining globals are fixed by identity, not a co_names subset.
        self.namespaces = tuple((ns, tuple(ns.items())) for ns in namespaces.values())
        self.classes = tuple((cls, cls.__mro__, tuple(vars(cls).items())) for cls in classes)
        self.locations = tuple((holder, name, getattr(holder, name)) for holder, name in locations)
        containers = (*containers, *(value for cls in classes for value in vars(cls).values()
            if type(value) in (dict, list, tuple)))
        self.containers = tuple((value, _shape(value)) for value in containers)

    def check(self):
        for fn, code, defaults, kwdefaults, closure, cells, ds, ks, cs, attributes in self.functions:
            require(fn.__code__ is code and fn.__defaults__ is defaults
                and fn.__kwdefaults__ is kwdefaults and fn.__closure__ is closure,
                'static_function_changed')
            require(_shape(defaults) == ds and _shape(kwdefaults) == ks
                and _shape(fn.__dict__) == attributes, 'static_function_container_changed')
            require(all(cell.cell_contents is value and _shape(value) == expected
                for (cell, value), expected in zip(cells, cs)), 'static_closure_changed')
        for namespace, items in self.namespaces:
            require(len(namespace) == len(items)
                and all(key in namespace and namespace[key] is value for key, value in items),
                'static_defining_globals_changed')
        for cls, mro, items in self.classes:
            current = vars(cls)
            require(cls.__mro__ is mro and len(current) == len(items)
                and all(key in current and current[key] is value for key, value in items),
                'static_class_or_MRO_changed')
        for holder, name, value in self.locations:
            require(getattr(holder, name) is value, 'static_dependency_location_changed:' + name)
        require(all(_shape(value) == expected for value, expected in self.containers),
            'static_proof_container_changed')


def _dependencies(live, method_inventory):
    """Exact original inventory inputs and its explicit collector/alias chain."""
    g, single, request = integration.gated, integration.single, integration.request
    adapter = request.adapter
    functions = [row['function'] for row in method_inventory.values()]
    functions += [g.inventory, integration.collection_inventory,
        integration.generated_template_inventory, integration._binding_record,
        integration._code_digest, integration._code_tree,
        integration.gate.collection_inventory, integration.gate.native_advance_sites,
        integration.gate.tree, integration.gate.dump, integration.gate.require,
        adapter.collect_initial_ledger, adapter.collect_native, adapter._valid_handle,
        adapter.previous.collect_initial_ledger, single.initial.collect_native,
        request.fixed_B_first_action, request.InitialOwnerRequest.collect,
        request.InitialOwnerRequest.observe_after_boundary,
        request.InitialOwnerRequest.final_revalidate_and_submit,
        integration.COLLECT, integration.FINAL_REVALIDATE,
        integration.call_with_recorded_collection, single._TEMPLATE,
        *[fn for fn, _ in single._IDENTITIES],
        *[fn for _, _, fn, _ in integration._BINDINGS],
        live.ActualAdvanceChain.__init__, live.TRACKED_DRAIN,
        integration._actual_root_drain, live.run_continuation]
    classes = []
    for cls in (live.TracedContinuationOwner, integration.old.public.LocalTransport,
                live.ActualAdvanceChain, live.CapturedRequest, live.FixedDefaultRequest,
                single._Capture):
        classes.extend(cls.__mro__)
    locations = list(integration._LOCATIONS) + [
        (g, 'inventory'), (g, 'SOURCE_FUNCTIONS'),
        (integration, 'collection_inventory'), (integration, '_BINDINGS'),
        (integration, '_TEMPLATE'), (integration, '_TEMPLATE_AST_PROOF'),
        (integration, 'COLLECT'), (integration, 'FINAL_REVALIDATE'),
        (integration._old_facade, 'call_with_recorded_collection'),
        (request, 'adapter'), (adapter, 'previous'),
        (adapter, 'collect_initial_ledger'), (adapter, 'collect_native'), (adapter, '_valid_handle'),
        (adapter.previous, 'collect_initial_ledger'),
        (single, 'adapter'), (single, 'rolling'), (single, 'initial'),
        (single, '_Capture'), (single, '_TEMPLATE'), (single, '_AST_PROOF'),
        (single.initial, 'collect_native'), (single.initial, 'validate_pair'),
        (single.normalization, 'normalize'),
        (integration.old.public, 'LocalTransport'),
        (g.trace, 'SOURCE'), (request, 'InitialOwnerRequest'),
        (request, 'FixedContinuationOwner')]
    containers = [g.SOURCE_FUNCTIONS, single._AST_PROOF, integration._TEMPLATE_AST_PROOF,
        integration._BINDINGS, single._IDENTITIES, live.run_continuation._source_proof,
        vars(integration._old_facade), vars(live),
        vars(live.ActualAdvanceChain.__init__.__globals__['gate'])]
    # Builtin lookup is an actual dependency; check its fixed mapping once per
    # use, without recursively walking builtins' objects or importing anything.
    for fn in functions:
        value = fn.__globals__.get('__builtins__')
        if type(value) is dict and not any(value is item for item in containers):
            containers.append(value)
    return dict(functions=functions, classes=classes, locations=locations, containers=containers)


class _Inventories:
    def __init__(self, live):
        self.policy_type = live.TracedContinuationOwner
        self.transport_type = integration.old.public.LocalTransport
        # No constructors, native handles, endpoints or instance state are read.
        # The original inventory uses only type(instance).__mro__/vars(class).
        probes = {name: object.__new__(self.policy_type) for name in ('A', 'B')}
        transport = object.__new__(self.transport_type)
        methods = integration.gated.inventory(probes, transport)
        self.collection = integration.collection_inventory()
        self.parts = {label: tuple((key, tuple(row.items())) for key, row in methods.items()
            if key.startswith(label + ':')) for label in ('A', 'B', 'transport')}
        require(sum(map(len, self.parts.values())) == len(methods), 'static_inventory_labels')
        self.boundary = _ProgramBoundary(**_dependencies(live, methods))
        self.binding_boundary = None

    def check(self):
        self.boundary.check()
        if self.binding_boundary is not None:
            self.binding_boundary.check()

    def methods(self, policies, client):
        self.check()
        # These exact instance/owner/session checks already execute in the
        # unchanged constructor. Retain a closed provider domain as well.
        require(type(policies) is dict and tuple(policies) in ((), ('A', 'B'), ('B', 'A'))
            and all(type(value) is self.policy_type for value in policies.values())
            and type(client) is self.transport_type, 'static_inventory_instance_domain')
        return {key: dict(row) for label in (*policies, 'transport') for key, row in self.parts[label]}

    def collections(self):
        self.check()
        return copy.deepcopy(self.collection)


def bind(live):
    """Explicit cold bind of an existing accepted live composition.

The upstream binding check is a source/shape check, NOT independent C authority.
A future runtime must obtain live from owned.bind(verified Candidate), retain
the original C loader/lifetime checks, and charge this entire cold call.
"""
    owned.binding_proof(live)
    cached = _Inventories(live)

    class ActualAdvanceChain(live.ActualAdvanceChain):
        pass

    actual_drain = private(integration._actual_root_drain, {'ActualAdvanceChain': ActualAdvanceChain})
    tracked_drain = private(live.TRACKED_DRAIN, {'_actual_root_drain': actual_drain})

    class CapturedRequest(live.CapturedRequest):
        drain_and_finish_if_closed = tracked_drain

    class FixedDefaultRequest(CapturedRequest):
        choose = live.FixedDefaultRequest.choose

    constructor = live.ActualAdvanceChain.__init__
    facade = SimpleNamespace(**{**vars(constructor.__globals__['gate']),
        'collection_inventory': cached.collections})
    ActualAdvanceChain.__init__ = private(constructor, {
        'inventory': cached.methods, 'gate': facade,
        'TRACKED_DRAIN': tracked_drain, 'CapturedRequest': CapturedRequest})
    run = private(live.run_continuation, {'ActualAdvanceChain': ActualAdvanceChain})
    run._source_proof = copy.deepcopy(live.run_continuation._source_proof)
    result = SimpleNamespace(**{**vars(live), 'CapturedRequest': CapturedRequest,
        'FixedDefaultRequest': FixedDefaultRequest, 'ActualAdvanceChain': ActualAdvanceChain,
        'TRACKED_DRAIN': tracked_drain, 'run_continuation': run,
        'collection_inventory': cached.collections})
    # Private metadata holds STATIC program objects/proofs only. No root/client,
    # session, observation, outbox, ACK, policy instance or decision is retained.
    result._static_inventory = cached
    result._source_binding = live
    result._actual_root_drain = actual_drain
    result._constructor_changes = {'inventory': ActualAdvanceChain.__init__.__globals__['inventory'],
        'gate': facade, 'TRACKED_DRAIN': tracked_drain, 'CapturedRequest': CapturedRequest}
    cached.binding_boundary = _ProgramBoundary(
        functions=(ActualAdvanceChain.__init__, actual_drain, tracked_drain, run),
        classes=(ActualAdvanceChain, CapturedRequest, FixedDefaultRequest),
        containers=(vars(facade), vars(result), result._constructor_changes,
                    cached.parts, cached.collection))
    binding_proof(result)
    return result


def binding_proof(binding):
    live = binding._source_binding
    cached = binding._static_inventory
    cached.check()
    owned._delta(live.ActualAdvanceChain.__init__, binding.ActualAdvanceChain.__init__,
        binding._constructor_changes)
    owned._delta(live.TRACKED_DRAIN, binding.TRACKED_DRAIN,
        {'_actual_root_drain': binding._actual_root_drain})
    owned._delta(integration._actual_root_drain, binding._actual_root_drain,
        {'ActualAdvanceChain': binding.ActualAdvanceChain})
    owned._delta(live.run_continuation, binding.run_continuation,
        {'ActualAdvanceChain': binding.ActualAdvanceChain})
    require(binding.ActualAdvanceChain.__bases__ == (live.ActualAdvanceChain,)
        and binding.CapturedRequest.__bases__ == (live.CapturedRequest,)
        and binding.FixedDefaultRequest.__bases__ == (binding.CapturedRequest,), 'static_new_MRO')
    constructor = binding.ActualAdvanceChain.__init__
    cell = dict(zip(constructor.__code__.co_freevars, constructor.__closure__ or ()))['__class__']
    require(cell.cell_contents is integration.gated.ActualAdvanceChain
        and binding.ActualAdvanceChain.__mro__[binding.ActualAdvanceChain.__mro__.index(
            integration.gated.ActualAdvanceChain) + 1] is integration.gate._RecordedChain,
        'static_original_super_cell')
    for name in ('collect', 'final_revalidate_and_submit', 'observe_after_boundary', '_record', 'evidence'):
        require(getattr(binding.CapturedRequest, name) is getattr(live.CapturedRequest, name),
            'static_changed_dynamic_method:' + name)
    for name in ('EVIDENCE', 'finish_root', 'publish_root', 'call_with_recorded_collection',
                 'TracedContinuationOwner', 'make_client', 'TRACED_OBSERVE'):
        require(getattr(binding, name) is getattr(live, name), 'static_changed_live_dependency:' + name)
    require(binding.CapturedRequest.drain_and_finish_if_closed is binding.TRACKED_DRAIN
        and binding.FixedDefaultRequest.choose is live.FixedDefaultRequest.choose,
        'static_changed_drain_or_default_policy')
    return {'schema': SCHEMA, 'original_constructor_code_defaults_closure_exact': True,
        'original_AST_unchanged_not_recompiled': True,
        'constructor_private_global_changes': sorted(binding._constructor_changes),
        'cold_original_method_inventory_calls': 1, 'cold_original_collection_inventory_calls': 1,
        'warm_static_checks_and_fresh_proof_copies_charged': True,
        'dynamic_session_handle_transport_owner_ACK_current_checks_removed': 0,
        'source_bytes_and_complete_loaded_closure_require_campaign_entry_exit_pins': True,
        'original_complete_publisher_and_collection_normalization_unchanged': True,
        'cross_request_observation_or_result_cache': False,
        'general_mutable_plugins_or_concurrency_supported': False,
        'allocation_failure_equivalence_claimed': False,
        'per_sample_cycle_reclamation_certified': False,
        'actual_C_support_or_campaign_ready_or_speed_claimed': False}


def branch_function(binding):
    original = owned.branch_function(binding._source_binding)
    binding_proof(binding)
    result = private(original, {'CapturedRequest': binding.CapturedRequest,
        'FixedDefaultRequest': binding.FixedDefaultRequest, 'run_continuation': binding.run_continuation})
    owned._delta(original, result, {'CapturedRequest': binding.CapturedRequest,
        'FixedDefaultRequest': binding.FixedDefaultRequest, 'run_continuation': binding.run_continuation})
    return result
