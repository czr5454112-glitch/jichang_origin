"""Experimental v2 typed writer: only the numeric groups in each job change.

Not installed in any policy/native adapter. The fast path checks exact builtin
ownership before using the original traversal. Unsupported shapes invoke the
original function once; resource failures are never retried. This module does
not validate delivery, freshness, permissions, or the meaning of a capture.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import struct
import textwrap
from types import FunctionType, SimpleNamespace

from . import planning_capture_v2_digest as original

_ORIGINAL = original.capture_digest_v2
_LOCAL = original._write_local_capture
_ORIGINAL_CODE, _LOCAL_CODE = _ORIGINAL.__code__, _LOCAL.__code__
_MASK = (1 << 64) - 1
_PREFIX = struct.Struct('>QQddQdddddBB')
_SUFFIX = struct.Struct('>ddd')
_LENGTH = struct.Struct('>Q')


class _Unsupported(Exception):
    """A no-user-hook fast attempt may fall back exactly once."""


def _builtin_tree(value):
    """No callbacks, coercions or custom-key lookup during eligibility checks.

Cycles fall back to the original finite field traversal; shared aliases are
allowed. All state is per-call. NaN/inf are allowed here: the original writer
encodes them even though some callers impose a stricter finite schema.
"""
    active, done = set(), set()
    pending = [(value, False)]
    while pending:
        item, leaving = pending.pop()
        kind = type(item)
        if kind is str or kind is int or kind is float or kind is bool or item is None:
            continue
        if kind is not dict and kind is not list:
            raise _Unsupported()
        identity = id(item)
        if leaving:
            active.remove(identity); done.add(identity)
            continue
        if identity in done:
            continue
        if identity in active:
            raise _Unsupported()
        active.add(identity); pending.append((item, True))
        if kind is dict:
            # Check keys without equality/membership against user objects.
            # Only after this loop may the original string lookups execute.
            for key in item:
                if type(key) is not str:
                    raise _Unsupported()
            pending.extend((child, False) for child in item.values())
        else:
            pending.extend((child, False) for child in item)


def _double_supported(value):
    kind = type(value)
    # Arbitrary-size ints remain supported in integer slots. In a double slot
    # large int conversion can overflow; leave exact error precedence to the
    # original traversal rather than eagerly converting or masking it.
    return kind is float or kind is bool or (kind is int and value.bit_length() <= 63)


def _write_job_batched(data, job):
    if type(job) is not dict:
        raise _Unsupported()
    try:
        identity = job['business_bag_id']
        values = (job['origin'], job['destination'], job['arrival'], job['deadline'],
            job['storage_node'], job['storage_release_at'], job['storage_min_dwell'],
            job['load_seconds'], job['unload_seconds'], job['hold_seconds'],
            job['protected_service'], job['allow_suffix_reroute'])
        status = job['status']
        suffix = (job['loaded_at'], job['storage_entered_at'], job['storage_released_at'])
    except KeyError:
        # Gathering a group must not replace an earlier original type/encoding
        # error with a later missing-field error. The original decides order.
        raise _Unsupported() from None
    if type(identity) is not str or type(status) is not str:
        raise _Unsupported()
    for index in (0, 1, 4):
        kind = type(values[index])
        if kind is not int and kind is not bool:
            raise _Unsupported()
    if not all(_double_supported(values[index]) for index in (2, 3, 5, 6, 7, 8, 9)):
        raise _Unsupported()
    if type(values[10]) is not bool or type(values[11]) is not bool:
        raise _Unsupported()
    if not all(_double_supported(value) for value in suffix):
        raise _Unsupported()
    encoded = identity.encode('utf-8')
    data.extend(_LENGTH.pack(len(encoded))); data.extend(encoded)
    data.extend(_PREFIX.pack(values[0] & _MASK, values[1] & _MASK,
        values[2], values[3], values[4] & _MASK, *values[5:10],
        1 if values[10] else 0, 1 if values[11] else 0))
    encoded = status.encode('utf-8')
    data.extend(_LENGTH.pack(len(encoded))); data.extend(encoded)
    data.extend(_SUFFIX.pack(*suffix))


def _clone(function, namespace):
    cloned = FunctionType(function.__code__, namespace, function.__name__,
        function.__defaults__, function.__closure__)
    cloned.__kwdefaults__ = function.__kwdefaults__
    return cloned


def _build_local():
    tree = ast.parse(textwrap.dedent(inspect.getsource(_LOCAL)))
    baseline = copy.deepcopy(tree)
    loops = [node for node in ast.walk(tree) if isinstance(node, ast.For)
        and ast.unparse(node.target) == 'job' and ast.unparse(node.iter) == "body['jobs']"]
    if len(loops) != 1:
        raise ValueError('batched_writer_job_loop_inventory')
    previous = copy.deepcopy(loops[0].body)
    loops[0].body = ast.parse('_write_job_batched(data, job)').body
    inverse = copy.deepcopy(tree)
    next(node for node in ast.walk(inverse) if isinstance(node, ast.For)
        and ast.unparse(node.target) == 'job').body = previous
    if ast.dump(inverse, include_attributes=False) != ast.dump(baseline, include_attributes=False):
        raise ValueError('batched_writer_inverse_AST')
    namespace = {**_LOCAL.__globals__, '_write_job_batched': _write_job_batched}
    exec(compile(ast.fix_missing_locations(tree), '<v2-batched-job-only>', 'exec'), namespace)
    return namespace[_LOCAL.__name__], {
        'only_job_loop_body_changed': True, 'inverse_AST_exact': True,
        'original_AST_sha256': hashlib.sha256(ast.dump(baseline,
            include_attributes=False).encode()).hexdigest(),
        'prefix_format': _PREFIX.format, 'suffix_format': _SUFFIX.format}


class _BufferResult:
    """Private hash facade exposes the exact pre-SHA buffer for byte tests."""
    __slots__ = ('data',)
    def __init__(self, data): self.data = data
    def hexdigest(self): return self.data


_BATCHED_LOCAL, _AST_PROOF = _build_local()
_BUFFER_HASH = SimpleNamespace(sha256=_BufferResult)
_REFERENCE_BUFFER = _clone(_ORIGINAL, {**_ORIGINAL.__globals__, 'hashlib': _BUFFER_HASH})
_BATCHED_BUFFER = _clone(_ORIGINAL, {**_ORIGINAL.__globals__,
    'hashlib': _BUFFER_HASH, '_write_local_capture': _BATCHED_LOCAL})


def _fast_buffer(body):
    _builtin_tree(body)
    return _BATCHED_BUFFER(body)


def reference_bytes_v2(body):
    """Original encoding code and original local writer; only final hash replaced."""
    return bytes(_REFERENCE_BUFFER(body))


def typed_bytes_v2(body):
    """Test/diagnostic API; no bytes or input reference escapes on failure."""
    try:
        return bytes(_fast_buffer(body))
    except _Unsupported:
        return reference_bytes_v2(body)


def capture_digest_v2(body):
    try:
        data = _fast_buffer(body)
    except _Unsupported:
        return _ORIGINAL(body)
    return hashlib.sha256(data).hexdigest()


def source_proof():
    if original.capture_digest_v2 is not _ORIGINAL or original._write_local_capture is not _LOCAL:
        raise ValueError('batched_writer_original_identity_changed')
    if _ORIGINAL.__code__ is not _ORIGINAL_CODE or _LOCAL.__code__ is not _LOCAL_CODE:
        raise ValueError('batched_writer_original_code_changed')
    if _REFERENCE_BUFFER.__code__ is not _ORIGINAL_CODE or _BATCHED_BUFFER.__code__ is not _ORIGINAL_CODE:
        raise ValueError('batched_writer_outer_code_changed')
    if _REFERENCE_BUFFER.__globals__['_write_local_capture'] is not _LOCAL:
        raise ValueError('batched_writer_reference_changed')
    if _BATCHED_BUFFER.__globals__['_write_local_capture'] is not _BATCHED_LOCAL:
        raise ValueError('batched_writer_private_binding_changed')
    return {**_AST_PROOF, 'schema': 'g31.planning_v2_digest.batched_source.v1',
        'outer_original_code_defaults_closure_unchanged': True,
        'original_module_globals_unchanged': True,
        'fallback_trigger': 'Only private Unsupported; exactly one original call',
        'resource_failure_equivalence': False,
        'preflight_scope': 'Entire exact builtin tree, per-call; overhead is charged and gain unknown',
        'policy_authority_added': False, 'native_installation': False}
