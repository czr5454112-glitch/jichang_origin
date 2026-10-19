"""Only AST/source inspection; no native or controller import."""
import ast
import hashlib
import json
from pathlib import Path


class RemoveAddedAuditScopes(ast.NodeTransformer):
    def visit_With(self, node):
        node = self.generic_visit(node)
        if (len(node.items) == 1 and isinstance(node.items[0].context_expr, ast.Call)
                and isinstance(node.items[0].context_expr.func, ast.Attribute)
                and node.items[0].context_expr.func.attr == 'owner_scope'):
            return node.body
        return node

    def visit_Expr(self, node):
        call = node.value
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name) and call.func.value.id == 'progress'
                and call.func.attr == 'update' and {key.arg for key in call.keywords}
                == {'path_timing', 'static_registry_initialization'}):
            return None
        return self.generic_visit(node)


def check(root):
    run = root/'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/R1_guarded_001'
    plan = json.loads((run/'plan.json').read_text())
    source = next(key for key in plan['source_archive'] if key.endswith('foundation_repeated_native.py'))
    old_path, new_path = run/plan['source_archive'][source], root/source
    old, new = ast.parse(old_path.read_text()), ast.parse(new_path.read_text())
    before = next(node for node in old.body if isinstance(node, ast.FunctionDef) and node.name == 'run_branch')
    after = next(node for node in new.body if isinstance(node, ast.FunctionDef) and node.name == 'run_branch')
    assert ast.dump(before) == ast.dump(RemoveAddedAuditScopes().visit(after))
    before = next(node for node in old.body if isinstance(node, ast.ClassDef) and node.name == 'OwnerPolicy')
    after = next(node for node in new.body if isinstance(node, ast.ClassDef) and node.name == 'OwnerPolicy')
    unchanged = []
    for method in before.body:
        if isinstance(method, ast.FunctionDef) and method.name != 'activate':
            current = next(node for node in after.body if isinstance(node, ast.FunctionDef) and node.name == method.name)
            assert ast.dump(method) == ast.dump(current), method.name
            unchanged.append(method.name)
    return {'status': 'passed', 'old_source_sha256': hashlib.sha256(old_path.read_bytes()).hexdigest(),
        'new_source_sha256': hashlib.sha256(new_path.read_bytes()).hexdigest(),
        'run_branch_equal_after_removing_only_new_audit_scopes_and_scalar_progress_retention': True,
        'unchanged_owner_policy_method_bodies': unchanged, 'native_started': False}


if __name__ == '__main__':
    print(json.dumps(check(Path(__file__).resolve().parents[5]), indent=2))
