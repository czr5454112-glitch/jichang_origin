"""Unexecuted, scalar-only constructor diagnostic; no campaign installation.

The original ConstructorTimer instance and its actual constructor are retained.
Its __call__ is privately compiled with three clock points and one final hook.
The two existing exact-constructor clocks and every original statement survive
inverse AST restoration. New diagnostic failures are sticky and never replace
an original exception or become zero-duration evidence. All added work belongs
inside the caller's full root; no per-root disk write occurs here.
"""
from __future__ import annotations

import ast
import hashlib
import inspect
from pathlib import Path
import textwrap
from types import FunctionType, SimpleNamespace

from . import single_capture_static_inventory_runtime as original

SCHEMA = 'g31.constructor_prelude.instrumentation.v1'
SOURCE_SHA = '9ec4089e19232c4671ee76175ea9b6b068dc57f1e042bf2a398f1a03655b8c60'
_CALL = original.ConstructorTimer.__call__
_IDENTITY = (_CALL.__code__, _CALL.__defaults__, _CALL.__kwdefaults__, _CALL.__closure__)
_HOOKS = ('_prelude_clock', '_prelude_finish')


def require(value, reason):
    if not value:
        raise ValueError('constructor_prelude:' + reason)


def _dump(value):
    return ast.dump(value, include_attributes=False)


def _nodes(source):
    return ast.parse(source).body


_PREFIX = '''
_diag_start = _prelude_clock(self)
_diag_boundary_end = None
_diag_metadata_end = None
_diag_row = None
_diag_primary = None
'''
_HANDLER = '''
try:
    pass
except BaseException as _diag_error:
    _diag_primary = _diag_error
    raise
finally:
    _prelude_finish(self, _diag_start, _diag_boundary_end, _diag_metadata_end, _diag_row, _diag_primary)
'''


def _original_tree():
    require(original.ConstructorTimer.__call__ is _CALL
        and _CALL.__code__ is _IDENTITY[0] and _CALL.__defaults__ is _IDENTITY[1]
        and _CALL.__kwdefaults__ is _IDENTITY[2] and _CALL.__closure__ is _IDENTITY[3],
        'original_function_identity')
    require(hashlib.sha256(Path(original.__file__).read_bytes()).hexdigest() == SOURCE_SHA,
        'accepted_source_bytes')
    tree = ast.parse(textwrap.dedent(inspect.getsource(_CALL)))
    fn = tree.body[0]
    require(len(tree.body) == 1 and type(fn) is ast.FunctionDef and len(fn.body) == 5,
        'original_five_statements')
    require(_dump(fn.body[0]) == _dump(_nodes('if self.boundary is not None:\n    self.boundary.check()')[0])
        and type(fn.body[1]) is ast.Assign and type(fn.body[1].targets[0]) is ast.Name
        and fn.body[1].targets[0].id == 'row'
        and _dump(fn.body[2]) == _dump(_nodes('self.rows.append(row)')[0])
        and _dump(fn.body[3]) == _dump(_nodes("row['started_ns'] = self.clock()")[0])
        and type(fn.body[4]) is ast.Try, 'original_boundary_metadata_and_clock_positions')
    require(not set(_HOOKS).intersection(_CALL.__globals__), 'new_private_global_names')
    return tree


def _transformed():
    tree = _original_tree()
    fn = tree.body[0]
    before = fn.body
    wrapper = _nodes(_HANDLER)[0]
    wrapper.body = [before[0], *_nodes('_diag_boundary_end = _prelude_clock(self)'),
        before[1], *_nodes('_diag_row = row'), before[2],
        *_nodes('_diag_metadata_end = _prelude_clock(self)'), *before[3:]]
    fn.body = [*_nodes(_PREFIX), wrapper]
    _inverse(tree)
    return ast.fix_missing_locations(tree)


def _inverse(tree):
    """Reject any extra change, then recover the complete original function."""
    restored = ast.parse(ast.unparse(tree))
    fn = restored.body[0]
    prefix = _nodes(_PREFIX)
    require(len(fn.body) == len(prefix) + 1
        and all(_dump(a) == _dump(b) for a, b in zip(fn.body, prefix)), 'exact_diagnostic_prefix')
    outer = fn.body[-1]
    expected = _nodes(_HANDLER)[0]
    require(type(outer) is ast.Try and not outer.orelse
        and _dump(ast.Module(body=outer.handlers, type_ignores=[])) == _dump(ast.Module(body=expected.handlers, type_ignores=[]))
        and _dump(ast.Module(body=outer.finalbody, type_ignores=[])) == _dump(ast.Module(body=expected.finalbody, type_ignores=[]))
        and len(outer.body) == 8, 'exact_finally_and_original_exception_priority')
    for index, code in ((1, '_diag_boundary_end = _prelude_clock(self)'),
                        (3, '_diag_row = row'), (5, '_diag_metadata_end = _prelude_clock(self)')):
        require(_dump(outer.body[index]) == _dump(_nodes(code)[0]), 'exact_inserted_clock_or_local')
    fn.body = [outer.body[i] for i in (0, 2, 4, 6, 7)]
    require(_dump(restored) == _dump(_original_tree()), 'complete_inverse_AST')
    return restored


class _Probe:
    """Serial scalar sidecar. Nothing stores an exception or authority object."""
    def __init__(self, rows):
        require(type(rows) is list and not rows, 'fresh_exact_diagnostic_rows')
        self.rows = rows
        self.failed = False
        self.errors = []

    def _failure(self, phase, error):
        self.failed = True
        try:
            self.errors.append({'phase': phase, 'error_type': type(error).__name__})
        except BaseException:
            pass

    def clock(self, timer):
        try:
            value = timer.clock()
            require(type(value) is int and value >= 0, 'exact_nonnegative_clock')
            return value
        except BaseException as error:
            self._failure('additional_clock', error)
            return None

    def finish(self, timer, start, boundary_end, metadata_end, original_row, primary):
        # Called in a finally clause. The original exception/return wins over
        # every diagnostic exception, even MemoryError or a clock exception.
        try:
            finished = self.clock(timer)
            row = original_row if type(original_row) is dict else {}
            fields = row.get('root')
            root = None
            if type(fields) is dict:
                kinds = {'request_id': str, 'started_ns': int, 'deadline_ns': int, 'cutoff_ns': int}
                require(set(fields) == set(kinds) and all(v is None or type(v) is kinds[k] for k, v in fields.items()),
                    'original_scalar_root_fields')
                root = dict(fields)
            result = {'ordinal': len(self.rows), 'root': root,
                'original_constructor_ordinal': row.get('ordinal'),
                'original_constructor_status': row.get('status'),
                'original_constructor_error_type': row.get('error_type'),
                'original_exception_type': None if primary is None else type(primary).__name__,
                'boundary_started_ns': start, 'boundary_finished_ns': boundary_end,
                'metadata_finished_ns': metadata_end,
                'constructor_started_ns': row.get('started_ns'),
                'constructor_finished_ns': row.get('finished_ns'),
                'diagnostic_finished_ns': finished,
                'status': 'unknown_partial_or_failed_diagnostic', 'intervals_ns': None,
                'is_CPU_or_zero_cost_instrumentation': False,
                'post_final_clock_export_cost_is_inside_complete_root_not_this_span': True}
            points = [start, boundary_end, metadata_end, row.get('started_ns'), row.get('finished_ns'), finished]
            if all(type(v) is int and v >= 0 for v in points) and points == sorted(points):
                names = ('original_boundary_check', 'root_fields_row_and_append',
                    'metadata_to_original_clock_gap', 'existing_exact_constructor', 'post_constructor_diagnostic_tail')
                result['intervals_ns'] = {name: b - a for name, a, b in zip(names, points, points[1:])}
                if primary is None and row.get('status') == 'constructor_returned' and not self.failed:
                    result['status'] = 'complete_scalar_intervals'
            self.rows.append(result)
        except BaseException as error:
            self._failure('final_scalar_sidecar', error)

    def binding_failed(self, start, finish, error):
        try:
            self.rows.append({'ordinal': len(self.rows), 'status': 'unknown_instrumentation_binding_rejected',
                'binding_started_ns': start, 'binding_finished_ns': finish,
                'original_exception_type': type(error).__name__, 'original_constructor_ordinal': None,
                'root': None, 'intervals_ns': None})
        except BaseException as failure:
            self._failure('binding_failure_sidecar', failure)

    def attach_binding(self, ordinal, start, end):
        try:
            require(len(self.rows) == ordinal + 1, 'one_diagnostic_per_invocation')
            row = self.rows[ordinal]
            row.update(binding_started_ns=start, binding_finished_ns=end,
                binding_scope='New instrumentation source-bound check; additional wall, separate from the original boundary.check.')
            if not (type(start) is int and type(end) is int and 0 <= start <= end
                    and type(row['boundary_started_ns']) is int and end <= row['boundary_started_ns']):
                row['status'] = 'unknown_binding_clock'
        except BaseException as error:
            self._failure('binding_scalar_sidecar', error)


class _Call:
    def __init__(self, timer, function, probe):
        self.timer, self.function, self.probe = timer, function, probe
        self.boundary = None
        self._boundary_expected = None

    def __call__(self, session, client, root, policies):
        start = self.probe.clock(self.timer)
        try:
            require(self.boundary is self._boundary_expected
                and type(self.boundary) is original.static._ProgramBoundary,
                'instrumentation_boundary_identity')
            self.boundary.check()
        except BaseException as error:
            self.probe.binding_failed(start, self.probe.clock(self.timer), error)
            raise
        end = self.probe.clock(self.timer)
        ordinal = len(self.probe.rows)
        try:
            return self.function(self.timer, session, client, root, policies)
        finally:
            self.probe.attach_binding(ordinal, start, end)


def bind_timer(timer, diagnostic_rows):
    """Bind an existing accepted timer, not a native/C provider or campaign.

Synthetic tests can create an exact ConstructorTimer with a fake constructor.
That does not grant native authority or establish actual C support.
"""
    require(type(timer) is original.ConstructorTimer, 'exact_accepted_timer')
    probe = _Probe(diagnostic_rows)
    tree = _transformed()
    namespace = dict(_CALL.__globals__)
    namespace.update(_prelude_clock=probe.clock, _prelude_finish=probe.finish)
    scratch = dict(namespace)
    exec(compile(tree, '<constructor_prelude_private_call>', 'exec'), scratch)
    code = scratch[_CALL.__name__].__code__
    require(code.co_freevars == _CALL.__code__.co_freevars, 'original_classcell_and_freevars')
    function = FunctionType(code, namespace, _CALL.__name__, _CALL.__defaults__, _CALL.__closure__)
    function.__kwdefaults__ = _CALL.__kwdefaults__
    call = _Call(timer, function, probe)
    call.boundary = original.static._ProgramBoundary(functions=(function,), classes=(_Probe, _Call),
        locations=((timer, 'exact_class'), (timer, 'rows'), (timer, 'clock'), (timer, 'boundary'),
            (call, 'timer'), (call, 'function'), (call, 'probe'), (probe, 'rows')))
    call._boundary_expected = call.boundary
    result = SimpleNamespace(call=call, function=function, timer=timer, probe=probe,
        generated_AST_sha256=hashlib.sha256(_dump(tree).encode()).hexdigest(),
        generated_code=code, instrumentation_boundary=call.boundary)
    source_proof(result)
    return result


def source_proof(value):
    tree = _transformed()
    fn, probe, timer, call = value.function, value.probe, value.timer, value.call
    require(type(timer) is original.ConstructorTimer and type(call) is _Call and type(probe) is _Probe
        and call.timer is timer and call.function is fn and call.probe is probe
        and call.boundary is call._boundary_expected is value.instrumentation_boundary, 'exact_new_binding')
    require(fn.__code__ is value.generated_code and fn.__defaults__ is _CALL.__defaults__
        and fn.__kwdefaults__ is _CALL.__kwdefaults__ and fn.__closure__ is _CALL.__closure__
        and fn.__code__.co_freevars == _CALL.__code__.co_freevars, 'complete_generated_function_identity')
    require(set(fn.__globals__) == set(_CALL.__globals__) | set(_HOOKS)
        and all(fn.__globals__[k] is v for k, v in _CALL.__globals__.items()), 'complete_original_defining_globals')
    require(fn.__globals__['_prelude_clock'].__self__ is probe
        and fn.__globals__['_prelude_clock'].__func__ is _Probe.clock
        and fn.__globals__['_prelude_finish'].__self__ is probe
        and fn.__globals__['_prelude_finish'].__func__ is _Probe.finish, 'exact_private_hooks')
    require(value.generated_AST_sha256 == hashlib.sha256(_dump(tree).encode()).hexdigest(), 'generated_tree_pin')
    value.instrumentation_boundary.check()
    return {'schema': SCHEMA, 'original_source_sha256': SOURCE_SHA,
        'complete_inverse_AST_exact': True, 'original_body_and_exact_constructor_clock_statements_unchanged': True,
        'original_full_globals_defaults_kwdefaults_closure_and_freevars_kept': True,
        'exact_original_timer_and_actual_constructor_class_kept': True,
        'new_binding_guard_is_separately_timed_and_charged': True,
        'original_exception_precedes_diagnostic_failures': True,
        'diagnostic_failures_are_sticky_and_not_zero_duration': True,
        'native_session_client_root_policy_references_in_sidecar': False,
        'per_root_disk_write': False, 'Provider_or_campaign_integration': False,
        'actual_native_C_or_model_execution': False, 'complete100ms_certified': False,
        'resource_failure_timing_equivalence_claimed': False}
