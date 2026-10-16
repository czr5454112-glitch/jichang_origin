"""Full32 conditional estimates with private model graph ownership.

This revision removes only diagnostic traversals from model execution. It keeps
16 independently guarded initial contexts,32 complete graph clones, all dynamic
cut checks and the unchanged future-fork source inventory. No target/native
state, diagnostic outcome or caller-supplied forecast table enters evaluation.
"""
from __future__ import annotations
import copy
import time
import traceback
from . import live_obligation_initial_candidate_provider as previous
from . import live_obligation_initial_decision_adapter_v2 as origin
from . import live_obligation_owned_prefix_evaluator as execution
from . import live_obligation_full32_suffix_partition as domain
from . import live_obligation_future_later_fork as future

VERSION='g31.live_obligation.owned_initial_conditional32_provider.v1'
JOBS=previous.JOBS
CandidateBatch=previous.CandidateBatch
CandidateQueries=previous.CandidateQueries
known_completion=previous.known_completion
encoding=previous.encoding
require=previous.require
_ORIGIN={name:getattr(origin,name) for name in ('require_current','supplied_snapshot','revalidate_first_component')}
_EXECUTION=execution.execute_group
_CODES={function:function.__code__ for function in (*_ORIGIN.values(),_EXECUTION)}


def source_proof():
    require(all(getattr(origin,name) is value for name,value in _ORIGIN.items())
        and execution.execute_group is _EXECUTION
        and all(function.__code__ is code for function,code in _CODES.items()),'owned_provider_source_bindings')
    return {'schema':VERSION,'execution':execution.source_proof(),
        'origin_version':origin.VERSION,'final_revalidation_module':origin.revalidate_first_component.__module__,
        'contexts_per_complete_batch':16,'complete_graph_clones_per_complete_batch':32,
        'all_candidate_cost_charged_to_each_method':True,'diagnostic_graph_traversals':False,
        'no_context_or_source_inventory_cache':True,'native_authority':False}


def _group_error(group,error):
    return {'prefix_index':group['prefix_index'],'candidate_indices':copy.deepcopy(group['candidate_indices']),
        'context_constructions':1,'detail':None,'error':error,
        'rows':{f'vector_{i:02d}':{'candidate_index':i,'action':copy.deepcopy(action),'status':'unknown_group_error'}
            for i,action in zip(group['candidate_indices'],group['actions'],strict=True)}}


def evaluate_declared32(decision):
    started=time.perf_counter();actions=future.core.lazy.original.physics.previous.actions();partition=domain.partition(actions)
    rows=[{'candidate_index':i,'action':copy.deepcopy(a),'status':'unknown_unexecuted','completion':None} for i,a in enumerate(actions)]
    result={'schema':VERSION,'rows':rows,'groups':[],'counts':{'logical_candidates':32,'context_constructions':0,
        'initial_engines':0,'initial_advances':0,'prefix_same_resumes':0,'future_forks':0,'future_resumes':0},
        'status':'unknown_in_progress','native_protection_certified':False,'online_rolling_reestimation':False}
    try:
        origin.require_current(decision);audit=decision.audit_copy()
        result.update(owner=audit['owner'],initial_public_sha256=audit['public_sha256'],actual_collection_at=audit['at'])
        source_proof()
        for group in partition['groups']:
            predictions={}
            try:
                # Revalidate all actual supplied initial facts for each prefix.
                context=origin.supplied_snapshot(decision)
                item=execution.execute_group(group,context)
                detail=item['detail'];predictions=item['predictions']
            except Exception:
                detail=_group_error(group,traceback.format_exc())
            result['groups'].append(detail);result['counts']['context_constructions']+=detail['context_constructions']
            inner=detail.get('detail')
            if inner is not None:
                for key,value in inner['counts'].items():result['counts'][key]+=value
            for i,choice in zip(group['candidate_indices'],domain.LATER,strict=True):
                suffix=detail['rows'][f'vector_{i:02d}'];prediction=predictions.get(choice)
                completion=known_completion(prediction)
                owned_ok=(inner is not None and inner['prefix'].get('status')=='supported_known_B_cut'
                    and inner['prefix'].get('isolation_basis')==execution.OWNERSHIP
                    and inner['prefix'].get('diagnostic_graphs_computed') is False
                    and inner['prefix'].get('parent_unconsumed') is True
                    and inner['suffixes'][choice].get('status')=='returned'
                    and suffix.get('status')=='unknown_prediction_returned_audit_pending'
                    and inner['suffixes'][choice].get('isolation_basis')==execution.OWNERSHIP)
                rows[i].update(status='conditional_forecast' if owned_ok and completion is not None else 'unknown_projection',
                    completion=completion if owned_ok else None,prediction=prediction,execution=suffix)
        origin.require_current(decision)
        result['status']='conditional_forecasts_complete' if all(r['status']=='conditional_forecast' for r in rows) else 'conditional_forecasts_with_unknowns'
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError) as error:
        result.update(status='unknown_initial_origin_or_provider',error=str(error))
        for row in rows:row.update(status='unknown_origin_or_provider_failure',completion=None)
    result['provider_preseal_seconds']=time.perf_counter()-started
    result['complete_request_100ms_certified']=False
    result['cost_scope']='All source checks/16 fresh guarded initial contexts/16 prefixes/32 complete graph clones and suffixes/in-memory outputs included. Diagnostic traversals omitted by private construction ownership. Prior collection and future selection/revalidation/serialization/submit/ACK descendants remain separately charged.'
    batch=CandidateBatch(previous._TOKEN,result,decision)
    batch._provider_elapsed=time.perf_counter()-started
    return batch


def require_current_batch_origin(batch):
    require(type(batch) is CandidateBatch,'conditional_batch_type');batch._read();origin.require_current(batch._decision)
    return batch._decision
