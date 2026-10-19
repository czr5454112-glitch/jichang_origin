"""Separate pure historical-goal-service gate. Old raw fields stay unchanged.

No native capability, new collection, simulation or policy is implemented here.
Every unchanged current endpoint/owner/action/ACK-union/occupancy check is rerun.
"""
from __future__ import annotations
import copy
from types import FunctionType
from . import domain_guard_v2 as old
from . import live_obligation_lifecycle_state_v2 as lifecycle
from . import live_obligation_historical_service as history

VERSION='g31.live_obligation.historical_goal_service.v1'

def clone(f,namespace):
    out=FunctionType(f.__code__,namespace,f.__name__,f.__defaults__,f.__closure__)
    out.__kwdefaults__=f.__kwdefaults__
    return out

def validate_collected_endpoints(view,command,returned,*,own_publication_requests,**kwargs):
    first=old.validate_collected_endpoints(view,command,returned,**kwargs)
    if (first.get('reasons')!=['unsupported_later_model_state'] or
            first.get('bundle',{}).get('reasons')!=['stable_committed_local_service']):
        return first
    try:
        selected=[e for e in returned if history.local(e)['message_id']==kwargs['peer_message_id']]
        bounds=history.derive_goal_service_bounds(view,command['last_delivered_ack'],selected,
            retained=kwargs['retained'],own_actions=kwargs['own_actions'],
            own_publication_requests=own_publication_requests,phase=kwargs['phase'])
        def stationary(name,t,jobs,completed,*,floor,now,phase,service):
            if name not in bounds:return lifecycle.stable_stationary(name,t,jobs,completed,floor=floor,now=now,phase=phase,service=service)
            h=bounds[name];jid={'E':'receiver','P':'blocker'}[name];job=jobs[jid]
            lifecycle.require(phase=='first_reuse_route' and name in ('E','P') and jid not in completed
                and t['mode']=='loaded' and t['business_bag_id']==jid and job['status']=='in_transit'
                and t['node']==job['destination'] and t['edge_from']==t['edge_to']==t['reception_node']==-1
                and t['service_ready_known'] is True and t['ready_kind']=='committed_local_service_end'
                and t['load_complete_at']==-1. and t['service_ready_at']==h['raw_service_ready_at']
                and 0<=t['available_at']<=floor and 0<=job['loaded_at']<=h['observed_entry']['entered_at']
                and t['committed_prefix']==([1,3,4] if name=='E' else [9,3,10])
                and all(t[f]==h[f] for f in ('tray_id','business_bag_id','generation','traversal_id'))
                and floor==h['floor'] and now==h['now'] and h['derived_arrival_at']<=floor<=now<h['derived_service_end']
                and h['derived_service_end']==h['derived_arrival_at']+service[t['node']],
                'historical_stationary_goal_identity_or_interval')
            if name=='P':lifecycle.require(0<=job['loaded_at']<=job['storage_entered_at']<=job['storage_released_at']<=h['observed_entry']['entered_at'],'historical_P_storage_history')
            return h['derived_service_end']
        ns=dict(vars(lifecycle));ns['stable_stationary']=stationary;ns['VERSION']=VERSION
        bundle_function=clone(lifecycle.later_bundle,ns)
        def bundle(*args,**kw):
            result=bundle_function(*args,**kw)
            if result['status']=='conditional_model_input':
                result['derived_goal_service_bounds']=copy.deepcopy(bounds)
                result['raw_service_ready_fields_preserved']=True
            return result
        namespace=dict(vars(old.old));namespace['later_bundle']=bundle
        namespace['validate_later_pair']=clone(old.old.validate_later_pair,namespace)
        validate=clone(old.old.validate_collected_endpoints,namespace)
        result=validate(view,command,returned,**kwargs)
        result['historical_service_scope']='conditional_supplied_data_only_no_new_native_or_policy_execution'
        return result
    except (KeyError,TypeError,ValueError,OverflowError,AttributeError) as exc:
        first['historical_goal_service_check']={'status':'unknown','reason':str(exc)}
        return first
