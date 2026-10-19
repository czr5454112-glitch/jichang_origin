"""Narrow private public-data reads inside one fresh conditional prediction.

Generic inputs() still deepcopies the whole table. Only public_input(case)
copies the selected case, and construction.identify borrows the private table
for its unchanged read-only digest loop. Historical guards point to the same
scoped initial guard. No observation, outcome or validation result is cached.

The domain is the pinned serial three-case builtin fixture constructor. As in
v1, fewer allocations can change resource-failure timing; concurrent mutation
of the private table or fixture builders is outside this experimental domain.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import inspect
import textwrap
from types import FunctionType

from . import public_live_obligation_scoped_inputs as prior

_PUBLIC = prior.initial.public_input
_IDENTIFY = prior.construction.identify
_HISTORY = prior.historical.history
_DIGEST = prior.construction.construction.digest
_ENCODED = prior.construction.construction.encoded
_CODES = tuple(f.__code__ for f in (_PUBLIC, _IDENTIFY, _DIGEST, _ENCODED))


def require(value, reason):
    if not value: raise ValueError('scoped_public_inputs_v2:' + reason)


def _ast(function):
    return ast.parse(textwrap.dedent(inspect.getsource(function)))


def _dump(tree): return ast.dump(tree, include_attributes=False)


def _build_public_code():
    original = _ast(_PUBLIC); tree = copy.deepcopy(original)
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Return)
        and ast.unparse(n.value) == 'construction.inputs()[case]']
    require(len(nodes) == 1, 'single_public_case_expression')
    previous = copy.deepcopy(nodes[0].value)
    nodes[0].value = ast.parse('_copy_public_case(case)', mode='eval').body
    restored = copy.deepcopy(tree)
    changed = [n for n in ast.walk(restored) if isinstance(n, ast.Return)
        and ast.unparse(n.value) == '_copy_public_case(case)']
    require(len(changed) == 1, 'single_inverse_expression')
    changed[0].value = previous
    require(_dump(restored) == _dump(original), 'public_case_inverse_AST')
    namespace = dict(_PUBLIC.__globals__)
    exec(compile(ast.fix_missing_locations(tree), '<scoped-public-case-only>', 'exec'), namespace)
    return namespace[_PUBLIC.__name__].__code__, {
        'only_public_input_return_expression_changed': True,
        'public_case_validation_AST_unchanged': True,
        'inverse_AST_exact': True,
        'original_public_input_AST_sha256': hashlib.sha256(_dump(original).encode()).hexdigest()}


def _readonly_proof():
    # This is deliberately a closed function body, not a broad purity guess.
    # Borrowed values go only to original json.dumps+sha256; the sole returned
    # object is the original immutable case-name key. No data/table escapes.
    expected = ast.parse('''def identify(data):
    key = construction.digest(data)
    matches = [name for name,value in inputs().items() if construction.digest(value)==key]
    if len(matches) != 1: raise ValueError("unsupported_fixed_input")
    return matches[0]
''')
    expected_digest = ast.parse('''def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()
''')
    expected_encoder = ast.parse('''def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
''')
    require(_dump(_ast(_IDENTIFY)) == _dump(expected), 'identify_readonly_body')
    require(_dump(_ast(_DIGEST)) == _dump(expected_digest)
        and _dump(_ast(_ENCODED)) == _dump(expected_encoder), 'borrowed_digest_readonly_body')
    return {'identify_original_code_unchanged': True,
        'borrowed_values_only_consumed_by_original_readonly_digest': True,
        'identify_returns_only_immutable_case_name': True,
        'identify_AST_sha256': hashlib.sha256(_dump(expected).encode()).hexdigest()}


_PUBLIC_CODE, _PUBLIC_PROOF = _build_public_code()
_READONLY_PROOF = _readonly_proof()


class PublicInputScope(prior.PublicInputScope):
    def __init__(self):
        super().__init__()
        self.public_case_reads = 0; self.identify_table_reads = 0

        # Only identify gets this private borrowing global. Other consumers
        # of construction.inputs keep the inherited full deepcopy interface.
        self._identify_namespace = {**self._construction_namespace, 'inputs': self._borrow_for_identify}
        identify = prior.private(_IDENTIFY, self._identify_namespace)
        self._identify_namespace['identify'] = identify
        self._construction_namespace['identify'] = identify
        self.construction.identify = identify

        self._public_case_namespace = {**self._initial_namespace, '_copy_public_case': self._copy_public_case}
        public = FunctionType(_PUBLIC_CODE, self._public_case_namespace, _PUBLIC.__name__,
            _PUBLIC.__defaults__, _PUBLIC.__closure__)
        public.__kwdefaults__ = _PUBLIC.__kwdefaults__
        self._public_case_namespace['public_input'] = public
        self._initial_namespace['public_input'] = public
        self.initial.public_input = public
        # v1 intentionally held aliases in these complete private namespaces.
        self._lifecycle_namespace['public_input'] = public
        self.lifecycle.public_input = public
        self.v2._private['public_input'] = public
        self.v2.public_input = public

        self.history, self._history_namespace = prior.clone_module(_HISTORY, {
            'base': self.initial, 'require': self.initial.require, 'finite': self.initial.finite})
        self._historical_namespace['history'] = self.history
        self.historical.history = self.history

    def _copy_public_case(self, case):
        self.public_case_reads += 1
        return copy.deepcopy(self._inputs[case])

    def _borrow_for_identify(self):
        self.identify_table_reads += 1
        return self._inputs

    def source_proof(self):
        require(prior.initial.public_input is _PUBLIC and prior.construction.identify is _IDENTIFY
            and prior.construction.construction.digest is _DIGEST
            and prior.construction.construction.encoded is _ENCODED,
            'original_function_identity_changed')
        require(all(f.__code__ is code for f,code in zip((_PUBLIC, _IDENTIFY, _DIGEST, _ENCODED), _CODES)),
            'original_function_code_changed')
        checks = {}
        for label, original, namespace in (
            ('construction', prior.construction, self._construction_namespace),
            ('initial', prior.initial, self._initial_namespace),
            ('lifecycle', prior.lifecycle, self._lifecycle_namespace),
            ('historical', prior.historical, self._historical_namespace),
            ('history', _HISTORY, self._history_namespace),
            ('context', prior.context, self._context_namespace)):
            for name, function in vars(original).items():
                if type(function) is not FunctionType or function.__module__ != original.__name__: continue
                if (label, name) in (('construction', 'inputs'), ('initial', 'public_input')): continue
                current = namespace[name]
                require(current.__code__ is function.__code__ and current.__closure__ is function.__closure__
                    and current.__defaults__ is function.__defaults__ and current.__kwdefaults__ is function.__kwdefaults__,
                    'guard_or_helper_code_changed:' + label + '.' + name)
                require(set(current.__globals__) == set(function.__globals__), 'defining_globals_lost:' + label + '.' + name)
                checks[label + '.' + name] = True
        require(self.initial.public_input.__code__ is _PUBLIC_CODE
            and self.initial.public_input.__defaults__ is _PUBLIC.__defaults__
            and self.initial.public_input.__closure__ is _PUBLIC.__closure__
            and self.initial.public_input.__kwdefaults__ is _PUBLIC.__kwdefaults__
            and set(self.initial.public_input.__globals__) == set(_PUBLIC.__globals__) | {'_copy_public_case'},
            'public_case_private_binding')
        require(self.construction.inputs.__self__ is self and self.construction.inputs.__func__ is prior.PublicInputScope.inputs
            and self.construction.identify.__globals__['inputs'].__self__ is self
            and self.construction.identify.__globals__['inputs'].__func__ is PublicInputScope._borrow_for_identify,
            'generic_copy_or_identify_binding')
        require(self.lifecycle.public_input is self.initial.public_input
            and self._lifecycle_namespace['public_input'] is self.initial.public_input
            and self.v2.public_input is self.initial.public_input
            and self.v2._private['public_input'] is self.initial.public_input
            and self._initial_namespace['public_input'] is self.initial.public_input
            and self.initial.public_input.__globals__['_copy_public_case'].__self__ is self
            and self.initial.public_input.__globals__['_copy_public_case'].__func__ is PublicInputScope._copy_public_case,
            'public_case_alias_chain')
        require(self.initial.construction is self.construction and self.lifecycle.old is self.initial
            and self.lifecycle.identify_public_case is self.initial.identify_public_case
            and self.historical.old is self.v2 and self.v2.old is self.initial
            and self.historical.history is self.history and self.history.base is self.initial
            and self.historical.validate_collected_endpoints.__globals__['history'] is self.history
            and self.history.derive_goal_service_bounds.__globals__['base'] is self.initial
            and self.context.initial is self.initial and self.context.later is self.historical
            and self.context.SuppliedContext is prior.context.SuppliedContext,
            'history_context_full_scope_chain')
        require(self.predict.__code__ is prior.lazy.predict.__code__
            and self.predict.__globals__['context'] is self.context
            and self.Projection.collect.__code__ is prior.lazy.original.Projection.collect.__code__
            and self.Projection.collect.__globals__['guard'] is self.historical
            and self.Projection.activate is prior.lazy.Projection.activate and self.Projection.run is prior.lazy.Projection.run,
            'model_or_collection_binding')
        return {**_PUBLIC_PROOF, **_READONLY_PROOF,
            'schema': 'g31.live_obligation.scoped_public_inputs.v2', 'unchanged_functions': checks,
            'generic_inputs_full_deepcopy_retained': True, 'public_case_returns_fresh_deepcopy': True,
            'historical_base_rebound_to_same_private_initial_guard': True,
            'original_fixed_input_constructor_calls_per_scope': 1,
            'new_scope_per_predict': True, 'all_existing_guards_retained': True,
            'initial_context_caller_optimization_included': False,
            'cached_observation_or_result_or_validation': False, 'global_cache': False,
            'source_domain': 'Pinned serial builtin three-case constructor and private owned table',
            'concurrent_private_or_builder_mutation_supported': False,
            'removed_allocation_failure_timing_equivalence': False,
            'per_sample_cycle_cleanup_certified': False, 'native_authority': False}


def predict(supplied_context, action):
    scope = PublicInputScope()
    return scope.predict(supplied_context, action)
