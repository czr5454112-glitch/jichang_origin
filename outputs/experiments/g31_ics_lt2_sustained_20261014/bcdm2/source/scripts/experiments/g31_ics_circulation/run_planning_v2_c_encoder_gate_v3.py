"""Only parent log names change; command logs/readers keep original names.

The first build failed before the encoder target compiler started. This version
uses fresh build/output names and preserves its predecessors and all 120s gates.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import inspect
from pathlib import Path
from . import run_planning_v2_c_encoder_gate_v2 as previous

TEST='tests/test_g31_circulation_planning_v2_c_encoder_parent_logs.py'
PURE='scripts/experiments/g31_ics_circulation/run_planning_v2_c_encoder_parent_logs_pure.py'
old=previous.old


def parent_main_tree():
    reference=ast.parse(inspect.getsource(old.main))
    tree=copy.deepcopy(reference);changes=[]
    class Replace(ast.NodeTransformer):
        def visit_BinOp(self,node):
            if (isinstance(node.op,ast.Add) and isinstance(node.left,ast.Attribute) and
                isinstance(node.left.value,ast.Name) and node.left.value.id=='args' and node.left.attr=='mode' and
                isinstance(node.right,ast.Constant) and node.right.value in ('.stdout.log','.stderr.log')):
                changes.append(node.right.value)
                return ast.copy_location(ast.BinOp(left=ast.BinOp(left=ast.Constant('parent_'),
                    op=ast.Add(),right=copy.deepcopy(node.left)),op=ast.Add(),right=copy.deepcopy(node.right)),node)
            return self.generic_visit(node)
    tree=Replace().visit(tree)
    old.require(changes==['.stdout.log','.stderr.log'],'exact_parent_log_changes')
    class Restore(ast.NodeTransformer):
        def visit_BinOp(self,node):
            if (isinstance(node.op,ast.Add) and isinstance(node.left,ast.BinOp) and
                isinstance(node.left.op,ast.Add) and isinstance(node.left.left,ast.Constant) and
                node.left.left.value=='parent_' and isinstance(node.right,ast.Constant) and
                node.right.value in ('.stdout.log','.stderr.log')):
                return ast.copy_location(ast.BinOp(left=copy.deepcopy(node.left.right),op=ast.Add(),
                    right=copy.deepcopy(node.right)),node)
            return self.generic_visit(node)
    restored=Restore().visit(copy.deepcopy(tree))
    old.require(ast.dump(restored,include_attributes=False)==ast.dump(reference,include_attributes=False),'parent_main_inverse_AST')
    return ast.fix_missing_locations(tree),{'parent_log_prefix':'parent_',
        'exact_replacements':changes,'inverse_AST_equals_frozen_main':True,
        'all_other_main_statements_preserved':True,
        'AST_sha256':hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest()}


def namespace():
    ns=previous.namespace()
    ns['__file__']=__file__;ns['MODULE']=__package__+'.run_planning_v2_c_encoder_gate_v3'
    ns['BUILD']=old.ROOT/'build_planning_v2_typed_encoder_002'
    tree,proof=parent_main_tree()
    exec(compile(tree,'<g31_typed_encoder_parent_logs_v3>','exec'),ns)
    original_commands=ns['commands']
    def commands(plan_path,plan_sha,build_output,functional_output):
        # Frozen prepare's two output-name literals are translated only at the
        # command-construction boundary. Actual worker log names stay untouched.
        if Path(build_output)==old.OUT/'planning_v2_C_encoder_build_001':
            build_output=old.OUT/'planning_v2_C_encoder_build_002'
        if Path(functional_output)==old.OUT/'planning_v2_C_encoder_functional_001':
            functional_output=old.OUT/'planning_v2_C_encoder_functional_002'
        return original_commands(plan_path,plan_sha,build_output,functional_output)
    ns['commands']=commands
    original_closure=ns['project_closure']
    def project_closure():
        result=original_closure()
        for name in (TEST,PURE):result[name]=old.sha(old.ROOT/name)
        return dict(sorted(result.items()))
    ns['project_closure']=project_closure
    original_prepare=ns['prepare']
    def prepare(output,report):
        report['parent_log_repair']=proof
        report['fresh_execution_names']={'build_directory':str(ns['BUILD']),
            'build_output':str(old.OUT/'planning_v2_C_encoder_build_002'),
            'functional_output':str(old.OUT/'planning_v2_C_encoder_functional_002')}
        original_prepare(output,report)
    ns['prepare']=prepare
    return ns


def main():return namespace()['main']()


if __name__=='__main__':raise SystemExit(main())
