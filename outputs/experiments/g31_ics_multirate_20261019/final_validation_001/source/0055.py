"""Private saved-audit binder restoring the original C JSON comparison.

No audit driver, native execution, actor-copy replacement or global patch.
"""
from __future__ import annotations
import ast
import hashlib
import inspect
from . import bridge_saved_linear_core as frozen
from . import bridge_saved_linear_progress_v2 as progress

_SEMANTIC_API = frozen.original.semantic_api
_SEMANTIC_CODE = _SEMANTIC_API.__code__
_BIND = frozen.bind
_BIND_CODE = _BIND.__code__
_REPLAY = frozen.replay_type
_REPLAY_CODE = _REPLAY.__code__
_PROGRESS_BIND = progress.bind
_PROGRESS_BIND_CODE = _PROGRESS_BIND.__code__
_SHARED_READS = progress.SharedReads
_REQUIRE = frozen.require


def semantic_equal(a, b):
    return _SEMANTIC_API(a) == _SEMANTIC_API(b)


def binder_function():
    _REQUIRE(frozen.original.semantic_api is _SEMANTIC_API
        and _SEMANTIC_API.__code__ is _SEMANTIC_CODE
        and frozen.bind is _BIND and _BIND.__code__ is _BIND_CODE
        and frozen.replay_type is _REPLAY and _REPLAY.__code__ is _REPLAY_CODE
        and progress.bind is _PROGRESS_BIND and _PROGRESS_BIND.__code__ is _PROGRESS_BIND_CODE
        and progress.SharedReads is _SHARED_READS, 'C_compare_frozen_identity_changed')
    namespace = {**_BIND.__globals__, 'SharedReads': _SHARED_READS,
                 'semantic_equal': semantic_equal}
    function = frozen.r.original.clone(_BIND, namespace)
    _REQUIRE(function.__code__ is _BIND_CODE and function.__defaults__ is _BIND.__defaults__
        and function.__closure__ is _BIND.__closure__, 'C_compare_bind_code_changed')
    return function


def source_proof():
    function = binder_function()
    # Complete original globals are retained, not copied from a neighboring
    # module whose inherited function may require missing globals.
    changed = sorted(k for k in _BIND.__globals__
                     if function.__globals__[k] is not _BIND.__globals__[k])
    _REQUIRE(changed == ['SharedReads', 'semantic_equal']
        and set(function.__globals__) == set(_BIND.__globals__), 'C_compare_global_domain')
    tree = ast.parse(inspect.getsource(_BIND))
    reference_tree = ast.parse(inspect.getsource(_SEMANTIC_API))
    return {'schema': 'g31.bridge.original_C_compare.private_bind.v1',
        'bind_bytecode_defaults_closure_unchanged': True,
        'all_original_globals_present': True,
        'only_private_global_changes': changed,
        'bind_ast_sha256': hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest(),
        'original_semantic_api_ast_sha256': hashlib.sha256(ast.dump(reference_tree, include_attributes=False).encode()).hexdigest(),
        'comparison': 'Exact original semantic_api(a) == semantic_api(b)',
        'actor_deepcopy_unchanged': True,
        'progress': 'Exact existing progress_v2.SharedReads; no capacity or aggregation change.',
        'full_audit_execution_or_acceptance': False}


def bind(plan, redirect, journal):
    proof = source_proof()
    execute = binder_function()(plan, redirect, journal)
    def run(directory):
        result, stats = execute(directory)
        stats['comparison_restore'] = proof
        return result, stats
    return run
