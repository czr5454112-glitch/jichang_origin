"""Versioned owned120 source/functional gate, no native or performance run."""
import time
BOOT=time.monotonic()
from . import run_initial_owner_route_gate_pure_v2 as old
from . import initial_owner_route_entry_integration as integration

TESTS=(*old.TESTS,'tests/test_g31_circulation_initial_owner_route_entry_hop.py',
    'tests/test_g31_circulation_initial_owner_route_entry_integration.py',
    'tests/test_g31_circulation_initial_owner_route_entry_campaign.py')


def modules():
    return old.modules()+tuple(__package__+'.'+name for name in (
        'run_initial_owner_route_entry_pure','prepare_initial_owner_route_entry_campaign',
        'launch_initial_owner_route_entry_campaign','initial_owner_route_entry_campaign',
        'verify_initial_owner_route_entry_campaign'))+tuple(path[:-3].replace('/','.') for path in TESTS[-3:])


def main():
    # Keep the complete old parent/worker lifecycle; substitute the child target
    # once through a private argv wrapper because the old target is a literal.
    import ast,copy
    gate=integration.previous.gate;syntax=gate.tree(old.main);original=copy.deepcopy(syntax);count=0
    for node in ast.walk(syntax):
        if isinstance(node,ast.Constant) and node.value=='.run_initial_owner_route_gate_pure_v2':
            node.value='.run_initial_owner_route_entry_pure';count+=1
    if count!=1:raise ValueError('entry_pure_child_target_count')
    restored=copy.deepcopy(syntax)
    for node in ast.walk(restored):
        if isinstance(node,ast.Constant) and node.value=='.run_initial_owner_route_entry_pure':
            node.value='.run_initial_owner_route_gate_pure_v2'
    if gate.dump(restored)!=gate.dump(original):raise ValueError('entry_pure_parent_AST_changed')
    namespace={**vars(old),**globals()}
    exec(compile(ast.fix_missing_locations(syntax),'<entry-pure-lifecycle>','exec'),namespace)
    return namespace['main']()


if __name__=='__main__':raise SystemExit(main())
