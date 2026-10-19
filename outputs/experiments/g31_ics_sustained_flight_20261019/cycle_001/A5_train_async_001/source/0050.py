"""Fixed complete action coverage using the accepted future-only fork.

This is a diagnostic evaluator, not an online selector or a native authority.
Inputs/targets, source verification and storage belong to the caller. Every
group obtains a new initial supplied context; no engine is reused across the
three already-consumed action coordinates. Both children are created by the
unchanged paired runner before either suffix executes.
"""
from __future__ import annotations
import copy
import traceback
from . import live_obligation_full32_suffix_partition as domain
from . import validate_future_later_paired_suffix as paired

MAXIMUM_CUTS=4  # At most original+one fresh collection for each of A and B.


def require(ok,reason):
    if not ok:raise ValueError('full32_suffix_evaluator:'+reason)


def empty_rows(actions):
    domain.partition(actions)
    return {f'vector_{i:02d}':{'candidate_index':i,'action':copy.deepcopy(action),
        'status':'unknown_unexecuted'} for i,action in enumerate(actions)}


def execute_group(group,make_context,save_prediction,*,model,future):
    """One context factory, at most one engine and two future suffixes.

The factory receives only the declared prefix index/action. There is no
prediction-target or native endpoint argument. Errors keep both candidates.
"""
    result={'prefix_index':group['prefix_index'],'candidate_indices':copy.deepcopy(group['candidate_indices']),
        'context_constructions':0,'detail':None,'rows':{
            f'vector_{i:02d}':{'candidate_index':i,'action':copy.deepcopy(action),'status':'unknown_unexecuted'}
            for i,action in zip(group['candidate_indices'],group['actions'],strict=True)}}
    try:
        index=group['prefix_index']
        require(type(index) is int and 0<=index<16 and group['candidate_indices']==[2*index,2*index+1],
            'exact_prefix_indices')
        require(len(result['rows'])==2 and [a['later_action'] for a in group['actions']]==list(domain.LATER),'two_ordered_actions')
        require(all(type(a) is dict and tuple(a)==domain.FIELDS for a in group['actions']),'exact_action_fields')
        require(all(domain.token(group['actions'][0][k])==domain.token(group['actions'][1][k])
            for k in domain.FIELDS[:-1]),'past_coordinates_unchanged')
        require(paired.bytes_of(group['prefix_key'])==paired.bytes_of({k:group['actions'][0][k] for k in domain.FIELDS[:-1]}),'prefix_key')
        require(paired.bytes_of(group['representative_action'])==paired.bytes_of(group['actions'][0]),'default_representative')
        result['context_constructions']+=1
        context=make_context(group['prefix_index'],copy.deepcopy(group['representative_action']))
        detail=paired.run_case(context,copy.deepcopy(group['representative_action']),MAXIMUM_CUTS,model,future,save_prediction)
        result['detail']=detail
        require(tuple(detail['suffixes'])==domain.LATER,'complete_suffix_denominator')
        for (key,row),choice in zip(result['rows'].items(),domain.LATER,strict=True):
            suffix=detail['suffixes'][choice]
            row.update(status='unknown_prediction_returned_audit_pending' if suffix['status']=='returned'
                else 'unknown_'+suffix['status'].removeprefix('unknown_'),prefix_status=detail['prefix']['status'],suffix=copy.deepcopy(suffix))
    except Exception:
        result['error']=traceback.format_exc()
        for row in result['rows'].values():row['status']='unknown_group_error'
    return result


def evaluate(actions,make_context,save_prediction,*,model,future,on_group=lambda result:None):
    """Exhaustive fixed32 diagnostic. Not adaptive method query accounting.

Every sibling is a charged candidate. The caller must charge all setup, source
checks, input construction, clones, outputs, target checks and failure work.
"""
    partition=domain.partition(actions);rows=empty_rows(actions);groups=[]
    for group in partition['groups']:
        def save(label,value):return save_prediction(group['prefix_index'],label,value)
        result=execute_group(group,make_context,save,model=model,future=future)
        rows.update(result['rows']);groups.append(result);on_group(result)
    require(tuple(rows)==tuple(f'vector_{i:02d}' for i in range(32)) and len(groups)==16,'complete32_order')
    return {'schema':'g31.full32_future_suffix_evaluation.v1','rows':rows,'groups':groups,
        'logical_candidates':32,'maximum_initial_engines':16,'maximum_future_suffixes':32,
        'context_constructions':sum(g['context_constructions'] for g in groups),
        'native_authority':False,'hidden_state_coverage':False,'online_protection_certified':False}


def expected_prefix(target):
    """Audit-only target chronology, ending at the first known B collection."""
    result=[]
    for row in target['projected_collections']:
        require(type(row) is dict,'target_collection_shape')
        # disposition belongs to the decide remainder AFTER the saved cut and
        # may legitimately differ. Compare only the same pre-tail point fields
        # used by the accepted paired audit; complete outputs are checked below.
        result.append({k:copy.deepcopy(row[k]) for k in
            ('owner','at','phase','recollection_index','information_status','retry_admission')})
        if row['phase']=='first_reuse_route' and row['information_status']=='conditional_validated_later_v3_data':
            require(row['owner']=='B' and len(result)<=MAXIMUM_CUTS,'target_first_known_B')
            return result
    raise ValueError('full32_suffix_evaluator:target_missing_known_B')


def audit_group(result,targets):
    """Only already-produced artifacts are compared; no fallback prediction."""
    require(tuple(targets)==domain.LATER and len(result['rows'])==2,'audit_two_candidates')
    import json
    expected=expected_prefix(json.loads(targets[domain.LATER[0]]))
    other=expected_prefix(json.loads(targets[domain.LATER[1]]))
    require(paired.bytes_of(expected)==paired.bytes_of(other),'paired_target_prefix_changed')
    require(result['context_constructions']==1 and type(result['detail']) is dict,'one_constructed_prefix')
    paired.audit_case(result['detail'],expected,targets)
    for row,choice in zip(result['rows'].values(),domain.LATER,strict=True):
        row.update(status='exact_conformance',suffix=copy.deepcopy(result['detail']['suffixes'][choice]))
    result['status']='exact_two_future_suffixes'
