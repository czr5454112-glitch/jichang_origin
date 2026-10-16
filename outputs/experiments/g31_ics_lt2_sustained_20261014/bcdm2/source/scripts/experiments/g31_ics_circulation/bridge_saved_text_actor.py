"""Saved-only fresh actor tree from the exact same gzip text as its observer.

All original checks execute. The retained text spans one synchronous call only;
no actor object aliases the observer and no later file/row supplies its value.
"""
from __future__ import annotations
import ast
import gzip
import inspect
import json
from . import bridge_saved_c_compare as comparison

frozen=comparison.frozen
base,require=frozen.base,frozen.require
Progress=comparison.progress.Progress
progress_contract=comparison.progress.progress_contract
_READER=base.gzread
_READER_CODE=_READER.__code__
_GETATTR=base.ReplayTape.__getattr__
_GETATTR_CODE=_GETATTR.__code__
_LOAD,_LOADS=json.load,json.loads


def read_text_row(path):
    # Same text codec/newline and default decoder as original gzread. No
    # hooks, strict-domain replacement, dumps, or second file read introduced.
    with gzip.open(path,'rt',encoding='utf-8') as stream:
        text=stream.read()
    return json.loads(text),text


def source_proof():
    cproof=comparison.source_proof()
    require(base.gzread is _READER and _READER.__code__ is _READER_CODE
        and base.ReplayTape.__getattr__ is _GETATTR and _GETATTR.__code__ is _GETATTR_CODE
        and json.load is _LOAD and json.loads is _LOADS,'text_actor_source_identity')
    actual=ast.parse(inspect.getsource(_READER))
    expected=ast.parse('def gzread(path):\n    with gzip.open(path, "rt", encoding="utf-8") as f: return json.load(f)\n')
    require(ast.dump(actual,include_attributes=False)==ast.dump(expected,include_attributes=False),'text_actor_original_reader_shape')
    # json.load calls loads(fp.read(), ...). Both reads retain the original
    # defaults. Exact source/runtime versions are frozen by the parent plan.
    load_tree=ast.parse(inspect.getsource(_LOAD))
    return {'schema':'g31.bridge.same_text_actor.source_proof.v1','comparison':{
        'expression':'Exact original semantic_api(a) == semantic_api(b)',
        'reference_C_only_binder':cproof,
        'reference_scope':'The reference binder retains deepcopy before this additional actor substitution; its actor-copy statement is historical, not the combined candidate.'},
        'original_reader_AST_exact':True,'stdlib_json_load_source':inspect.getsourcefile(_LOAD),
        'stdlib_json_load_AST_sha256':frozen.hashlib.sha256(ast.dump(load_tree,include_attributes=False).encode()).hexdigest(),
        'actor':'Second standard json.loads on the identical private immutable text; select result. No encoding or new input read.',
        'observer':'Original first decoded row retained; original observer_result binding is unchanged.',
        'alias_proof':'Standard JSON decoder creates a distinct dict/list for every container occurrence on every invocation. Immutable scalars may be shared exactly as with deepcopy; no decoder hooks or object graph input.',
        'lifetime':'At most one current row text. Cleared before second decode and in a finally on every return/error. No cross-row cache; bounded by current row size, not a claimed byte/WCET cap.',
        'input_domain':'Original standard decoder behavior, including duplicate keys, scalar types, order, signed zero and decoder exceptions. No stricter load domain installed.',
        'future_data':'Both parses consume the same text from exactly one read of the manifest-selected current path; no extra row or file is consulted.',
        'unchanged':'All hashes, ordinal/endpoint/actual-argument/clock checks, full replay/physical guards and original C semantic comparisons.',
        'source_assumption':'Private synchronous fixed-code worker; no concurrent stdlib monkeypatch or arbitrary mutation callback equivalence claim.',
        'native_calls':0,'full_saved_audit_accepted':False}


def replay_type(prefix,progress):
    runtime={'first_row_parses':0,'second_actor_parses':0,'pending_texts':0,'high_water_texts':0,
             'discarded_on_error':0,'instances':0}
    hashed_count=0
    def hashed(path):
        nonlocal hashed_count
        value=base.sha(path);hashed_count+=1
        if hashed_count%256==0:progress.emit('new_row_hash_progress',completed=hashed_count)
        return value
    init=frozen.r.original.clone(base.ReplayTape.__init__,{**base.ReplayTape.__init__.__globals__,'sha':hashed})
    def start(self,directory):
        self._text_binding=None
        self._observer_pending=False
        runtime['instances']+=1
        with progress.stage('new_manifest_and_all_compressed_hashes'):init(self,directory)
        progress.emit('new_row_hash_complete',completed=hashed_count)
    def release(self):
        if self._text_binding is not None:
            self._text_binding=None;runtime['pending_texts']-=1
    def read_bound(self,path):
        require(self._text_binding is None and self._observer_pending is False,'text_actor_unconsumed_prior_row')
        # Original __getattr__ supplied this same selected path; no replacement
        # of its index/manifest expression or any subsequent checks.
        row,text=read_text_row(path)
        self._text_binding=(row,text)
        runtime['first_row_parses']+=1;runtime['pending_texts']+=1
        runtime['high_water_texts']=max(runtime['high_water_texts'],runtime['pending_texts'])
        prefix.consume(row)
        return row
    def retain(self,row):
        require(self._text_binding is not None and self._text_binding[0] is row,'text_actor_same_read_binding')
        text=self._text_binding[1]
        release(self)
        value=json.loads(text)['result']
        runtime['second_actor_parses']+=1
        self._observer_row=row;self._actor_return=value;self._observer_pending=True
        if self.index%256==0:
            progress.emit('api_replay_progress',completed=self.index,old_prefix_completed=prefix.index,
                ordinal=row['ordinal'],endpoint=row['endpoint'])
        return value
    method,proof=frozen.transformed(_GETATTR,[
        ('gzread(self.directory / self.manifest[self.index]["path"])',
         'self._read_bound(self.directory / self.manifest[self.index]["path"])'),
        ("deepcopy(row['result'])",'self._retain_and_parse(row)')],dict(_GETATTR.__globals__))
    def getattr_(self,name):
        original_call=method(self,name)
        def call(*args,**kwargs):
            try:return original_call(*args,**kwargs)
            finally:
                if self._text_binding is not None:runtime['discarded_on_error']+=1
                release(self)
        return call
    cls=type('SameTextActorReplayTape',(base.ReplayTape,),{'__init__':start,'__getattr__':getattr_,
        '_read_bound':read_bound,'_retain_and_parse':retain})
    proof.update(schema='g31.bridge.same_text_actor.replay.v1',runtime=runtime,
        original_checks_preserved=True,default_decoder_unchanged=True,one_current_text_only=True)
    return cls,proof


def binder_function():
    function=comparison.binder_function()
    return frozen.r.original.clone(function,{**function.__globals__,'replay_type':replay_type})


def bind(plan,redirect,progress):
    proof=source_proof()
    execute=binder_function()(plan,redirect,progress)
    def run(directory):
        result,stats=execute(directory)
        bindings=[p for p in stats['ast_proofs'] if p.get('schema')=='g31.bridge.same_text_actor.replay.v1']
        require(len(bindings)==1,'text_actor_proof_denominator')
        runtime=bindings[0]['runtime'];rows=result['replay']['api_rows']
        require(runtime=={'first_row_parses':rows,'second_actor_parses':rows,'pending_texts':0,
            'high_water_texts':1,'discarded_on_error':0,'instances':1},'text_actor_complete_runtime')
        stats['historical_readonly_consumer_proof']=stats['source_proof']
        stats['source_proof']=proof
        stats['policy_return_deepcopy_retained']=False
        stats['policy_return_same_text_fresh_parse']=True
        stats['comparison_restore']=proof['comparison']
        return result,stats
    return run
