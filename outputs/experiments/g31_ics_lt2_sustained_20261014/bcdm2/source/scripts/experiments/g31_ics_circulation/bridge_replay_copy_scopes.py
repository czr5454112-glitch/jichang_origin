"""Two private, source-bound copy omissions for a future saved-only replay.

No generic client/selector is replaced. The two refresh callers discard their
return. The direct BridgeOwner selector is borrowed only through read-only
consumers; PossessionGate's escaping proof still uses the original selector.
No campaign, native session, file readback or benchmark is dispatched here.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import inspect
import textwrap
from types import FunctionType, SimpleNamespace
from . import cooperative_bridge_policy as policy
from . import research_original_low_wip as base
from . import research_original_low_wip_reuse as reuse
from . import protocol_control as protocol
from . import current_empty_possession_permit as possession


def require(ok, reason):
    if not ok:
        raise ValueError('bridge_copy_scopes:' + reason)


def private(function, namespace):
    value = FunctionType(function.__code__, namespace, function.__name__,
                         function.__defaults__, function.__closure__)
    value.__kwdefaults__ = function.__kwdefaults__
    return value


def _dump(value):
    return ast.dump(value, include_attributes=False)


def expression_variant(function, old_expression, new_expression, namespace):
    """Exactly one expression changes; the inverse reconstructs the whole AST."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    before = _dump(tree)
    old = ast.parse(old_expression, mode='eval').body
    new = ast.parse(new_expression, mode='eval').body
    count = 0

    class Replace(ast.NodeTransformer):
        def generic_visit(self, node):
            nonlocal count
            if _dump(node) == _dump(old):
                count += 1
                return ast.copy_location(copy.deepcopy(new), node)
            return super().generic_visit(node)

    tree = Replace().visit(tree)
    require(count == 1, 'expression_count')
    reverse_count = 0

    class Reverse(ast.NodeTransformer):
        def generic_visit(self, node):
            nonlocal reverse_count
            if _dump(node) == _dump(new):
                reverse_count += 1
                return ast.copy_location(copy.deepcopy(old), node)
            return super().generic_visit(node)

    restored = Reverse().visit(copy.deepcopy(tree))
    require(reverse_count == 1 and _dump(restored) == before, 'inverse_AST')
    # Compilation inside an enclosing function recreates the original lexical
    # __class__ free variable. Its actual original cell is supplied below.
    fn = tree.body[0]
    if function.__closure__:
        require(function.__code__.co_freevars == ('__class__',), 'unsupported_closure')
        outer = ast.FunctionDef(name='_factory', args=ast.arguments(posonlyargs=[],
            args=[], kwonlyargs=[], kw_defaults=[], defaults=[]), body=[
            ast.Assign(targets=[ast.Name(id='__class__', ctx=ast.Store())], value=ast.Constant(None)),
            fn, ast.Return(value=ast.Name(id=fn.name, ctx=ast.Load()))], decorator_list=[])
        compiled_tree = ast.Module(body=[outer], type_ignores=[])
    else:
        compiled_tree = tree
    scope = dict(namespace)
    exec(compile(ast.fix_missing_locations(compiled_tree), inspect.getsourcefile(function), 'exec'), scope)
    compiled = scope['_factory']() if function.__closure__ else scope[function.__name__]
    require(compiled.__code__.co_freevars == function.__code__.co_freevars, 'freevars_changed')
    result = FunctionType(compiled.__code__, scope, function.__name__,
                          function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result, {'function': function.__module__ + '.' + function.__qualname__,
        'old_expression': old_expression, 'new_expression': new_expression,
        'inverse_AST_exact': True, 'original_AST_sha256': hashlib.sha256(before.encode()).hexdigest(),
        'original_freevars': list(function.__code__.co_freevars),
        'original_closure_cells_preserved': result.__closure__ == function.__closure__}


_REFRESH = protocol.ProtocolClient.refresh
_OWN = reuse.latest_own_capture
_BASE_ACTIVATE = base.Owner.activate
_BRIDGE_ACTIVATE = policy.BridgeOwner.activate
_RUN = policy.run_policy
_CONSUMERS = (policy.received_barrier, policy.choose_action,
    policy.current_own_fifo_heads, policy.fifo_heads, policy.completion_permit,
    base.public_graph, base.paths_from, possession.PossessionGate.consume)
_IDENTITIES = tuple((f, f.__code__) for f in
    (_REFRESH, _OWN, _BASE_ACTIVATE, _BRIDGE_ACTIVATE, _RUN, *_CONSUMERS))

# A unique private no-op expression makes the inverse unambiguous. The
# discarded list construction is omitted; all earlier state/ACK/retry work stays.
def _discard_unused_views():
    return None


_REFRESH_DISCARD, _REFRESH_PROOF = expression_variant(_REFRESH,
    'views.append({"request_id": request_id, "kind": row["kind"], "view": copy.deepcopy(view)})',
    '_discard_unused_views()',
    {**_REFRESH.__globals__, '_discard_unused_views': _discard_unused_views})


def _refresh_discarded(client, *, owner_id):
    require(type(client) is protocol.ProtocolClient, 'nonexact_client')
    # Deliberately no returned list: this private helper has exactly two
    # source-proven expression-statement callers. It is not a refresh API.
    _REFRESH_DISCARD(client, owner_id=owner_id)


_BORROWED_OWN, _BORROW_PROOF = expression_variant(_OWN,
    '{"request_id": request_id, "ack": deepcopy(ack), "envelope": deepcopy(valid)}',
    '{"request_id": request_id, "ack": ack, "envelope": valid}', dict(_OWN.__globals__))
_PRIVATE_REUSE = SimpleNamespace(**{**vars(reuse), 'latest_own_capture': _BORROWED_OWN})
_CALL = 'self.client.refresh(owner_id=self.owner)'
_DISCARD_CALL = '_refresh_discarded(self.client, owner_id=self.owner)'
_BASE_VARIANT, _BASE_PROOF = expression_variant(_BASE_ACTIVATE, _CALL, _DISCARD_CALL,
    {**_BASE_ACTIVATE.__globals__, '_refresh_discarded': _refresh_discarded})
_BRIDGE_VARIANT, _BRIDGE_PROOF = expression_variant(_BRIDGE_ACTIVATE, _CALL, _DISCARD_CALL,
    {**_BRIDGE_ACTIVATE.__globals__, '_refresh_discarded': _refresh_discarded, 'reuse': _PRIVATE_REUSE})


class _DiscardBaseOwner(base.Owner):
    activate = _BASE_VARIANT


class CopyScopedBridgeOwner(policy.BridgeOwner, _DiscardBaseOwner):
    """Closed replay type; original super() visits the private base activate."""
    activate = _BRIDGE_VARIANT


run_policy = private(_RUN, {**_RUN.__globals__, 'BridgeOwner': CopyScopedBridgeOwner})
_PRIVATE_IDENTITIES = tuple((f, f.__code__) for f in
    (_REFRESH_DISCARD, _BORROWED_OWN, _BASE_VARIANT, _BRIDGE_VARIANT, run_policy))


def source_proof():
    require(all(f.__code__ is code for f, code in _IDENTITIES), 'function_code_drift')
    require(all(f.__code__ is code for f, code in _PRIVATE_IDENTITIES), 'private_code_drift')
    require(protocol.ProtocolClient.refresh is _REFRESH and reuse.latest_own_capture is _OWN
        and base.Owner.activate is _BASE_ACTIVATE and policy.BridgeOwner.activate is _BRIDGE_ACTIVATE
        and policy.run_policy is _RUN, 'defining_identity_drift')
    for function in _CONSUMERS:
        module = inspect.getmodule(function)
        current = module
        for part in function.__qualname__.split('.'):
            current = getattr(current, part)
        require(current is function, 'readonly_consumer_drift')
    require(CopyScopedBridgeOwner.__mro__[1:4] ==
        (policy.BridgeOwner, _DiscardBaseOwner, base.Owner), 'super_MRO')
    require(CopyScopedBridgeOwner.activate.__closure__ == _BRIDGE_ACTIVATE.__closure__
        and super(policy.BridgeOwner, CopyScopedBridgeOwner.__new__(CopyScopedBridgeOwner)).activate.__func__
            is _BASE_VARIANT, 'super_target')
    require(_BRIDGE_VARIANT.__globals__['reuse'] is _PRIVATE_REUSE
        and _PRIVATE_REUSE.latest_own_capture is _BORROWED_OWN
        and possession.PossessionGate.consume.__globals__['reuse'] is reuse
        and reuse.latest_own_capture is _OWN, 'escaping_possession_selector_changed')
    require(run_policy.__code__ is _RUN.__code__ and
        run_policy.__globals__['BridgeOwner'] is CopyScopedBridgeOwner, 'policy_loop_changed')
    require(CopyScopedBridgeOwner.activate is _BRIDGE_VARIANT
        and _DiscardBaseOwner.activate is _BASE_VARIANT
        and all(f.__globals__['_refresh_discarded'] is _refresh_discarded
                for f in (_BASE_VARIANT, _BRIDGE_VARIANT)), 'private_binding_drift')
    return {'schema': 'g31.bridge.private_copy_scopes.v1',
        'expression_proofs': [_REFRESH_PROOF, _BORROW_PROOF, _BASE_PROOF, _BRIDGE_PROOF],
        'consumer_source_sha256': {f.__module__+'.'+f.__qualname__:
            hashlib.sha256(inspect.getsource(f).encode()).hexdigest() for f in _CONSUMERS},
        'refresh_sites': ['base.Owner.activate discarded expression', 'BridgeOwner.activate halt discarded expression'],
        'retained_client_view_deepcopy': True, 'all_original_guard_invocations_retained': True,
        'possession_gate_original_copies_retained': True,
        'borrow_lifetime': 'Direct activation local only; consumers return fresh barrier/path or copied job/completion. No durable escape.',
        'exception_scope': 'Builtin saved domain only. Omitted allocations may avoid MemoryError; identical resource-failure timing is not claimed. Remaining failure is unknown.',
        'not_generic_refresh_or_selector_API': True, 'global_monkeypatch': False,
        'full_saved_audit_installed': False, 'native_dispatched': False,
        'performance_measured': False}
