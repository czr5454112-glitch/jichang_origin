"""Equal-domain conditional proposal searches; no native forks/outcome lookup.

Predicted non-regression is an exact point-estimate predicate, not a native
protection certificate. All preparation and all evaluations belong to the
request. This version deliberately retains repeated validation cost.
"""
from __future__ import annotations
import copy
import math
import time
from . import public_native_preference_projection as initial
from . import public_native_later_preference_projection as later

VERSION='public_native_preference_search_v1'
METHODS=('coordinate_strict','coordinate_plateau','resource_pair_repair','finite_horizon_enumeration')


def search(actions, base, evaluate, *, method, budget, selectable=None):
    if method not in METHODS+('incumbent','fixed_initial_window') or type(budget) is not int or budget<1:
        raise ValueError('preference_search:unsupported_search_contract')
    ordered=sorted(actions); selectable=set(ordered) if selectable is None else set(selectable)
    if base not in actions or not selectable.issubset(actions):
        raise ValueError('preference_search:invalid_domain')
    cache={}; hit=False
    def value(key):
        nonlocal hit
        if key in cache:return cache[key]
        if len(cache)>=budget:hit=True;return None
        started=time.perf_counter();prediction=evaluate(actions[key]);elapsed=time.perf_counter()-started
        reference=cache[base]['prediction'] if base in cache else prediction
        known=(prediction.get('status')==reference.get('status')=='conditional_prediction'
               and set(prediction.get('completion',{}))==set(reference.get('completion',{}))==initial.contract.JOBS
               and all(type(x) in (int,float) and math.isfinite(x) for x in prediction['completion'].values())
               and all(type(x) in (int,float) and math.isfinite(x) for x in reference['completion'].values()))
        predicate=all(prediction['completion'][j]<=reference['completion'][j] for j in initial.contract.JOBS) if known else None
        cache[key]={'action':copy.deepcopy(actions[key]),'prediction':prediction,
                    'predicted_all_job_not_worse':predicate,'model_call_wall_seconds':elapsed}
        return cache[key]
    value(base)
    score=lambda key:(cache[key]['prediction']['completion_sum'],key)
    if cache[base]['predicted_all_job_not_worse'] is True:
        if method in ('finite_horizon_enumeration','fixed_initial_window'):
            for key in ordered:
                if key in selectable and value(key) is None:break
        elif method!='incumbent':
            frontier=[base];visited=set()
            while frontier and not hit:
                current=min(frontier,key=score);frontier.remove(current)
                if current in visited:continue
                visited.add(current);eligible=[]
                for key in ordered:
                    distance=sum(a!=b for a,b in zip(key,current))
                    if not 1<=distance<=(2 if method=='resource_pair_repair' else 1):continue
                    row=value(key)
                    if row is None:break
                    if row['predicted_all_job_not_worse'] is not True:continue
                    improves=(score(key)[0]<score(current)[0] if method=='coordinate_strict'
                              else score(key)[0]<=score(current)[0])
                    if improves and key not in visited:eligible.append(key)
                if method=='coordinate_strict':frontier=[min(eligible,key=score)] if eligible else []
                else:frontier.extend(k for k in eligible if k not in frontier)
    candidates=[key for key,row in cache.items() if key in selectable and row['predicted_all_job_not_worse'] is True]
    best=min(candidates,key=score) if candidates else None
    return {'status':'conditional_model_proposal' if best is not None else 'unknown_no_eligible_projection',
        'method':method,'selected_action':copy.deepcopy(actions[best]) if best is not None else None,
        'selected_prediction':cache[best]['prediction'] if best is not None else None,
        'evaluations':len(cache),'evaluation_budget':budget,'candidate_denominator':len(actions),
        'selectable_denominator':len(selectable),'stop_reason':'evaluation_budget_exhausted' if hit else 'declared_neighborhood_exhausted',
        'rows':[{**cache[k],'evaluation_status':'evaluated','key':list(k)} if k in cache else
                {'action':copy.deepcopy(actions[k]),'key':list(k),'evaluation_status':'unknown_unexecuted',
                 'predicted_all_job_not_worse':None} for k in ordered],
        'native_protection_certified':False,'model_error_bound_certified':False,
        'online_information_delivered':False,'used_native_fork_or_saved_outcome_input':False}


def initial_proposal(bundle, *, method, fixed_window=None, later_default_only=False):
    start=time.perf_counter()
    if bundle.get('status')!='conditional_model_input' or bundle.get('model_version')!=initial.contract.VERSION:
        return {'status':'unknown_initial_input','selected_action':None,'native_protection_certified':False}
    try:case=initial.contract.infer_case(bundle.get('jobs',{}))
    except (TypeError,KeyError,ValueError):case=None
    if case is None:return {'status':'unknown_population','selected_action':None,'native_protection_certified':False}
    windows=initial.contract.domain.domain(case)['public_derivation']['supply_windows']
    domain={(i,w,r,l):{'initial_action':initial_action,'empty_departure':window,
            'return_delay':delay,'later_action':later_action}
        for i,initial_action in enumerate(('native_default','prefer_2'))
        for w,window in enumerate(windows) for r,delay in enumerate((0.,.5))
        for l,later_action in enumerate(('native_default','prefer_8'))}
    selectable=None
    if method=='fixed_initial_window':
        if type(fixed_window) is not int or not 0<=fixed_window<4:raise ValueError('preference_search:invalid_fixed_window')
        selectable={key for key in domain if key[0]==0 and key[1]==fixed_window}
    elif fixed_window is not None:raise ValueError('preference_search:unexpected_fixed_window')
    if type(later_default_only) is not bool:raise ValueError('preference_search:invalid_ablation')
    if later_default_only:
        selectable={key for key in domain if key[3]==0} if selectable is None else {key for key in selectable if key[3]==0}
    result=search(domain,(0,0,0,0),lambda action:initial.predict(bundle,action),method=method,budget=32,selectable=selectable)
    result.update(model_version=VERSION,stage='initial',fixed_window=fixed_window,
        proposal_wall_seconds=time.perf_counter()-start,all_preparation_charged=True,
        future_components_nonbinding=True,first_actions_only=('initial_route_preference_if_selected','E_transfer_earliest_departure'),
        public_window_derivation=initial.contract.domain.domain(case)['public_derivation'],later_default_only=later_default_only)
    return result


def later_proposal(bundle, *, method, later_default_only=False):
    start=time.perf_counter()
    domain={(r,l):{'return_delay':delay,'later_action':action} for r,delay in enumerate((0.,.5))
            for l,action in enumerate(('native_default','prefer_8'))}
    if type(later_default_only) is not bool:raise ValueError('preference_search:invalid_ablation')
    result=search(domain,(0,0),lambda action:later.predict(bundle,action),method=method,budget=4,
        selectable={key for key in domain if key[1]==0} if later_default_only else None)
    result.update(model_version=VERSION,stage=bundle.get('phase'),proposal_wall_seconds=time.perf_counter()-start,
        all_preparation_charged=True,future_components_nonbinding=True,
        inactive_coordinates=['return_delay'] if bundle.get('phase')=='first_reuse_route' else [],
        later_default_only=later_default_only)
    return result
