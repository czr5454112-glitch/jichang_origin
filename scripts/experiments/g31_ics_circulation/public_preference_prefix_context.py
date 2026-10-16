"""Opt-in supplied-data prefix sharing, with unchanged candidate semantics.

No native checkpoint/fork, no cross-request cache, no tick deletion. A cached
prefix is private and never advanced again. One whole-graph copy preserves
dynamic request aliases; only proved read-only data and scalar tick tuples
are shared. Each requested result is copied out independently.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import inspect
import math
from pathlib import Path
import textwrap
from types import FunctionType, MappingProxyType

from . import public_preference_request_context as guards
from . import public_native_preference_projection as original
from . import public_native_later_preference_projection as later

VERSION = 'public_preference_prefix_context_v1'
EXPECTED_GUARDS = '9c64e97e1e954a3639696ba5ca1f72f9f85e07032121f389b7e34507dfa71c3c'
EXPECTED_LATER = 'e81688db8664d71a1defaba1af581719f0e917bec74c99b9fb8b150825b956ac'
_END = object()
_ERRORS = (TypeError, ValueError, KeyError, OverflowError, AttributeError)
# These are assigned by the original constructors, and subsequently only
# read by the exact pinned event loop/inherited methods. potential is omitted:
# it is a per-instance mutable shortest-distance memo.
STATIC = ('b', 'service', 'travel', 'nodes', 'edges', 'outgoing', 'jobs',
          'incoming_degree', 'score_potential', 'score_potential_contract')


def _check_sources():
    for module, digest in ((guards, EXPECTED_GUARDS), (later, EXPECTED_LATER)):
        if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() != digest:
            raise ValueError('prefix_context:unreviewed_dependency_revision')


def _ast(body):
    return ast.dump(ast.Module(body=body, type_ignores=[]), include_attributes=False)


def _run_parts(cls):
    """Mechanically split the original run, retaining every handler AST."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(cls.run)))
    source = tree.body[0]
    index = next(i for i, n in enumerate(source.body) if isinstance(n, ast.While))
    loop = source.body[index]
    if (ast.unparse(loop.test) != 'self.events' or loop.orelse
            or ast.unparse(source.body[index - 1]) != 'count = 0'
            or ast.unparse(loop.body[0]) != 'self.time, _, _, kind, args = heapq.heappop(self.events)'
            or ast.unparse(loop.body[1]) != 'if self.time > legacy.HORIZON:\n    break'
            or ast.unparse(loop.body[2]) != 'count += 1'
            or ast.unparse(loop.body[3]) != "if count > 20000:\n    return {'status': 'unknown_event_budget', 'completion': self.completed}"):
        raise ValueError('prefix_context:unreviewed_event_loop_shape')
    class Counter(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id == 'count':
                return ast.copy_location(ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()),
                    attr='_prefix_count', ctx=node.ctx), node)
            return node
    class ReverseCounter(ast.NodeTransformer):
        def visit_Attribute(self, node):
            if isinstance(node.value, ast.Name) and node.value.id == 'self' and node.attr == '_prefix_count':
                return ast.copy_location(ast.Name(id='count', ctx=node.ctx), node)
            return self.generic_visit(node)
    seed = copy.deepcopy(source.body[:index])
    step = copy.deepcopy(loop.body)
    finish = copy.deepcopy(source.body[index + 1:])
    # break exits only this source loop; returning a private sentinel lets the
    # external driver finish after the exact original pop/time assignment.
    step[1].body = [ast.Return(value=ast.Name(id='_PREFIX_END', ctx=ast.Load()))]
    original_step = copy.deepcopy(step)
    original_step[1].body = [ast.Break()]
    if _ast(original_step) != _ast(loop.body): raise ValueError('prefix_context:handler_change')
    functions = []
    for name, body in (('_seed', seed), ('_step', step), ('_finish', finish)):
        converted = [Counter().visit(copy.deepcopy(n)) for n in body]
        if _ast([ReverseCounter().visit(copy.deepcopy(n)) for n in converted]) != _ast(body):
            raise ValueError('prefix_context:counter_transform_changed_other_logic')
        function = ast.parse(f'def {name}(self):\n    pass').body[0]
        function.body = converted; functions.append(function)
    namespace = {**cls.run.__globals__, '_PREFIX_END': _END}
    exec(compile(ast.fix_missing_locations(ast.Module(body=functions, type_ignores=[])),
                 __file__ + ':exact_run_split', 'exec'), namespace)
    return tuple(namespace[name] for name in ('_seed', '_step', '_finish'))


def _freeze_static(p):
    for field in STATIC:
        value = getattr(p, field)
        if type(value) is not MappingProxyType:
            value = guards._freeze(value)
        setattr(p, field, value)


def _scalar_tick(event):
    return (type(event) is tuple and len(event) == 5 and event[3] == 'tick' and event[4] == ()
        and type(event[0]) is float and math.isfinite(event[0])
        and type(event[1]) is int and type(event[2]) is int)


def clone(p):
    """Clone one dynamic graph, preserving every request alias within it."""
    memo = {id(getattr(p, key)): getattr(p, key) for key in STATIC}
    memo.update({id(event): event for event in p.events if _scalar_tick(event)})
    result = object.__new__(type(p))
    result.__dict__ = copy.deepcopy(p.__dict__, memo)
    return result


def _advance(p, step, finish, stop_kind=None):
    while p.events:
        if stop_kind is not None and p.events[0][3] == stop_kind and p.events[0][0] <= original.legacy.HORIZON:
            return ('paused', p)
        result = step(p)
        if result is _END: return ('terminal', finish(p))
        if result is not None: return ('terminal', result)
    return ('terminal', finish(p))


def _private_class(snapshot, *, is_later):
    potential = guards._freeze(original.service_aware_potential(
        snapshot['contract']['node_records'], snapshot['contract']['edge_records'], minimum_service_seconds=.001))
    def same_potential(nodes, edges, *, minimum_service_seconds):
        if (nodes is not snapshot['contract']['node_records'] or edges is not snapshot['contract']['edge_records']
                or type(minimum_service_seconds) is not float or minimum_service_seconds != .001):
            raise ValueError('prefix_context:unexpected_static_potential')
        return potential
    init = original.Projection.__init__
    private_init = FunctionType(init.__code__, {**init.__globals__, 'service_aware_potential': same_potential},
                               init.__name__, init.__defaults__, init.__closure__)
    private_init.__kwdefaults__ = copy.deepcopy(init.__kwdefaults__)
    if not is_later:
        return type('_InitialPrefixProjection', (original.Projection,), {'__init__': private_init})
    # Original later constructor differs only in its super-init target, which
    # is bound to the exact private initial constructor above. Its remaining
    # completed-prefix/return counter assignments are retained unchanged.
    tree = ast.parse(textwrap.dedent(inspect.getsource(later.LaterProjection.__init__)))
    function = tree.body[0]; first = function.body[0]
    if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Call) or ast.unparse(first.value.func) != 'super().__init__':
        raise ValueError('prefix_context:unreviewed_later_constructor')
    initial_first = copy.deepcopy(first)
    first.value.func = ast.Name(id='_private_initial_init', ctx=ast.Load())
    first.value.args.insert(0, ast.Name(id='self', ctx=ast.Load()))
    check = copy.deepcopy(first); check.value.args.pop(0); check.value.func = initial_first.value.func
    if _ast([check]) != _ast([initial_first]): raise ValueError('prefix_context:later_init_arguments_changed')
    namespace = {**later.LaterProjection.__init__.__globals__, '_private_initial_init': private_init}
    exec(compile(ast.fix_missing_locations(tree), __file__ + ':exact_later_init', 'exec'), namespace)
    return type('_LaterPrefixProjection', (later.LaterProjection,), {'__init__': namespace['__init__']})


class PrefixContext:
    """Single initial request, lazily compute only the candidate requested.

The event prefix cache is supplied-data work sharing, not native observation
authority. It is discarded with this object; new observations need a new one.
"""
    def __init__(self, bundle):
        _check_sources()
        validate, self.__action_check, proof = guards.compile_guards()
        guards._closed_tree(bundle); self.__snapshot = copy.deepcopy(bundle)
        try: checked = validate(self.__snapshot)
        except _ERRORS: checked = guards.malformed()
        self.__failure = None
        self.__roots, self.__returns, self.__results = {}, {}, {}
        self.__proof = proof
        if not (type(checked) is tuple and len(checked) == 3 and checked[0] is guards._OK):
            self.__failure = copy.deepcopy(checked); self.__actions = []; return
        _, windows, self.__numeric = checked
        self.__actions = original.vocabulary.domain(windows)['actions']
        self.__class = _private_class(self.__snapshot, is_later=False)
        self.__seed, self.__step, self.__finish = _run_parts(original.Projection)

    def actions(self): return copy.deepcopy(self.__actions)

    def predict(self, action):
        if self.__failure is not None: return copy.deepcopy(self.__failure)
        try:
            verdict = self.__action_check(action, self.__actions, self.__numeric)
            if verdict is not guards._OK: return verdict
            guards._closed_tree(action); action = copy.deepcopy(action)
            root_key = action['initial_action'], action['empty_departure']
            return_key = root_key + (action['return_delay'],)
            key = return_key + (action['later_action'],)
            if key in self.__results: return copy.deepcopy(self.__results[key])
            if root_key not in self.__roots:
                root_action = {**action, 'return_delay': 0., 'later_action': 'native_default'}
                root = self.__class(self.__snapshot, root_action); _freeze_static(root); self.__seed(root)
                self.__roots[root_key] = _advance(root, self.__step, self.__finish, 'return_decision')
            state, value = self.__roots[root_key]
            if state == 'terminal': result = value
            else:
                if return_key not in self.__returns:
                    branch = clone(value); branch.action['return_delay'] = action['return_delay']
                    self.__returns[return_key] = _advance(branch, self.__step, self.__finish, 'later_decision')
                state, value = self.__returns[return_key]
                if state == 'terminal': result = value
                else:
                    branch = clone(value); branch.action['later_action'] = action['later_action']
                    state, result = _advance(branch, self.__step, self.__finish)
            self.__results[key] = copy.deepcopy(result)
            return copy.deepcopy(result)
        except _ERRORS:
            return guards.malformed()

    def describe(self):
        return {'version': VERSION, 'phase': 'initial', 'candidate_count': len(self.__actions),
                'root_prefixes': len(self.__roots), 'return_prefixes': len(self.__returns),
                'completed_candidate_results': len(self.__results), 'quiet_tail_changed': False,
                'cross_request_cache': False, 'native_protection_certified': False,
                'online_information_delivered': False, 'complete_100ms_certified': False}


class LaterPrefixContext:
    """Four later choices retain typed guards and immutable completed prefix."""
    def __init__(self, bundle):
        _check_sources()
        guards.compile_guards()  # pin inherited original/legacy implementations
        guards._closed_tree(bundle); snapshot = copy.deepcopy(bundle)
        self.__failure = None; self.__roots = {}; self.__results = {}
        try: checked = later.revalidate(snapshot)
        except _ERRORS:
            checked = {'status': 'unknown_malformed_later_input', 'completion': {},
                       'native_protection_certified': False, 'online_information_delivered': False}
            self.__failure = checked; return
        if checked['status'] != 'conditional_model_input':
            self.__failure = {'status': 'unknown_missing_later_input', 'completion': {},
                'reasons': checked.get('reasons', []), 'native_protection_certified': False,
                'online_information_delivered': False}; return
        self.__snapshot = checked; self.__phase = checked['phase']
        self.__class = _private_class(checked, is_later=True)
        self.__seed, self.__step, self.__finish = _run_parts(later.LaterProjection)

    def actions(self): return copy.deepcopy(list(later.ACTIONS))

    def predict(self, action):
        try:
            # Same typed action guard executes before any supplied-input failure.
            if (set(action) != {'return_delay', 'later_action'} or type(action['return_delay']) not in (int, float)
                    or action not in later.ACTIONS):
                return {'status': 'unknown_unsupported_action', 'completion': {}, 'native_protection_certified': False}
            guards._closed_tree(action); action = copy.deepcopy(action)
            if self.__failure is not None: return copy.deepcopy(self.__failure)
            # At first_reuse_route the completed first return is immutable,
            # returns=1 and reuse1 is already in choice_jobs. No later event
            # consumes return_delay; the second return remains direct delay0.
            delay = action['return_delay'] if self.__phase == 'first_return' else 0.
            key = delay, action['later_action']
            if key not in self.__results:
                if self.__phase == 'first_return':
                    if delay not in self.__roots:
                        root = self.__class(self.__snapshot, {'return_delay': delay, 'later_action': 'native_default'})
                        _freeze_static(root); self.__seed(root)
                        self.__roots[delay] = _advance(root, self.__step, self.__finish, 'later_decision')
                    state, value = self.__roots[delay]
                    if state == 'terminal': result = value
                    else:
                        branch = clone(value); branch.action['later_action'] = action['later_action']
                        _, result = _advance(branch, self.__step, self.__finish)
                else:
                    root = self.__class(self.__snapshot, {'return_delay': 0., 'later_action': action['later_action']})
                    _freeze_static(root); self.__seed(root)
                    _, result = _advance(root, self.__step, self.__finish)
                self.__results[key] = copy.deepcopy(result)
            return copy.deepcopy(self.__results[key])
        except _ERRORS:
            return {'status': 'unknown_malformed_later_input', 'completion': {}, 'native_protection_certified': False,
                    'online_information_delivered': False}

    def describe(self):
        return {'version': VERSION, 'phase': getattr(self, '_LaterPrefixContext__phase', 'unknown'),
                'candidate_count': 4, 'completed_unique_results': len(self.__results),
                'quiet_tail_changed': False, 'cross_request_cache': False,
                'native_protection_certified': False, 'online_information_delivered': False,
                'complete_100ms_certified': False}
