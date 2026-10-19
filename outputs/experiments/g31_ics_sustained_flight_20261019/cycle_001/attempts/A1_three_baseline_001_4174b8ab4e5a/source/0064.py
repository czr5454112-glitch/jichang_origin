"""Full32 conditional estimates with private model graph ownership.

The controller path omits diagnostic traversals and binds static proof once. It keeps
16 independently guarded initial contexts,32 complete graph clones, all dynamic
cut checks and one request-bound future-fork source inventory. No target/native
state, diagnostic outcome or caller-supplied forecast table enters evaluation.
"""
from __future__ import annotations
import copy
import copyreg
import hashlib
from pathlib import Path
import time
import traceback
from . import live_obligation_initial_candidate_provider as previous
from . import live_obligation_initial_decision_adapter_v2 as origin
from . import live_obligation_owned_prefix_evaluator as execution
from . import live_obligation_full32_suffix_partition as domain
from . import live_obligation_future_later_fork as future
from . import live_obligation_bound_future_fork_v3 as binding

VERSION='g31.live_obligation.owned_initial_conditional32_provider.v1'
JOBS=previous.JOBS
CandidateBatch=previous.CandidateBatch
CandidateQueries=previous.CandidateQueries
known_completion=previous.known_completion
encoding=previous.encoding
require=previous.require
_ORIGIN={name:getattr(origin,name) for name in ('require_current','supplied_snapshot','revalidate_first_component')}
_EXECUTION=execution.execute_group
_BOUND_EXECUTION=execution.execute_bound_group
_BOUND_PROOF=execution.bound_source_proof
_BIND_REQUEST=binding.bind_request
_COPY_SLOTNAMES=copyreg._slotnames
_COPY_SLOTNAMES_CODE=_COPY_SLOTNAMES.__code__
_COPYREG_SHA256='a04efa4d0f7034a190700f4df14893f09b37bc51e8ad6ed441fa9200a7f0bd52'
_COPY_CLASSES=(future.core.Projection,future.core.lazy.original.captures.CaptureWorld,
    future.core.lazy.original.policy.PhaseReplyBudget)


def _prepare_copy_metadata():
    require(copyreg._slotnames is _COPY_SLOTNAMES and _COPY_SLOTNAMES.__code__ is _COPY_SLOTNAMES_CODE,
        'canonical_copy_slotnames_function')
    source=Path(copyreg.__file__).resolve()
    require(hashlib.sha256(source.read_bytes()).hexdigest()==_COPYREG_SHA256,'canonical_copyreg_source')
    current=(future.core.Projection,future.core.lazy.original.captures.CaptureWorld,
        future.core.lazy.original.policy.PhaseReplyBudget)
    require(all(actual is expected for actual,expected in zip(current,_COPY_CLASSES,strict=True)),
        'exact_copy_metadata_classes')
    rows=[]
    for cls in current:
        require(type(cls) is type and not any('__slots__' in vars(base) for base in cls.__mro__),
            'declared_copy_classes_have_no_slots')
        namespace=vars(cls);before=dict(namespace);present='__slotnames__' in namespace
        require(not present or type(namespace['__slotnames__']) is list and not namespace['__slotnames__'],
            'unexpected_existing_copy_slotnames')
        names=_COPY_SLOTNAMES(cls)
        require(type(names) is list and not names and namespace.get('__slotnames__') is names,
            'canonical_empty_copy_slotnames')
        require(tuple(namespace)==tuple(before)+(('__slotnames__',) if not present else ())
            and all(namespace[name] is value for name,value in before.items()),'only_copy_metadata_initialized')
        rows.append({'class':cls.__module__+'.'+cls.__qualname__,'already_present':present,
            'materialized':not present,'slotnames':[]})
    return {'classes':rows,'copyreg_source_sha256':_COPYREG_SHA256,
        'standard_library_slotnames_function':True,'full_class_namespace_still_sealed':True,
        'model_context_or_observation_reused':False,'model_execution':False}


_CODES={function:function.__code__ for function in (*_ORIGIN.values(),_EXECUTION,
    _BOUND_EXECUTION,_BOUND_PROOF,_BIND_REQUEST,_prepare_copy_metadata,_COPY_SLOTNAMES)}


def source_proof(request=None):
    require(all(getattr(origin,name) is value for name,value in _ORIGIN.items())
        and execution.execute_group is _EXECUTION
        and execution.execute_bound_group is _BOUND_EXECUTION
        and execution.bound_source_proof is _BOUND_PROOF and binding.bind_request is _BIND_REQUEST
        and all(function.__code__ is code for function,code in _CODES.items()),'owned_provider_source_bindings')
    return {'schema':VERSION,'execution':execution.source_proof() if request is None else execution.bound_source_proof(request),
        'origin_version':origin.VERSION,'final_revalidation_module':origin.revalidate_first_component.__module__,
        'contexts_per_complete_batch':16,'complete_graph_clones_per_complete_batch':32,
        'all_candidate_cost_charged_to_each_method':True,'diagnostic_graph_traversals':False,
        'no_context_or_source_inventory_cache':request is None,'initial_context_cache':False,
        'source_inventory_cache_scope':'none' if request is None else 'one_request_exact_dependencies',
        'native_authority':False}


def _group_error(group,error):
    return {'prefix_index':group['prefix_index'],'candidate_indices':copy.deepcopy(group['candidate_indices']),
        'context_constructions':1,'detail':None,'error':error,
        'rows':{f'vector_{i:02d}':{'candidate_index':i,'action':copy.deepcopy(action),'status':'unknown_group_error'}
            for i,action in zip(group['candidate_indices'],group['actions'],strict=True)}}


def _invalidate(result,rows,error):
    result['status']='unknown_initial_origin_or_provider'
    result.setdefault('error',error)
    for row in rows:row.update(status='unknown_origin_or_provider_failure',completion=None)


def evaluate_declared32(decision):
    started=time.perf_counter();actions=future.core.lazy.original.physics.previous.actions();partition=domain.partition(actions)
    rows=[{'candidate_index':i,'action':copy.deepcopy(a),'status':'unknown_unexecuted','completion':None} for i,a in enumerate(actions)]
    result={'schema':VERSION,'rows':rows,'groups':[],'counts':{'logical_candidates':32,'context_constructions':0,
        'initial_engines':0,'initial_advances':0,'prefix_same_resumes':0,'future_forks':0,'future_resumes':0},
        'status':'unknown_in_progress','native_protection_certified':False,'online_rolling_reestimation':False,
        'source_binding':{'status':'unknown_not_bound','cold_bind_attempts':0}}
    request=None
    try:
        origin.require_current(decision);audit=decision.audit_copy()
        result.update(owner=audit['owner'],initial_public_sha256=audit['public_sha256'],actual_collection_at=audit['at'])
        result['source_binding']['copy_metadata_preparation']=_prepare_copy_metadata()
        result['source_binding']['cold_bind_attempts']=1
        request=binding.bind_request()
        result['source_binding']['status']='bound_setup_pending'
        source_proof(request)
        result['source_binding']['status']='bound_setup_checked'
        for group in partition['groups']:
            predictions={};binding_error=None
            try:
                # Revalidate all actual supplied initial facts for each prefix.
                context=origin.supplied_snapshot(decision)
                item=execution.execute_bound_group(request,group,context)
                detail=item['detail'];predictions=item['predictions']
                binding_error=item.get('binding_error')
                if binding_error is not None:
                    detail['binding_error']=binding_error
                    result['source_binding'].setdefault('group_error',binding_error)
            except Exception:
                detail=_group_error(group,traceback.format_exc())
            result['groups'].append(detail);result['counts']['context_constructions']+=detail['context_constructions']
            inner=detail.get('detail')
            if inner is not None:
                for key,value in inner['counts'].items():result['counts'][key]+=value
            for i,choice in zip(group['candidate_indices'],domain.LATER,strict=True):
                suffix=detail['rows'][f'vector_{i:02d}'];prediction=predictions.get(choice)
                completion=known_completion(prediction)
                owned_ok=(binding_error is None and inner is not None and inner['prefix'].get('status')=='supported_known_B_cut'
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
        if 'group_error' in result['source_binding']:
            _invalidate(result,rows,result['source_binding']['group_error'])
    except Exception as error:
        _invalidate(result,rows,str(error))
        result['error_traceback']=traceback.format_exc()
    finally:
        if request is not None:
            evidence=result['source_binding'];evidence['close_attempted']=True
            try:
                evidence['before_close']=request.description()
                uses=evidence['before_close']['proof_binding']['proof_uses']
                require(type(uses) is int and 1<=uses<=65,'bound_request_proof_use_range')
                require(result['status']!='conditional_forecasts_complete' or uses==65,
                    'complete_full32_requires65_proof_uses')
            except Exception as error:
                evidence['inspection_error']=traceback.format_exc()
                _invalidate(result,rows,str(error))
            finally:
                try:
                    request.close()
                    evidence['close_completed']=True
                except Exception as error:
                    evidence['close_error']=traceback.format_exc()
                    evidence['close_completed']=False
                    _invalidate(result,rows,str(error))
            evidence['status']=('closed_complete65' if result['status']=='conditional_forecasts_complete'
                else 'closed_with_unknowns' if evidence['close_completed'] and 'inspection_error' not in evidence
                else 'unknown_binding_cleanup')
    result['provider_preseal_seconds']=time.perf_counter()-started
    result['complete_request_100ms_certified']=False
    result['cost_scope']='Cold source bind/up to65 checked static proof uses/final close/16 fresh guarded initial contexts/16 prefixes/32 complete graph clones and suffixes/in-memory outputs included. Diagnostic traversals omitted by private construction ownership. Prior collection and future selection/revalidation/serialization/submit/ACK descendants remain separately charged.'
    batch=CandidateBatch(previous._TOKEN,result,decision)
    batch._provider_elapsed=time.perf_counter()-started
    return batch


def require_current_batch_origin(batch):
    require(type(batch) is CandidateBatch,'conditional_batch_type');batch._read();origin.require_current(batch._decision)
    return batch._decision
