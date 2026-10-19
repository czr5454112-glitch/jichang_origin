"""Opt-in, one-request initial projection context; no native authority.

The original input guards execute once on an isolated supplied-data snapshot.
Every action retains the original typed vocabulary guard and every simulation
retains the original dynamic constructor and event loop. Only the public
service potential is shared, read-only, inside this single context.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import math
from pathlib import Path
import pickle
from types import FunctionType, MappingProxyType

from . import public_native_preference_projection as original

VERSION = 'public_preference_single_request_context_v1'
EXPECTED_SOURCE = 'f501e125feb6ddb4fc343f55ddf684781741d13b71d6fa9178b485ff8ce3b4b7'
EXPECTED_LEGACY = 'bb1bf8bc35822b671e9db5844e136ff91f187c4d92d465190f5d630f7cb739d1'
_OK = object()
_ERRORS = (TypeError, ValueError, KeyError, OverflowError, AttributeError)


def malformed():
    return {'status': 'unknown_malformed_or_unsupported_projection_input', 'completion': {},
            'native_protection_certified': False, 'online_information_delivered': False}


def _closed_tree(value, active=None):
    """No custom reducers/deepcopy hooks. This experiment accepts supplied data."""
    if type(value) in (str, int, float, bool, type(None)):
        return
    if type(value) not in (dict, list, tuple):
        raise TypeError('request_context:non_builtin_supplied_data')
    active = set() if active is None else active
    if id(value) in active:
        raise ValueError('request_context:cyclic_supplied_data')
    active.add(id(value))
    if type(value) is dict:
        for key, item in value.items():
            if type(key) not in (str, int, float, bool, type(None)):
                raise TypeError('request_context:non_builtin_key')
            _closed_tree(item, active)
    else:
        for item in value:
            _closed_tree(item, active)
    active.remove(id(value))


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) in (tuple, list):
        return tuple(_freeze(item) for item in value)
    if type(value) in (str, int, float, bool, type(None)):
        return value
    raise TypeError('request_context:unsupported_potential_container')


def compile_guards():
    """Preserve the exact source AST; split only at the action-dependent tail."""
    for module, expected in ((original, EXPECTED_SOURCE), (original.legacy, EXPECTED_LEGACY)):
        if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() != expected:
            raise ValueError('request_context:unreviewed_source_revision')
    tree = ast.parse(inspect.getsource(original._predict))
    source = tree.body[0]
    if (not isinstance(source, ast.FunctionDef) or source.name != '_predict'
            or ast.unparse(source.body[-3]) != "windows = contract.domain.domain(case)['public_derivation']['supply_windows']"
            or not isinstance(source.body[-2], ast.If)
            or ast.unparse(source.body[-1]) != 'return Projection(bundle, action).run()'):
        raise ValueError('request_context:guard_tail_changed')
    validation = copy.deepcopy(source)
    validation.name = '_validate_supplied_snapshot'
    validation.args.args = validation.args.args[:1]
    validation.body = copy.deepcopy(source.body[:-2]) + [ast.Return(value=ast.Tuple(elts=[
        ast.Name(id='_GUARD_OK', ctx=ast.Load()), ast.Name(id='windows', ctx=ast.Load()),
        ast.Name(id='numeric', ctx=ast.Load())], ctx=ast.Load()))]
    if ast.dump(ast.Module(body=validation.body[:-1], type_ignores=[]), include_attributes=False) != ast.dump(
            ast.Module(body=source.body[:-2], type_ignores=[]), include_attributes=False):
        raise ValueError('request_context:input_guard_changed')

    old_action = copy.deepcopy(source.body[-2])
    class ReplaceDomain(ast.NodeTransformer):
        count = 0
        def visit_Subscript(self, node):
            if ast.unparse(node) == "vocabulary.domain(windows)['actions']":
                self.count += 1
                return ast.copy_location(ast.Name(id='_declared_actions', ctx=ast.Load()), node)
            return self.generic_visit(node)
    replacement = ReplaceDomain()
    action_guard = replacement.visit(copy.deepcopy(old_action))
    if replacement.count != 1:
        raise ValueError('request_context:action_domain_changed')
    class RestoreDomain(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id == '_declared_actions':
                return ast.parse("vocabulary.domain(windows)['actions']", mode='eval').body
            return node
    if ast.dump(RestoreDomain().visit(copy.deepcopy(action_guard)), include_attributes=False) != ast.dump(old_action, include_attributes=False):
        raise ValueError('request_context:typed_action_guard_changed')
    action = ast.parse('def _validate_action(action, _declared_actions, numeric):\n    pass').body[0]
    action.body = [action_guard, ast.Return(value=ast.Name(id='_GUARD_OK', ctx=ast.Load()))]
    generated = ast.fix_missing_locations(ast.Module(body=[validation, action], type_ignores=[]))
    namespace = {**original._predict.__globals__, '_GUARD_OK': _OK}
    exec(compile(generated, __file__ + ':exact_guard_split', 'exec'), namespace)
    proof = {'status': 'exact_input_guard_AST_and_typed_action_guard',
             'projection_source_sha256': EXPECTED_SOURCE, 'legacy_source_sha256': EXPECTED_LEGACY,
             'action_change': 'The same vocabulary.domain(windows) actions are constructed once per request.',
             'constructor': 'Original code/closure in private FunctionType; only service_aware_potential global is replaced.',
             'event_loop': 'Original Projection.run and all inherited methods, unchanged.'}
    return namespace['_validate_supplied_snapshot'], namespace['_validate_action'], proof


class RequestContext:
    """Read-only public interface to an isolated, single-request snapshot.

    This is supplied-data validation, not an online token or native certificate.
    New observations require a new context. Results, actions and snapshot copies
    can be changed by callers without affecting subsequent candidate simulations.
    """
    __slots__ = ('__evaluate', '__snapshot', '__actions', '__fingerprint', '__proof')

    def __init__(self, bundle):
        validate, action_check, proof = compile_guards()
        _closed_tree(bundle)
        snapshot = copy.deepcopy(bundle)
        fingerprint = hashlib.sha256(pickle.dumps(snapshot, protocol=5)).hexdigest()
        try:
            checked = validate(snapshot)
        except _ERRORS:
            checked = malformed()
        if not (type(checked) is tuple and len(checked) == 3 and checked[0] is _OK):
            failure = copy.deepcopy(checked)
            evaluate = lambda action: copy.deepcopy(failure)
            actions = []
        else:
            _, windows, numeric = checked
            actions = original.vocabulary.domain(windows)['actions']
            # Same function, arguments and arithmetic order as original init.
            potential = _freeze(original.service_aware_potential(
                snapshot['contract']['node_records'], snapshot['contract']['edge_records'],
                minimum_service_seconds=.001))
            def shared_potential(nodes, edges, *, minimum_service_seconds):
                if (nodes is not snapshot['contract']['node_records']
                        or edges is not snapshot['contract']['edge_records']
                        or type(minimum_service_seconds) is not float or minimum_service_seconds != .001):
                    raise ValueError('request_context:unexpected_potential_arguments')
                return potential
            init = original.Projection.__init__
            private_init = FunctionType(init.__code__, {**init.__globals__,
                'service_aware_potential': shared_potential}, init.__name__, init.__defaults__, init.__closure__)
            private_init.__kwdefaults__ = copy.deepcopy(init.__kwdefaults__)
            private_projection = type('_SingleRequestProjection', (original.Projection,), {'__init__': private_init})
            def evaluate(action):
                try:
                    verdict = action_check(action, actions, numeric)
                    if verdict is not _OK:
                        return verdict
                    _closed_tree(action)
                    action = copy.deepcopy(action)
                    # Legacy constructor still copies the entire snapshot,
                    # jobs, trays and each dynamic calendar for every action.
                    return private_projection(snapshot, action).run()
                except _ERRORS:
                    return malformed()
        self.__evaluate = evaluate
        self.__snapshot = lambda: copy.deepcopy(snapshot)
        self.__actions = lambda: copy.deepcopy(actions)
        self.__fingerprint = fingerprint
        self.__proof = proof

    def predict(self, action):
        return self.__evaluate(action)

    def snapshot(self):
        return self.__snapshot()

    def actions(self):
        return self.__actions()

    def describe(self):
        return {'version': VERSION, 'supplied_snapshot_sha256': self.__fingerprint,
                'source_proof': copy.deepcopy(self.__proof), 'candidate_count': len(self.__actions()),
                'cross_request_cache': False, 'native_protection_certified': False,
                'online_information_delivered': False, 'complete_100ms_certified': False}
