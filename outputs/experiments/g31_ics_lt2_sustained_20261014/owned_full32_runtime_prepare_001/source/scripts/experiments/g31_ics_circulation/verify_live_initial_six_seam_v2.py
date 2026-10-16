"""Saved six-owner guard replay; no authority is reconstructed from JSON."""
import ast
import copy
import hashlib
import inspect
import textwrap
from types import FunctionType
from . import research_live_initial_six_seam as previous


def _dump(tree):return ast.dump(tree,include_attributes=False)


def verify_owner_code():
    tree=ast.parse(textwrap.dedent(inspect.getsource(previous.verify_owner)))
    old=ast.parse("tray['mode']=='loaded' and tray['node']==0 and tray['business_bag_id']=='loaded' and tray['service_ready_known'] is True and type(tray['service_ready_at']) is float and math.isfinite(tray['service_ready_at']) and .11+.01<tray['service_ready_at'] and len(target)==1 and target[0]['occupancy']<target[0]['capacity']",mode='eval').body
    new=ast.parse("tray['mode']=='loaded' and tray['node']==0 and tray['business_bag_id']=='loaded' and origin.route_window_from_public(public)['derived_earliest_source_service_end']>.11+.01 and len(target)==1 and target[0]['occupancy']<target[0]['capacity']",mode='eval').body
    class Replace(ast.NodeTransformer):
        def __init__(self,left,right):self.left,self.right,self.count=left,right,0
        def visit_BoolOp(self,node):
            if _dump(node)==_dump(self.left):self.count+=1;return ast.copy_location(copy.deepcopy(self.right),node)
            return self.generic_visit(node)
    forward=Replace(old,new);changed=forward.visit(copy.deepcopy(tree))
    previous.require(forward.count==1,'one_saved_A_guard')
    inverse=Replace(new,old);restored=inverse.visit(copy.deepcopy(changed))
    previous.require(inverse.count==1 and _dump(restored)==_dump(tree),'inverse_saved_owner_AST')
    namespace={};exec(compile(ast.fix_missing_locations(changed),__file__,'exec'),namespace)
    return namespace['verify_owner'].__code__,hashlib.sha256(_dump(tree).encode()).hexdigest()


CODE,AST_SHA=verify_owner_code()


def make_verify_owner(namespace):
    fn=previous.verify_owner
    result=FunctionType(CODE,namespace,fn.__name__,fn.__defaults__,fn.__closure__)
    result.__kwdefaults__=fn.__kwdefaults__;return result


def source_proof():
    code,source=verify_owner_code()
    previous.require(source==AST_SHA and code.co_code==CODE.co_code,'saved_source_changed')
    return {'schema':'g31.live_initial_six_saved_v2.source.v1','old_verify_owner_AST_sha256':source,
        'inverse_AST_one_typed_window_change':True,'full_endpoint_ledger_and_original_supplied_guards_retained':True,
        'unknown_status_not_promoted':True,'saved_JSON_has_no_authority':True}
