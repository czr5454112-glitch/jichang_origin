"""Independent lazy-view candidate; frozen communication model stays unchanged.

Only the two trigger-tray reads in owner activation construct a full view.
Collection/capture events and every guard remain the original implementations.
No batch/quiet-tail/event deletion, candidate reduction or numeric change.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import inspect
from pathlib import Path
import textwrap
from types import FunctionType
from . import public_live_obligation_communication_projection as original

EXPECTED='0c77f130e31f2727d0f6b7f6e6425ae073e3bf5b97515843cf1d03cced5c56ea'
CAPTURES='9d097e800eb138daa75032e07abd01537925f7d61fa02a601b57be764ba0c306'
VERSION='g31.live_obligation.lazy_communication_projection.v1'


def require(ok,why):
    if not ok:raise ValueError('lazy_communication:'+why)


def make_activate():
    require(hashlib.sha256(Path(original.__file__).read_bytes()).hexdigest()==EXPECTED,'frozen_original_source')
    require(hashlib.sha256(Path(original.captures.__file__).read_bytes()).hexdigest()==CAPTURES,'readonly_view_source')
    function=original.Projection.activate
    tree=ast.parse(textwrap.dedent(inspect.getsource(function)))
    before=copy.deepcopy(tree);body=tree.body[0].body
    positions=[i for i,node in enumerate(body) if isinstance(node,ast.Assign) and len(node.targets)==1
        and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='view']
    require(len(positions)==1,'single_view_assignment')
    position=positions[0];assignment=body.pop(position)
    require(ast.unparse(assignment.value)=='self.world.view(owner)','exact_readonly_expression')
    loads=[n for n in ast.walk(tree) if isinstance(n,ast.Name) and n.id=='view']
    require(len(loads)==2 and all(isinstance(n.ctx,ast.Load) for n in loads),'two_view_reads_only')
    # Both reads are exactly next(... view['trays'] ... tray_id=='L') passed
    # directly to begin_collection. No whole view is retained or certified.
    consumers=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
        and n.func.attr=='begin_collection']
    expected="next((x for x in view['trays'] if x['tray_id'] == 'L'))"
    require(len(consumers)==2 and all(len(n.args)==3 and ast.unparse(n.args[2])==expected for n in consumers),
        'exact_trigger_consumers')
    class Lazy(ast.NodeTransformer):
        def visit_Name(self,node):
            if node.id=='view':return ast.copy_location(copy.deepcopy(assignment.value),node)
            return node
    changed=Lazy().visit(tree)
    class Reverse(ast.NodeTransformer):
        def visit_Call(self,node):
            if ast.dump(node,include_attributes=False)==ast.dump(assignment.value,include_attributes=False):
                return ast.copy_location(ast.Name(id='view',ctx=ast.Load()),node)
            return self.generic_visit(node)
    reversed_tree=Reverse().visit(copy.deepcopy(changed));reversed_tree.body[0].body.insert(position,assignment)
    require(ast.dump(reversed_tree,include_attributes=False)==ast.dump(before,include_attributes=False),'inverse_AST_exact')
    ast.fix_missing_locations(changed);namespace=dict(function.__globals__)
    exec(compile(changed,'<conditional_lazy_owner_view>','exec'),namespace)
    proof={'source_sha256':EXPECTED,'capture_source_sha256':CAPTURES,'view_read_count':2,
        'removed_eager_assignments':1,'inverse_AST_exact':True,
        'same_capture_collect_guard_implementations':True,'new_numeric_expressions':0,
        'scope':'Only L trigger row is consumed. B E-recovery may create a request before deferred read, but changes no L field and no physical event runs inside activation.'}
    return namespace['activate'],proof


_activate,PROOF=make_activate()


class Projection(original.Projection):
    activate=_activate


# Preserve every input check, exception path, physical model and output. The
# private function's one globals replacement selects only the new subclass.
predict=FunctionType(original.predict.__code__,{**original.predict.__globals__,'Projection':Projection},
    original.predict.__name__,original.predict.__defaults__,original.predict.__closure__)
predict.__kwdefaults__=original.predict.__kwdefaults__
require(predict.__code__ is original.predict.__code__,'same_prediction_entry_code')


def source_proof():return copy.deepcopy(PROOF)
