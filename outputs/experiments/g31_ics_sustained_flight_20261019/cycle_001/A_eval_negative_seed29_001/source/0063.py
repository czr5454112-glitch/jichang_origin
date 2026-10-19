"""Owner-local retained initial estimate, with the full historical policy.

This is not rolling model optimization. Each constructor receives only that
owner's already selected initial vector. The caller must bind its actual origin;
this class neither authenticates an arbitrary vector nor reads a peer proposal.
All actual endpoint, history, union, current-state, wire, one-recollection and
reply-budget guards remain the historical implementation. Only three metadata
expressions change, proved by inverse AST restoration below.

The executed flag uses the old local ``executed`` expression. It includes an
admitted no-command native default; it is not an ACK, edge or physical success
certificate. A fallback or rejected local action cannot set it true. Added
construction/proof costs remain ordinary charged work, never subtracted.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import textwrap
from pathlib import Path
from types import FunctionType

from . import live_obligation_historical_policy as historical

SCHEMA = 'g31.live_obligation.online_retained_initial_policy.v1'
OLD_VECTOR_KEY = 'predeclared_counterfactual_vector'
VECTOR_KEY = 'retained_initial_estimate_vector'
OLD_STATUS = 'predeclared_finite_counterfactual_action'
STATUS = 'retained_initial_estimate_no_later_model_reestimate'
EXECUTED_KEY = 'future_proposal_component_executed_without_replan'
_ORIGINAL_DECIDE = historical.old.OwnerPolicy.decide_pending
_ORIGINAL_CHOICE = historical.old.old.fixed_choice
_ORIGINAL_INIT = historical.OwnerPolicy.__init__
_IDENTITIES = tuple((function, function.__code__, function.__globals__,
    function.__defaults__, function.__kwdefaults__, function.__closure__)
    for function in (_ORIGINAL_INIT, _ORIGINAL_DECIDE, _ORIGINAL_CHOICE))
_SOURCES = {
    'live_obligation_historical_policy.py': '43af16c3f71b6babc3e672b6386628639f160657cc1235ecf5d809a338d2f1f8',
    'live_obligation_recollection_policy_v2.py': '174c4a5e70c2b49e9a6a48407baccd4de928ec80f1cd67b022e25e2c2bff53f1',
    'live_obligation_recollection_policy.py': 'f89864910a0147416feb2ccab5cc78d5f7a017f4ea7727a29e5e0661b0937f94',
    'live_obligation_historical_adapter.py': 'c16dcdccddfcd763a90d15cf4e321c35697ffcdcac16e03da69fa097ad04d1cc',
}


def require(value, reason):
    if not value:
        raise ValueError('online_retained_policy:' + reason)


def original_identity():
    require(historical.OwnerPolicy.__init__ is _ORIGINAL_INIT
        and historical.old.OwnerPolicy.decide_pending is _ORIGINAL_DECIDE
        and historical.old.old.fixed_choice is _ORIGINAL_CHOICE,
        'original_definition_identity')
    for function, code, namespace, defaults, kwdefaults, closure in _IDENTITIES:
        require(function.__code__ is code and function.__globals__ is namespace
            and function.__defaults__ is defaults and function.__kwdefaults__ is kwdefaults
            and function.__closure__ is closure, 'original_function_identity')


def _dump(tree):
    return ast.dump(tree, include_attributes=False)


def _tree(function, role):
    """Exactly one status, or one dict key and its existing executed value."""
    original = ast.parse(textwrap.dedent(inspect.getsource(function)))
    require(len(original.body) == 1 and isinstance(original.body[0], ast.FunctionDef)
        and original.body[0].name == role, 'single_original_function')
    tree = copy.deepcopy(original)
    changed = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for index, key in enumerate(node.keys):
            if not isinstance(key, ast.Constant):
                continue
            value = node.values[index]
            if role == 'fixed_choice' and key.value == 'status' and isinstance(value, ast.Constant) and value.value == OLD_STATUS:
                node.values[index] = ast.copy_location(ast.Constant(STATUS), value)
                changed.append(('status', node, index, value))
            elif role == 'decide_pending' and key.value == OLD_VECTOR_KEY:
                node.keys[index] = ast.copy_location(ast.Constant(VECTOR_KEY), key)
                changed.append(('key', node, index, key))
            elif role == 'decide_pending' and key.value == EXECUTED_KEY:
                require(isinstance(value, ast.Constant) and value.value is False,
                    'old_execution_metadata_is_false')
                node.values[index] = ast.copy_location(ast.Name(id='executed', ctx=ast.Load()), value)
                changed.append(('executed', node, index, value))
    require([row[0] for row in changed].count('status') == (role == 'fixed_choice')
        and [row[0] for row in changed].count('key') == (role == 'decide_pending')
        and [row[0] for row in changed].count('executed') == (role == 'decide_pending')
        and len(changed) == (1 if role == 'fixed_choice' else 2), 'exact_metadata_edit_count')
    modified = copy.deepcopy(tree)
    for kind, node, index, before in reversed(changed):
        if kind == 'key': node.keys[index] = before
        else: node.values[index] = before
    require(_dump(tree) == _dump(original), 'inverse_AST_restores_all_statements')
    return modified, {
        'role': role, 'metadata_edits': [row[0] for row in changed],
        'inverse_AST_exact': True,
        'original_AST_sha256': hashlib.sha256(_dump(original).encode()).hexdigest(),
        'retained_AST_sha256': hashlib.sha256(_dump(modified).encode()).hexdigest(),
    }


def _rewrite(function, role, *, fixed_choice=None):
    reference = _ORIGINAL_CHOICE if role == 'fixed_choice' else _ORIGINAL_DECIDE
    require(function.__code__ is reference.__code__
        and function.__defaults__ is reference.__defaults__
        and function.__kwdefaults__ is reference.__kwdefaults__
        and function.__closure__ is reference.__closure__, 'actual_historical_instance_function')
    tree, proof = _tree(function, role)
    namespace = dict(function.__globals__)
    if fixed_choice is not None:
        require(role == 'decide_pending', 'only_decision_fixed_choice_rebinding')
        namespace['fixed_choice'] = fixed_choice
    # Compile in a throwaway full namespace, then retain exactly the actual
    # function's globals except for that one per-instance fixed_choice slot.
    scratch = dict(namespace)
    exec(compile(ast.fix_missing_locations(tree), '<online_retained_metadata>', 'exec'), scratch)
    code = scratch[role].__code__
    require(code.co_freevars == function.__code__.co_freevars, 'preserved_freevars')
    result = FunctionType(code, namespace, function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    expected = {'fixed_choice'} if fixed_choice is not None else set()
    require(set(result.__globals__) == set(function.__globals__)
        and all(result.__globals__[key] is value for key, value in function.__globals__.items()
                if key not in expected), 'complete_defining_globals_preserved')
    return result, proof


def source_proof():
    """Small source/AST evidence; does not create owners, native or a model."""
    original_identity()
    directory = Path(historical.__file__).resolve().parent
    for name, digest in _SOURCES.items():
        require(hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest,
            'frozen_source:' + name)
    _, choice = _tree(_ORIGINAL_CHOICE, 'fixed_choice')
    _, decision = _tree(_ORIGINAL_DECIDE, 'decide_pending')
    return {'schema': SCHEMA, 'sources': dict(_SOURCES),
        'transforms': [choice, decision], 'historical_constructor_called_unchanged': True,
        'owner_adapter_kept': True, 'full_globals_defaults_kwdefaults_closure_kept': True,
        'guards_retries_recollection_reply_budget_changed': False,
        'peer_proposal_or_consensus_read': False, 'later_model_reestimation': False,
        'executed_flag_semantics': 'Exact existing local executed expression; no ACK or physical completion claim.',
        'native_or_protection_certification': False,
        'resource_failure_timing_equivalent': False}


class OwnerPolicy(historical.OwnerPolicy):
    def __init__(self, native, session, client, owner, ledger, channel,
                 selected_vector, accepted, supply=None):
        original_identity()
        # The unchanged historical constructor creates the owner-bound adapter
        # and private guarded functions first. Never rebuild them from the raw
        # recollection module, which would lose this actual owner's history.
        super().__init__(native, session, client, owner, ledger, channel,
                         selected_vector, accepted, supply)
        original = self.decide_pending.__func__
        original_fixed = original.__globals__['fixed_choice']
        adapter = original.__globals__['adapter']
        require(type(adapter) is historical.adapter.OwnerCollectionAdapter
            and adapter._client is client and adapter._session is session and adapter._owner == owner
            and original_fixed.__globals__['adapter'] is adapter,
            'same_actual_owner_collection_adapter')
        fixed, _ = _rewrite(original_fixed, 'fixed_choice')
        decision, _ = _rewrite(original, 'decide_pending', fixed_choice=fixed)
        self.decide_pending = decision.__get__(self, type(self))
