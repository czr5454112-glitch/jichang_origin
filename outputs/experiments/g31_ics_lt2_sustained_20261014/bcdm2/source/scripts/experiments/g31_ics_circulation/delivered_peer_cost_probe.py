"""Private timers around the ORIGINAL delivered validator and typed digest.

This diagnostic preserves original code/defaults/closures/full globals. It is
not a fast validator, policy replay, observation source or execution authority.
Each fixed call records its original accepted/absent/rejected disposition;
resource failures propagate. Only O(1) counters are retained by the timer.
"""
from __future__ import annotations
import math
import time
from types import FunctionType
from . import research_original_low_wip as original

_VALIDATOR = original.delivered_peer
_DIGEST = original.capture_digest_v2
_CODE = _VALIDATOR.__code__
_GLOBALS = dict(_VALIDATOR.__globals__)


def require(value, reason):
    if not value: raise ValueError('delivered_peer_probe:' + reason)


class DigestTimer:
    def __init__(self, digest, clock=time.perf_counter_ns):
        self.digest, self.clock = digest, clock
        self.entered = self.completed = self.raised = self.nanoseconds = 0
        self.failed = False

    def __call__(self, body):
        self.entered += 1
        start = self.clock()
        succeeded = False
        try:
            result = self.digest(body)
            succeeded = True
            self.completed += 1
            return result
        finally:
            if not succeeded: self.raised += 1
            try:
                end = self.clock()
                require(type(start) is int and type(end) is int and 0 <= start <= end, 'digest_clock')
                self.nanoseconds += end-start
            except BaseException:
                self.failed = True
                # Preserve an original digest exception. If the digest
                # succeeded, the broken measurement must still fail closed.
                if succeeded: raise


def bind(timer):
    require(type(timer) is DigestTimer and timer.digest is _DIGEST, 'original_digest_timer')
    namespace = {**_VALIDATOR.__globals__, 'capture_digest_v2': timer}
    function = FunctionType(_VALIDATOR.__code__, namespace, _VALIDATOR.__name__,
                            _VALIDATOR.__defaults__, _VALIDATOR.__closure__)
    function.__kwdefaults__ = _VALIDATOR.__kwdefaults__
    require(set(namespace) == set(_VALIDATOR.__globals__) and all(
        namespace[k] is v for k,v in _VALIDATOR.__globals__.items() if k != 'capture_digest_v2'),
        'unchanged_all_other_globals')
    return function


def source_proof():
    require(original.delivered_peer is _VALIDATOR and _VALIDATOR.__code__ is _CODE
        and original.capture_digest_v2 is _DIGEST and set(_VALIDATOR.__globals__) == set(_GLOBALS)
        and all(_VALIDATOR.__globals__[k] is v for k,v in _GLOBALS.items()), 'original_source_identity')
    return {'original_validator_code': True, 'original_digest': True,
        'private_changed_global_only': 'capture_digest_v2', 'per_call_body_copy_or_hash_in_timer': False,
        'not_policy_frequency_or_full_day_acceptance': True, 'not_optimized_arm': True}


def arguments(row, public):
    """Static original contract plus exact query owner and query physical time.

    The peer is selected from the declared two-owner contract, never guessed
    from the envelope. All envelopes are passed intact to the original guard.
    No final owner state or late policy checkpoint is reconstructed here.
    """
    require(type(row) is dict and row.get('endpoint') == 'protocol_planning_snapshots_v2'
        and type(row.get('args')) is list and len(row['args']) == 1
        and row.get('kwargs') == {} and 'error' not in row, 'original_query')
    require(type(row.get('before')) in (int,float) and type(row.get('after')) is type(row['before'])
        and math.isfinite(row['before']) and row['before'] >= 0 and row['before'] == row['after'], 'query_clock')
    nodes = {n['node']: n for n in public['node_contracts']}
    require(len(nodes) == len(public['node_contracts']), 'duplicate_static_nodes')
    owners = sorted({n['resource_owner'] for n in nodes.values()})
    owner = row['args'][0]
    require(len(owners) == 2 and type(owner) is str and owner in owners, 'declared_two_owner_scope')
    require(type(row.get('result')) is list, 'complete_envelope_list')
    return row['result'], owner, next(p for p in owners if p != owner), row['before'], nodes


def invoke(function, args):
    """Record ordinary original rejections; never convert resource failures."""
    try:
        value = function(*args)
    except (ValueError, KeyError, TypeError) as exc:
        return {'status': 'rejected', 'exception_type': type(exc).__name__, 'exception_text': str(exc)}
    if value is None: return {'status': 'absent'}
    require(len(args[0]) == 1 and value is args[0][0], 'unexpected_original_return_identity')
    # Full returned envelope remains available to the outer saved-output audit.
    return {'status': 'accepted', 'envelope': value}


def measure(args, arm, clock=time.perf_counter_ns):
    require(arm in ('A','B'), 'arm')
    timer = DigestTimer(_DIGEST, clock) if arm == 'B' else None
    function = bind(timer) if timer is not None else _VALIDATOR
    # Private function/timer construction is setup, separately charged in the
    # harness whole span. This callable span measures the validator itself.
    begin = clock()
    value = invoke(function, args)
    end = clock()
    require(type(begin) is int and type(end) is int and 0 <= begin <= end, 'validator_clock')
    metrics = {'validator_ns': end-begin, 'started_ns': begin, 'finished_ns': end,
        'digest_entered': None, 'digest_completed': None, 'digest_raised': None,
        'digest_ns': None, 'validator_outside_digest_ns': None}
    if timer is not None:
        require(not timer.failed and timer.entered == timer.completed+timer.raised
            and timer.entered <= 1 and 0 <= timer.nanoseconds <= end-begin, 'nested_clock_or_count')
        metrics.update(digest_entered=timer.entered, digest_completed=timer.completed,
            digest_raised=timer.raised, digest_ns=timer.nanoseconds,
            validator_outside_digest_ns=end-begin-timer.nanoseconds)
    return value, metrics
