"""Deterministic same32 selectors over conditional forecasts, never authority.

Every method receives the same charged full32 provider. Query counts describe
selection work only. Unprotected intermediate proposals may be explored; none
are executed by this module. Final estimate protection uses all five jobs.
"""
from __future__ import annotations
import copy
import math
import time
from . import live_obligation_initial_candidate_provider as provider
from . import live_obligation_initial_decision_adapter as origin
from . import live_obligation_full32_suffix_partition as domain

METHODS=('incumbent','coordinate_strict','coordinate_plateau','pair_repair','finite_MPC')
RESTRICTIONS=('all','fixed_initial','later_default')


def require(ok,reason):
    if not ok:raise ValueError('same_information_search:'+reason)


def _known(row):
    values=row.get('completion')
    return (row.get('status')=='conditional_forecast' and type(values) is dict and set(values)==set(provider.JOBS)
        and all(type(values[k]) is float and math.isfinite(values[k]) and values[k]>=0 for k in provider.JOBS))


def select(batch,*,method,incumbent_index,restriction='all',budget=32):
    """Incumbent is a preregistered public policy argument, never learned here."""
    started=time.perf_counter()
    require(type(batch) is provider.CandidateBatch and method in METHODS and restriction in RESTRICTIONS,'declared_method')
    require(type(budget) is int and budget==32 and type(incumbent_index) is int and 0<=incumbent_index<32,'same32_budget_and_incumbent')
    require(restriction=='all' or method=='finite_MPC','restricted_complete_reference_requires_enumeration')
    queries=batch.claim(method+':'+restriction);actions=queries.domain();domain.partition(actions)
    allowed=[i for i,a in enumerate(actions) if restriction=='all'
        or restriction=='fixed_initial' and a['initial_action']=='native_default'
        or restriction=='later_default' and a['later_action']=='native_default']
    require(len(allowed)==(32 if restriction=='all' else 16),'complete_reference_domain')
    cache={};visited=[];internal_unprotected=[]
    def value(index):
        if index not in cache:cache[index]=queries.query(index)
        return cache[index]
    baseline=value(incumbent_index)
    def protected(index):
        row=cache[index]
        return (_known(row) and _known(baseline)
            and all(row['completion'][k]<=baseline['completion'][k] for k in provider.JOBS))
    # Objective association/order is explicit and identical for every method;
    # never accept a caller-supplied sum inconsistent with its five endpoints.
    def score(index):return (sum(cache[index]['completion'][k] for k in provider.JOBS),index)
    def distance(left,right):
        return sum(domain.token(actions[left][k])!=domain.token(actions[right][k]) for k in domain.FIELDS)
    if _known(baseline):
        if method=='finite_MPC':
            for index in allowed:value(index)
        elif method!='incumbent':
            frontier=[incumbent_index]
            while frontier:
                current=min(frontier,key=score);frontier.remove(current)
                if current in visited:continue
                visited.append(current)
                if not protected(current):internal_unprotected.append(current)
                eligible=[]
                for index in range(32):
                    if not 1<=distance(current,index)<=(2 if method=='pair_repair' else 1):continue
                    row=value(index)
                    if not _known(row) or index in visited:continue
                    improves=score(index)[0]<score(current)[0] if method=='coordinate_strict' else score(index)[0]<=score(current)[0]
                    if improves:eligible.append(index)
                if method=='coordinate_strict':frontier=[min(eligible,key=score)] if eligible else []
                else:frontier.extend(i for i in eligible if i not in frontier)
    selectable=[i for i in cache if i in allowed and protected(i)]
    best=min(selectable,key=score) if selectable else None
    # Complete-family certification is stricter than finding one admissible
    # estimate: one unknown keeps the reference optimum explicitly unknown.
    full_reference=(method=='finite_MPC' and all(i in cache and _known(cache[i]) for i in allowed) and _known(baseline))
    data=batch._read()
    output={'schema':'g31.live_obligation.same_information_selection.v1',
        'status':'conditional_estimate_proposal' if best is not None else 'unknown_no_admissible_estimate',
        'method':method,'restriction':restriction,'incumbent_index':incumbent_index,
        'selected_index':best,'selected_action':copy.deepcopy(actions[best]) if best is not None else None,
        'selected_completion':copy.deepcopy(cache[best]['completion']) if best is not None else None,
        'selected_prediction':copy.deepcopy(cache[best].get('prediction')) if best is not None else None,
        'estimated_per_job_delta':{k:cache[best]['completion'][k]-baseline['completion'][k] for k in provider.JOBS} if best is not None else None,
        'estimated_strict_improvement':bool(best is not None and score(best)[0]<score(incumbent_index)[0]),
        'full_reference_known':full_reference,'reference_optimum_index':best if full_reference else None,
        'allowed_candidate_indices':allowed,'declared_candidate_denominator':32,'selection_budget':budget,
        'visited_indices':visited,'internal_unprotected_visited_indices':internal_unprotected,
        'unknown_forecast_indices':[i for i,row in enumerate(data['rows']) if not _known(row)],
        'candidate_rows':[{'candidate_index':i,'action':copy.deepcopy(actions[i]),'provider_status':row['status'],
            'selection_status':'queried' if i in cache else 'not_queried_but_provider_cost_paid',
            'estimated_not_worse':protected(i) if i in cache and _known(row) and _known(baseline) else None}
            for i,row in enumerate(data['rows'])],
        'accounting':queries.accounting(),'native_protection_certified':False,'dispatch_authorized':False,
        'model_error_bound_certified':False,'online_rolling_reestimation':False,
        'tie_rule':'sum of five completion floats in declared JOBS order, then original Cartesian index',
        'fairness':'All32 forecasts and both siblings are charged to every method; query counts are not saved model computation.'}
    output['selection_before_return_seconds']=time.perf_counter()-started
    return output


def propose_initial(decision,*,method,incumbent_index,restriction='all'):
    """Minimal actual-data seam; no submit, native advance or future query.

This call may be expensive. Wall cost is reported, never presented as meeting
the product deadline. Neither the whole observed future nor a saved target is
available to any layer. Native campaign integration remains a separate task.
"""
    started=time.perf_counter()
    batch=provider.evaluate_declared32(decision)
    result=select(batch,method=method,incumbent_index=incumbent_index,restriction=restriction)
    result['local_component']=origin.unknown('no_selected_conditional_action')
    if result['selected_action'] is not None:
        try:
            actual=provider.require_current_batch_origin(batch)
            result['local_component']=origin.revalidate_first_component(actual,result['selected_action'])
        except (KeyError,TypeError,ValueError,AttributeError) as error:result['local_component']=origin.unknown(str(error))
    result['provider_evidence']=batch.audit_copy()
    result['whole_seam_before_return_seconds']=time.perf_counter()-started
    result['cost_scope']='Provider+selector+current recollection+complete evidence copy; initial collection, caller serialization and any later submit/ACK/descendants must also be charged.'
    result['complete_request_100ms_certified']=False
    return result
