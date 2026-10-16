"""One actual initial endpoint triplet; no duplicate evidence-only queries.

Source/pure prototype. It is not installed in a campaign or predictor image.
All native authority, dynamic validation and session-bound ledger code remains
the frozen implementation. Only private instrumentation and representation
ownership change; neither caller JSON nor a session proxy supplies authority.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import inspect
import time
from types import FunctionType, SimpleNamespace
from . import native_preexisting_v3_bound_adapter as adapter
from . import initial_owner_route_json_v3 as normalization

rolling = adapter.previous
initial = rolling.initial_adapter
_BOUND = adapter.collect_initial_ledger
_ROLLING = rolling.collect_initial_ledger
_NATIVE = initial.collect_native
_VALIDATE = initial.validate_pair
_NORMALIZE = normalization.normalize
_IDENTITIES = tuple((fn, fn.__code__) for fn in (_BOUND, _ROLLING, _NATIVE, _VALIDATE, _NORMALIZE))
_FIELDS = ('view', 'command', 'received')
_CALLS = ('session.observe_protocol(owner)', 'session.protocol_command(owner, own_request_id)',
          'session.protocol_planning_snapshots(owner)')


def require(value, reason):
    if not value:
        raise ValueError('initial_single_capture:'+reason)


def clone(function, namespace):
    value = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    value.__kwdefaults__ = function.__kwdefaults__
    return value


class _Capture:
    __slots__ = ('owner', 'identity', 'values', 'started', 'completed', 'active')

    def __init__(self, owner, identity):
        self.owner, self.identity = owner, identity
        self.values, self.started, self.completed = {}, [], []
        self.active = None

    def before(self, name):
        require(self.active is None and len(self.completed) < 3
            and name == _FIELDS[len(self.completed)], 'endpoint_start_order')
        self.active = name
        self.started.append({'endpoint': name, 'started_ns': time.perf_counter_ns()})

    def after(self, name, value):
        require(self.active == name and name not in self.values, 'endpoint_return_order')
        # Values never leave this private synchronous collection before fresh
        # normalization; validator consumes them read-only (copied model rows).
        self.values[name] = value
        self.completed.append(name)
        self.active = None

    def endpoints(self, at=None):
        result = {'owner': self.owner, 'request_id': self.identity}
        if at is not None:
            result['at'] = at
        result.update(self.values)
        return result


def _compile_native_template():
    tree = ast.parse(inspect.getsource(_NATIVE))
    original_ast = ast.dump(tree, include_attributes=False)
    function = tree.body[0]
    replacements, expanded = [], []
    for statement in function.body:
        field = statement.targets[0].id if (isinstance(statement, ast.Assign)
            and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name)) else None
        if field in _FIELDS:
            expected = ast.parse(_CALLS[_FIELDS.index(field)], mode='eval').body
            require(ast.dump(statement.value, include_attributes=False) == ast.dump(expected, include_attributes=False),
                    'endpoint_expression_drift')
            before = ast.parse(f"_capture.before('{field}')").body[0]
            after = ast.parse(f"_capture.after('{field}', {field})").body[0]
            expanded.extend((before, statement, after))
            replacements.extend((ast.dump(before, include_attributes=False), ast.dump(after, include_attributes=False)))
        else:
            expanded.append(statement)
    require(len(replacements) == 6 and '_capture' not in _NATIVE.__globals__, 'endpoint_hook_count')
    function.body = expanded
    restored = copy.deepcopy(tree)
    restored.body[0].body = [s for s in restored.body[0].body if ast.dump(s, include_attributes=False) not in replacements]
    require(ast.dump(restored, include_attributes=False) == original_ast, 'native_inverse_AST')
    namespace = {**_NATIVE.__globals__, '_capture': None}
    exec(compile(ast.fix_missing_locations(tree), inspect.getsourcefile(_NATIVE), 'exec'), namespace)
    return namespace[_NATIVE.__name__], {'native_AST_sha256': hashlib.sha256(original_ast.encode()).hexdigest(),
        'inverse_AST_exact': True, 'inserted_before_after_hooks': 6}


_TEMPLATE, _AST_PROOF = _compile_native_template()


def instrument_native(capture):
    require(type(capture) is _Capture, 'private_capture_type')
    # Only input-independent code is compiled at module startup. Every call
    # receives its own capture object and original complete global namespace.
    return clone(_TEMPLATE, {**_NATIVE.__globals__, '_capture': capture}), dict(_AST_PROOF)


def source_proof():
    require(adapter.collect_initial_ledger is _BOUND and rolling.collect_initial_ledger is _ROLLING
        and initial.collect_native is _NATIVE and initial.validate_pair is _VALIDATE
        and normalization.normalize is _NORMALIZE
        and all(fn.__code__ is code for fn, code in _IDENTITIES), 'source_identity_drift')
    return {**_AST_PROOF, 'schema': 'g31.initial_owner.single_capture.source_proof.v1',
        'native_authority_checks_removed': 0, 'ledger_constructor_and_token_unchanged': True,
        'private_namespaces_only': True, 'old_frozen_sources_changed': False,
        'AST_compilation': 'Input-independent module startup only; no request data cached.',
        'final_revalidation_requirement_unchanged': True, 'campaign_installed': False}


def collector(capture):
    source_proof()
    native_function, _ = instrument_native(capture)
    private_initial = SimpleNamespace(**{**vars(initial), 'collect_native': native_function})
    rolling_function = clone(_ROLLING, {**_ROLLING.__globals__, 'initial_adapter': private_initial})
    private_rolling = SimpleNamespace(**{**vars(rolling), 'collect_initial_ledger': rolling_function})
    return clone(_BOUND, {**_BOUND.__globals__, 'previous': private_rolling})


def captured_collection(records, native, session, owner, identity, *, accepted):
    """Fresh policy value and separately owned evidence; real ledger unchanged.

Successful record fields/order match the previous captured_collection shape.
Only failed/incomplete reads add capture_failure; none can be called complete.
The new code is deliberately not a final-revalidation cache.
"""
    require(type(records) is list, 'records_not_builtin_list')
    capture = _Capture(owner, identity)
    record = {'information': None, 'endpoints': capture.endpoints(), 'ledger': None}
    records.append(record)
    information = None
    try:
        information, ledger = collector(capture)(native, session, owner, identity, accepted=accepted)
        safe = _NORMALIZE(information)
        at = session.physical_time if capture.completed else None
        endpoints = _NORMALIZE(capture.endpoints(at))
        # The prior successful-path raw information copy was overwritten after
        # normalization. Build only the surviving independent record copy.
        record['information'] = copy.deepcopy(safe)
        record['endpoints'] = endpoints
        record['ledger'] = ledger.audit_copy() if ledger is not None else None
        if capture.completed != list(_FIELDS):
            require(safe.get('native_delivery_verified') is not True, 'incomplete_verified_collection')
            record['capture_failure'] = {'status': 'unknown_incomplete_endpoint_collection',
                'completed': list(capture.completed), 'active': capture.active, 'started': copy.deepcopy(capture.started)}
        return safe, ledger
    except BaseException as error:
        failure = {'status': 'unknown_failed_collection', 'error_type': type(error).__name__, 'error': str(error),
                   'completed': list(capture.completed), 'active': capture.active, 'started': copy.deepcopy(capture.started)}
        try:
            failure['typed_returned_prefix'] = normalization.typed_failure_snapshot(
                {'information': information, 'endpoints': capture.endpoints()})
        except BaseException as capture_error:
            failure['prefix_export_error'] = repr(capture_error)
        record['capture_failure'] = failure
        raise
