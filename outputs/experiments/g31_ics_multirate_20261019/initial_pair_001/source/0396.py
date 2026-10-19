"""Experimental exact no-op tick tail, independent of prefix sharing.

All physical and protocol events still execute normally. A tail is eligible
only after every declared job completed, every request is terminal, no future
E recovery can occur, and every remaining event is an immutable scalar tick.
Even then every heap pop, clock assignment and event-budget increment remains.
No complete-request or native execution certificate is supplied.
"""
from __future__ import annotations
import ast
import builtins
import copy
import hashlib
import heapq
import inspect
import math
from pathlib import Path
import textwrap
from types import FunctionType

from . import public_preference_request_context as base

EXPECTED_CONTEXT = '9c64e97e1e954a3639696ba5ca1f72f9f85e07032121f389b7e34507dfa71c3c'


def quiet_suffix(projection):
    """Sufficient, deliberately incomplete proof that all future ticks do nothing."""
    if projection.completed.keys() != projection.jobs.keys():
        return False
    if any(request['terminal'] is not True for request in projection.requests):
        return False
    request = projection.last_supply
    tray = projection.trays['E']
    # Reject even a recovery whose time threshold has not arrived yet: a later
    # tick could satisfy it. Only time-independent disabling facts suffice.
    if (request and request['terminal'] and request['ack'] == 'rejected'
            and len([r for r in projection.requests if r['tray'] == 'E']) < 16
            and tray['mode'] == 'empty' and tray['node'] == 5):
        return False
    return all(type(event) is tuple and len(event) == 5 and
        type(event[0]) is float and math.isfinite(event[0]) and
        type(event[1]) is int and type(event[2]) is int and
        event[3] == 'tick' and event[4] == () for event in projection.events)


def consume_quiet_suffix(projection, count):
    """Retain the exact heap consumption/time/count/overflow semantics."""
    while projection.events:
        projection.time, _, _, _, _ = heapq.heappop(projection.events)
        if projection.time > base.original.legacy.HORIZON:
            break
        count += 1
        if count > 20000:
            return count, True
    return count, False


def compile_quiet_run():
    # The untouched RequestContext constructor executes its complete guard
    # compilation below. Do not compile that same guard twice in one request.
    for module, expected in ((base.original, base.EXPECTED_SOURCE),
                             (base.original.legacy, base.EXPECTED_LEGACY)):
        if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() != expected:
            raise ValueError('quiet_context:projection_source_changed')
    tree = ast.parse(textwrap.dedent(inspect.getsource(base.original.Projection.run)))
    before = ast.dump(tree, include_attributes=False)
    loops = [n for n in tree.body[0].body if isinstance(n, ast.While)]
    if len(loops) != 1:
        raise ValueError('quiet_context:loop_shape_changed')
    loop = loops[0]
    if (ast.unparse(loop.body[0]) != 'self.time, _, _, kind, args = heapq.heappop(self.events)'
            or ast.unparse(loop.body[1]) != 'if self.time > legacy.HORIZON:\n    break'
            or ast.unparse(loop.body[2]) != 'count += 1'
            or ast.unparse(loop.body[3]) != "if count > 20000:\n    return {'status': 'unknown_event_budget', 'completion': self.completed}"):
        raise ValueError('quiet_context:budget_or_pop_changed')
    branches = [n for n in ast.walk(tree) if isinstance(n, ast.If)
                and ast.unparse(n.test) == "kind == 'tick'"]
    if len(branches) != 1 or ast.unparse(branches[0].body[0]) != 'self.tick()' or len(branches[0].body) != 1:
        raise ValueError('quiet_context:tick_dispatch_changed')
    branch = branches[0]
    addition = ast.parse('''
if len(self.completed) == len(self.jobs) and _quiet_suffix(self):
    count, quiet_budget_exceeded = _consume_quiet_suffix(self, count)
    if quiet_budget_exceeded:
        return {'status': 'unknown_event_budget', 'completion': self.completed}
    break
''').body[0]
    branch.body.insert(0, addition)
    restored = copy.deepcopy(tree)
    restored_branch = [n for n in ast.walk(restored) if isinstance(n, ast.If)
                       and ast.unparse(n.test) == "kind == 'tick'"][0]
    del restored_branch.body[0]
    if ast.dump(restored, include_attributes=False) != before:
        raise ValueError('quiet_context:non_tail_handler_changed')
    namespace = {**base.original.Projection.run.__globals__,
                 '_quiet_suffix': quiet_suffix, '_consume_quiet_suffix': consume_quiet_suffix}
    exec(compile(ast.fix_missing_locations(tree), __file__ + ':exact_tick_tail', 'exec'), namespace)
    return namespace['run']


class QuietRequestContext(base.RequestContext):
    """Same one-request constructor and guards; only its private run changes."""
    def __init__(self, bundle):
        if hashlib.sha256(Path(base.__file__).read_bytes()).hexdigest() != EXPECTED_CONTEXT:
            raise ValueError('quiet_context:context_source_changed')
        run = compile_quiet_run()
        def private_type(*args):
            if len(args) == 3:
                name, parents, fields = args
                if (name != '_SingleRequestProjection' or parents != (base.original.Projection,)
                        or set(fields) != {'__init__'}
                        or fields['__init__'].__code__ is not base.original.Projection.__init__.__code__):
                    raise ValueError('quiet_context:unexpected_private_class')
                return builtins.type(name, parents, {**fields, 'run': run})
            return builtins.type(*args)
        source = base.RequestContext.__init__
        init = FunctionType(source.__code__, {**source.__globals__, 'type': private_type},
                            source.__name__, source.__defaults__, source.__closure__)
        init.__kwdefaults__ = copy.deepcopy(source.__kwdefaults__)
        init(self, bundle)

    def describe(self):
        result = super().describe()
        result['version'] = 'public_preference_quiet_tail_context_v1'
        result['source_proof']['event_loop'] = 'Only proved no-op tick suffix skips tick handlers; all heap pops, time assignments, horizon checks and event counts retained.'
        result['prefix_sharing'] = False
        result['complete_100ms_certified'] = False
        return result
