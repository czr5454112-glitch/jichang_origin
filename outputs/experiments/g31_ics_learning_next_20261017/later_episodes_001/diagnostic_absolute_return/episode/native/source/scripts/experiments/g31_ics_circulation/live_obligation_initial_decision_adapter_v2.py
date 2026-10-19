"""Actual initial-route window from the already guarded own load transition.

observe_protocol has no service_ready_* tray fields. The explicitly derived
earliest source-service end below is a conservative bound, not a new native
sensor or execution guarantee. All original current-origin checks remain.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import inspect
import json
import math
import textwrap
from types import FunctionType
from . import live_obligation_initial_decision_adapter as previous

native_gate,history,supplied,representation,domain=(getattr(previous,k) for k in
    ('native_gate','history','supplied','representation','domain'))
InitialDecision=previous.InitialDecision
require_current=previous.require_current
collect_initial_decision=previous.collect_initial_decision
supplied_snapshot=previous.supplied_snapshot
unknown=previous.unknown
VERSION='g31.live_obligation.actual_initial_decision.v2'


def require(ok,reason):
    if not ok:raise ValueError('initial_route_window_v2:'+reason)


def finite_float(value):return type(value) is float and math.isfinite(value)


def route_window_from_validated(public,validated):
    """Pure arithmetic/identity check; its caller must rerun the original guard.

This helper accepts data and grants no native authority. It is separate so
exact wire-boundary and malformed derivation tests need no fabricated session.
"""
    history.payload_encoding({'public':public,'validated':validated})
    view=public['view'];now=view['now']
    require(validated['status']=='conditional_validated_data' and validated['owner']=='A'
        and view['owner_id']=='A' and finite_float(now) and now==.11,'owner_epoch')
    capture=validated['envelopes']['A']['capture']
    ack=public['command']['last_delivered_ack']
    require(validated['own_delivered_ack']==ack
        and validated['envelopes']['A']==ack['planning_snapshot'],'same_guarded_own_capture')
    require(capture['source_owner']=='A' and capture['target_owner']=='B','source_authority')
    current=[t for t in view['trays'] if t['tray_id']=='L']
    captured=[t for t in capture['trays'] if t['tray_id']=='L']
    jobs=[j for j in view['jobs'] if j['business_bag_id']=='loaded']
    transitions=[t for t in validated['conditional_projection'] if t['tray_id']=='L']
    nodes=[n for n in view['node_records'] if n[0]==0]
    require(len(current)==len(captured)==len(jobs)==len(transitions)==len(nodes)==1,'unique_source_rows')
    tray,prior,job,transition,node=current[0],captured[0],jobs[0],transitions[0],nodes[0]
    for item in (tray,prior):
        require(item['node']==0 and item['business_bag_id']=='loaded'
            and item['edge_from']==item['edge_to']==item['reception_node']==-1
            and item['committed_prefix']==[0],'source_uncommitted_identity')
        require(all(type(item[k]) is int and item[k]>=0 for k in ('generation','traversal_id')),'integer_public_identity')
    require(all(tray[k]==prior[k] for k in ('tray_id','node','business_bag_id','generation','traversal_id',
        'edge_from','edge_to','reception_node','committed_prefix')),'capture_current_identity')
    require(tray['mode']=='loaded' and prior['mode']=='loading'
        and prior['service_ready_known'] is True and prior['ready_kind']=='observed_load_completion','typed_load_transition')
    finish=prior['load_complete_at'];service=node[2];bound=transition['first_possible_source_service_end']
    require(all(finite_float(x) for x in (finish,service,bound,prior['service_ready_at'],capture['captured_at'],job['loaded_at']))
        and service>=.001 and capture['captured_at']<finish<=now,'finite_observed_load_and_service')
    require(prior['service_ready_at']==finish==job['loaded_at']
        and job['origin']==0 and job['status']=='in_transit' and job['allow_suffix_reroute'] is True,'current_completed_load')
    require(transition['source']=='A' and transition['from_mode']=='loading' and transition['to_mode']=='loaded'
        and transition['source_captured_at']==capture['captured_at']
        and transition['source_known_load_complete_at']==finish and transition['projected_at']==now,'guarded_transition_identity')
    require(bound==finish+service and now+.01<bound,'strict_earliest_source_service_bound')
    return {'schema':'g31.initial_route_window_derivation.v1','source':'validated_own_loading_transition_and_public_node_service',
        'source_owner':'A','tray_id':'L','business_bag_id':'loaded','generation':tray['generation'],
        'traversal_id':tray['traversal_id'],'capture_message_id':capture['message_id'],
        'capture_payload_sha256':validated['envelopes']['A']['payload_sha256'],
        'captured_at':capture['captured_at'],'ack_delivered_at':ack['delivered_at'],
        'current_loaded_at':finish,'public_node_service_seconds':service,'at':now,'wire_seconds':.01,
        'derived_earliest_source_service_end':bound,'exact_current_service_end_observed':False,
        'native_authority':False,'native_route_execution_certified':False}


def route_window_from_public(public):
    """Rerun all original supplied-data guards before deriving a bound."""
    context=supplied.initial_context(**public)
    require(type(context) is supplied.SuppliedContext,'full_fresh_initial_guard')
    payload=json.loads(context._payload)
    require(history.payload_encoding(payload['evidence'])==history.payload_encoding(public),'exact_revalidated_public')
    return route_window_from_validated(public,payload['validated'])


def _strict_route_window(fresh,view,tray,now):
    require_current(fresh)
    public=json.loads(fresh._public_bytes)
    require(history.payload_encoding(view)==history.payload_encoding(public['view']) and now==view['now']
        and [t for t in view['trays'] if t['tray_id']=='L']==[tray],'fresh_local_view_binding')
    route_window_from_public(public)
    require_current(fresh)
    return True


def _dump(tree):return ast.dump(tree,include_attributes=False)


def refresh_code():
    function=previous.revalidate_first_component
    tree=ast.parse(textwrap.dedent(inspect.getsource(function)))
    old=ast.parse("require(tray['service_ready_known'] is True and type(tray['service_ready_at']) is float and math.isfinite(tray['service_ready_at']) and now+.01<tray['service_ready_at'],'strict_actual_route_wire_window')",mode='eval').body
    new=ast.parse("require(_strict_route_window(fresh,view,tray,now),'strict_actual_route_wire_window')",mode='eval').body
    class Replace(ast.NodeTransformer):
        def __init__(self,left,right):self.left,self.right,self.count=left,right,0
        def visit_Call(self,node):
            if _dump(node)==_dump(self.left):self.count+=1;return ast.copy_location(copy.deepcopy(self.right),node)
            return self.generic_visit(node)
    forward=Replace(old,new);changed=forward.visit(copy.deepcopy(tree));require(forward.count==1,'one_missing_field_guard')
    inverse=Replace(new,old);restored=inverse.visit(copy.deepcopy(changed))
    require(inverse.count==1 and _dump(restored)==_dump(tree),'inverse_refresh_AST')
    namespace={};exec(compile(ast.fix_missing_locations(changed),__file__,'exec'),namespace)
    return namespace[function.__name__].__code__,hashlib.sha256(_dump(tree).encode()).hexdigest()


_CODE,_AST=refresh_code()
_GLOBALS={**previous.revalidate_first_component.__globals__,'_strict_route_window':_strict_route_window}
revalidate_first_component=FunctionType(_CODE,_GLOBALS,previous.revalidate_first_component.__name__,
    previous.revalidate_first_component.__defaults__,previous.revalidate_first_component.__closure__)
revalidate_first_component.__kwdefaults__=previous.revalidate_first_component.__kwdefaults__


def source_proof():
    code,source=refresh_code();require(source==_AST and code.co_code==_CODE.co_code,'refresh_source_changed')
    require(all(_GLOBALS[k] is v for k,v in previous.revalidate_first_component.__globals__.items())
        and set(_GLOBALS)==set(previous.revalidate_first_component.__globals__)|{'_strict_route_window'},'defining_globals')
    return {'schema':VERSION,'original_refresh_AST_sha256':source,'inverse_AST_one_guard_replacement':True,
        'original_collect_and_current_guards_unchanged':True,'original_owned_target_capacity_check_unchanged':True,
        'fresh_initial_data_guard_rerun':True,'missing_view_fields_not_fabricated':True,
        'strict_wire_earliest_bound_not_exact_sensor':True,'native_hidden_state_reads':False,
        'dispatch_authority':False,'native_protection_certified':False}
