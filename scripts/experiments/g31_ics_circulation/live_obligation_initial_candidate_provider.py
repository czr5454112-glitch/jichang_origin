"""Same32 conditional forecasts from one actual delivered initial collection.

No saved outcome, target, case label, native fork or other owner's endpoint is
an argument. This provider deliberately computes/charges every sibling; a later
search query count never claims that fewer models were computed.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
import time
from . import live_obligation_initial_decision_adapter as origin
from . import live_obligation_full32_suffix_evaluator as evaluator
from . import live_obligation_full32_suffix_partition as domain
from . import live_obligation_future_later_fork as future

_TOKEN=object()
JOBS=('loaded','receiver','reuse1','reuse2','blocker')
VERSION='g31.live_obligation.initial_conditional32_provider.v1'


def require(ok,reason):
    if not ok:raise ValueError('initial_provider:'+reason)


def encoding(value):return json.dumps(value,allow_nan=False,separators=(',',':'))


def known_completion(prediction):
    if type(prediction) is not dict or prediction.get('status')!='conditional_prediction':return None
    values=prediction.get('completion')
    if type(values) is not dict or set(values)!=set(JOBS):return None
    if not all(type(values[k]) is float and math.isfinite(values[k]) and values[k]>=0 for k in JOBS):return None
    if prediction.get('unknown_information_phases')!=[]:return None
    return {k:values[k] for k in JOBS}


class CandidateBatch:
    """One search may claim it. It cannot authorize native execution."""
    __slots__=('_token','_bytes','_digest','_claimed','_decision','_provider_elapsed')
    def __init__(self,token,data,decision):
        require(token is _TOKEN,'provider_factory_required')
        require(type(data['rows']) is list and len(data['rows'])==32
            and [r['candidate_index'] for r in data['rows']]==list(range(32)),'full32_order')
        domain.partition([r['action'] for r in data['rows']])
        self._token=token;self._bytes=encoding(data);self._digest=hashlib.sha256(self._bytes.encode()).hexdigest()
        self._claimed=False;self._decision=decision;self._provider_elapsed=None

    def _read(self):
        require(type(self) is CandidateBatch and self._token is _TOKEN
            and hashlib.sha256(self._bytes.encode()).hexdigest()==self._digest,'batch_integrity')
        return json.loads(self._bytes)

    def audit_copy(self):
        value=self._read();value.update(batch_sha256=self._digest,search_already_claimed=self._claimed,
            native_protection_certified=False,dispatch_authorized=False,saved_copy_has_authority=False)
        return value

    def claim(self,method):
        require(type(method) is str and method and self._claimed is False,'one_search_per_charged_batch')
        self._claimed=True
        return CandidateQueries(_TOKEN,self,method)


class CandidateQueries:
    __slots__=('_token','_batch','method','indices')
    def __init__(self,token,batch,method):
        require(token is _TOKEN,'provider_query_factory');self._token,self._batch,self.method=token,batch,method;self.indices=[]
    def query(self,index):
        require(self._token is _TOKEN and type(index) is int and 0<=index<32,'declared_candidate_index')
        if index not in self.indices:self.indices.append(index)
        require(len(self.indices)<=32,'logical_query_budget')
        return self._batch._read()['rows'][index]
    def domain(self):
        return [copy.deepcopy(row['action']) for row in self._batch._read()['rows']]
    def accounting(self):
        data=self._batch._read()
        return {'provider_charged_candidate_denominator':32,'provider_counts':data['counts'],
            'provider_preseal_seconds':data['provider_preseal_seconds'],
            'provider_measured_through_seal_seconds':self._batch._provider_elapsed,'query_indices':list(self.indices),
            'queried_indices':len(self.indices),'model_budget_saved_by_queries':False,
            'complete_request_100ms_certified':False,'batch_sha256':self._batch._digest,
            'initial_public_sha256':data.get('initial_public_sha256'),'owner':data.get('owner')}


def evaluate_declared32(decision):
    """All guarded construction, source proof, copies and exports are charged.

Returns an immutable *forecast* batch even on failure, with32 unknowns. The
native decision handle is validated before and after computation. No native
clock advance, result/queue peek or opposite-owner observation is performed.
"""
    started=time.perf_counter();actions=future.core.lazy.original.physics.previous.actions();partition=domain.partition(actions)
    rows=[{'candidate_index':i,'action':copy.deepcopy(a),'status':'unknown_unexecuted','completion':None} for i,a in enumerate(actions)]
    result={'schema':VERSION,'rows':rows,'groups':[],'counts':{'logical_candidates':32,'context_constructions':0,
        'initial_engines':0,'initial_advances':0,'prefix_same_resumes':0,'future_forks':0,'future_resumes':0},
        'status':'unknown_in_progress','native_protection_certified':False,'online_rolling_reestimation':False}
    try:
        origin.require_current(decision);audit=decision.audit_copy()
        result.update(owner=audit['owner'],initial_public_sha256=audit['public_sha256'],actual_collection_at=audit['at'])
        future.source_proof()
        for group in partition['groups']:
            predictions={}
            def make_context(index,action):
                # One freshly revalidated initial context per consumed prefix.
                # No other owner's current private view enters this factory.
                return origin.supplied_snapshot(decision)
            def save(label,value):
                raw=encoding(value);predictions[label]=json.loads(raw)
                return {'memory_label':label,'sha256':hashlib.sha256(raw.encode()).hexdigest(),'bytes':len(raw.encode())}
            detail=evaluator.execute_group(group,make_context,save,model=future.core,future=future)
            result['groups'].append(detail);result['counts']['context_constructions']+=detail['context_constructions']
            inner=detail.get('detail')
            if inner is not None:
                for key,value in inner['counts'].items():result['counts'][key]+=value
            for i,choice in zip(group['candidate_indices'],domain.LATER,strict=True):
                row=rows[i];suffix=detail['rows'][f'vector_{i:02d}'];prediction=predictions.get(choice)
                completion=known_completion(prediction)
                graph_ok=(inner is not None and inner['prefix'].get('status')=='supported_known_B_cut'
                    and inner['prefix'].get('complete_graph_only_future_action_changed') is True
                    and inner['prefix'].get('three_mutable_graphs_disjoint') is True
                    and inner['prefix'].get('parent_unconsumed') is True
                    and inner['suffixes'][choice].get('status')=='returned'
                    and suffix.get('status')=='unknown_prediction_returned_audit_pending'
                    and inner['suffixes'][choice].get('parent_and_unconsumed_sibling_isolated') is True)
                row.update(status='conditional_forecast' if graph_ok and completion is not None else 'unknown_projection',
                    completion=completion if graph_ok else None,prediction=prediction,execution=suffix)
        origin.require_current(decision)
        result['status']='conditional_forecasts_complete' if all(r['status']=='conditional_forecast' for r in rows) else 'conditional_forecasts_with_unknowns'
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError) as error:
        result.update(status='unknown_initial_origin_or_provider',error=str(error))
        # Retain partial calculations, but an invalid actual origin must not
        # leave any selectable forecast behind.
        for row in rows:row.update(status='unknown_origin_or_provider_failure',completion=None)
    result['provider_preseal_seconds']=time.perf_counter()-started
    result['complete_request_100ms_certified']=False
    result['cost_scope']='Includes source checks/16 fresh guarded initial contexts/16 prefixes/32 suffixes/graph diagnostics and in-memory exports; excludes prior actual collection and future selection/dispatch, which remain separately charged.'
    batch=CandidateBatch(_TOKEN,result,decision)
    batch._provider_elapsed=time.perf_counter()-started
    return batch


def require_current_batch_origin(batch):
    require(type(batch) is CandidateBatch,'conditional_batch_type');batch._read();origin.require_current(batch._decision)
    return batch._decision
