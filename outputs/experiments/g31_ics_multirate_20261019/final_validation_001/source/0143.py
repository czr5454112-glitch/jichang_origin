"""The accepted synchronous RPC client with only the new fixed entry path."""
from __future__ import annotations
import ast
import copy
import inspect
import textwrap
from . import json_prediction_client as original

OLD_ENTRY = 'scripts/experiments/g31_ics_circulation/json_prediction_worker.py'
NEW_ENTRY = 'scripts/experiments/g31_ics_circulation/initial_owner_route_worker.py'


def constructor():
    tree = ast.parse(textwrap.dedent(inspect.getsource(original.Client.__init__)))
    before = ast.dump(tree, include_attributes=False)
    matches = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == OLD_ENTRY]
    if len(matches) != 1:
        raise ValueError('unreviewed_client_entry_AST')
    matches[0].value = NEW_ENTRY
    restored = copy.deepcopy(tree)
    for node in ast.walk(restored):
        if isinstance(node, ast.Constant) and node.value == NEW_ENTRY:
            node.value = OLD_ENTRY
    if ast.dump(restored, include_attributes=False) != before:
        raise ValueError('client_constructor_changed')
    namespace = dict(original.Client.__init__.__globals__)
    exec(compile(ast.fix_missing_locations(tree), __file__+':entry_only', 'exec'), namespace)
    return namespace['__init__']


class InitialOwnerClient(original.Client):
    __init__ = constructor()
