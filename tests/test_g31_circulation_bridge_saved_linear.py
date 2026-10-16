from copy import deepcopy
import inspect
import json
import math
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import bridge_saved_linear_core as c
from scripts.experiments.g31_ics_circulation import audit_bridge_saved_linear as a


@pytest.mark.parametrize('left,right', [
    ({'a':1,'b':2},{'a':1,'b':2}), ({'a':1,'b':2},{'b':2,'a':1}),
    (True,1),(False,0),(1,1.0),(-0.0,0.0),(-0.0,-0.0),
    ([1,2],[1]),([1,{'x':'中🚀\n'}],[1,{'x':'中🚀\n'}]),
    (5e-324,5e-324),(1e20,1e20),([],()),({1:'a','1':'b'},{1:'a','1':'b'}),
    ({'x':None},{'x':False}),({'extra':{'x':1}},{'extra':{'x':2}}),
])
def test_ordered_json_exact_differential(left,right):
    assert c.ordered_equal(left,right) == (c.full.ordered(left)==c.full.ordered(right))


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-float('inf'),object()])
def test_invalid_json_never_passes(bad):
    with pytest.raises((ValueError,TypeError)):c.ordered_equal({'x':bad},{'x':bad})


def row(ordinal=0, endpoint='protocol_command', result=None, args=None, before=0., after=0.):
    return {'ordinal':ordinal,'endpoint':endpoint,'args':args or ['A','R'], 'kwargs':{},
            'before':before,'result':result if result is not None else {'state':{'x':[1,-0.0]}},'after':after}


@pytest.mark.parametrize('bad',[True,-1,float('nan'),float('inf')])
def test_wall_exclusion_rejects_invalid_scalar(bad):
    left=row(endpoint='advance_to',result={'wall_seconds':bad,'state':'reached'})
    with pytest.raises(ValueError):c.semantic_equal(left,left)


def test_only_wall_is_excluded_and_actual_argument_order_is_checked():
    left=row(endpoint='advance_to',result={'wall_seconds':1.,'state':'reached'})
    right=deepcopy(left);right['result']['wall_seconds']=2.
    assert c.semantic_equal(left,right)
    right['result']['state']='changed';assert not c.semantic_equal(left,right)
    left=row(args=[{'a':1,'b':2}]);right=row(args=[{'b':2,'a':1}])
    assert left==right and not c.semantic_equal(left,right)


def tape(tmp_path,rows):
    directory=tmp_path/'tape';directory.mkdir();manifest=[]
    for i,value in enumerate(rows):
        path=directory/f'{i:06d}.json.gz';c.base.gzwrite(path,value)
        manifest.append({'path':path.name,'sha256':c.base.sha(path),'endpoint':value['endpoint']})
    (directory/'manifest.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in manifest))
    return directory


class Comparison:
    def __init__(self):self.index=0;self.rows=[]
    def consume(self,value):self.index+=1;self.rows.append(value)


def test_real_replay_method_retains_actor_copy_and_private_observer_alias(tmp_path):
    directory=tape(tmp_path,[row(),row(1)])
    p=c.Progress(tmp_path);comp=Comparison();Replay,proof=c.replay_type(comp,p)
    old=c.base.ReplayTape(directory);new=Replay(directory)
    first=new.protocol_command('A','R');baseline=old.protocol_command('A','R')
    assert c.ordered_equal(first,baseline) and first is not new._observer_row['result']
    observed=c.observer_result(first,new,0);saved=deepcopy(observed)
    first['state']['x'].append(9)
    assert observed==saved and comp.rows[0]['result']==saved
    second=new.protocol_command('A','R');baseline2=old.protocol_command('A','R')
    assert c.ordered_equal(second,baseline2) and observed==saved
    with pytest.raises(ValueError,match='binding'):c.observer_result(first,new,1)
    assert proof['inverse_ast_exact'];p.close()


@pytest.mark.parametrize('change',['hash','ordinal','endpoint','args','before','after','error','extra_file','missing'])
def test_real_replay_preserves_rejections(tmp_path,change):
    value=row()
    if change=='ordinal':value['ordinal']=1
    if change=='endpoint':value['endpoint']='protocol_request'
    if change=='args':value['args']=['B','R']
    if change=='before':value['before']=1.
    if change=='after':value['after']=1.
    if change=='error':value['error']='saved error'
    directory=tape(tmp_path,[value])
    if change=='hash':(directory/'000000.json.gz').write_bytes(b'changed')
    if change=='extra_file':(directory/'extra.json.gz').write_bytes(b'extra')
    if change=='missing':(directory/'000000.json.gz').unlink()
    p=c.Progress(tmp_path);Replay,_=c.replay_type(Comparison(),p)
    try:
        with pytest.raises((ValueError,FileNotFoundError)):
            replay=Replay(directory);replay.protocol_command('A','R')
    finally:p.close()


def test_shared_exact_paths_decode_once_without_cross_request_cache(tmp_path):
    p=c.Progress(tmp_path);calls=[];value={'owners':[{'calls':[]}],'result':{'jobs':[]}}
    def load(path):calls.append(path);return deepcopy(value)
    shared=c.SharedReads(tmp_path,p,load)
    for name in ('raw_final.json.gz','input.json.gz'):
        first=shared.read(tmp_path/name);second=shared.read(tmp_path/name)
        assert first is second and first==value
    shared.read(tmp_path/'other.json.gz');shared.read(tmp_path/'other.json.gz')
    assert len(calls)==4 and len(shared.values)==2 and len(shared.finish())==2
    assert c.base.normalized_owners([{'calls':[{'submit_compute_ms':1.,'request':{'x':[1]}}]}])==[{'calls':[{'request':{'x':[1]}}]}]
    p.close()


def test_shared_incomplete_reads_cannot_certify(tmp_path):
    p=c.Progress(tmp_path);shared=c.SharedReads(tmp_path,p,lambda _: {})
    shared.read(tmp_path/'raw_final.json.gz')
    with pytest.raises(ValueError,match='denominator'):shared.finish()
    p.close()


def test_progress_bound_failure_and_original_exception(tmp_path):
    p=c.Progress(tmp_path);p.LIMIT=1;p.emit('first')
    with pytest.raises(ValueError,match='budget'):p.emit('second')
    assert len(p.path.read_text().splitlines())==1;p.close()
    other=tmp_path/'other';other.mkdir();p=c.Progress(other)
    with pytest.raises(RuntimeError,match='original'):
        with p.stage('test'):raise RuntimeError('original')
    p.close();rows=[json.loads(x) for x in p.path.read_text().splitlines()]
    assert [x['event'] for x in rows]==['stage_start','stage_failed']


def test_progress_close_always_closes_after_flush_error(tmp_path):
    p=c.Progress(tmp_path);p.stream.close();closed=[]
    class Failed:
        def flush(self):raise OSError('flush')
        def close(self):closed.append(True)
    p.stream=Failed()
    with pytest.raises(OSError,match='flush'):p.close()
    assert closed==[True]


def test_consumer_identity_or_code_mutation_rejected(monkeypatch):
    c.source_proof()
    monkeypatch.setattr(c.full,'physical_outcomes',lambda *args:None)
    with pytest.raises(ValueError,match='identity_changed'):c.source_proof()


def test_exact_inverse_proof_preserves_all_full_verifier_guards():
    substitutions=[('deepcopy(value)','observer_result(value, self, ordinal)'),
        ('semantic_api(row) == semantic_api(base.gzread(oldpath))','semantic_equal(row, base.gzread(oldpath))')]
    fn,proof=c.transformed(c.full.verify_case,substitutions,
        {**c.full.verify_case.__globals__,'observer_result':c.observer_result,'semantic_equal':c.semantic_equal})
    assert proof['inverse_ast_exact'] and fn.__globals__ is not c.full.verify_case.__globals__
    with pytest.raises(ValueError,match='substitution_count'):
        c.transformed(c.full.verify_case,[('absent(1)','other(1)')],vars(c.full))


class GuardDict(dict):
    def denied(self,*a,**k):raise AssertionError('shared consumer mutated input')
    __setitem__=__delitem__=clear=pop=popitem=setdefault=update=denied
    def __deepcopy__(self,memo):return {deepcopy(k,memo):deepcopy(v,memo) for k,v in self.items()}

class GuardList(list):
    def denied(self,*a,**k):raise AssertionError('shared consumer mutated input')
    __setitem__=__delitem__=append=extend=insert=pop=remove=clear=reverse=sort=__iadd__=__imul__=denied
    def __deepcopy__(self,memo):return [deepcopy(v,memo) for v in self]

def guarded(value):
    if type(value) is dict:return GuardDict({k:guarded(v) for k,v in value.items()})
    if type(value) is list:return GuardList(guarded(v) for v in value)
    return value


def test_real_native_physical_auditor_consumers_readonly_no_native():
    data={'trays':[{'tray_id':'T','node':0}], 'jobs':[], 'transfers':[], 'edge_records':[],
          'edge_contracts':[], 'node_contracts':[{'node':0,'capacity':1}]}
    result={'mode':'circulation','trays':[{'tray_id':'T','node':0,'edge_to':-1}], 'jobs':[],
        'leg_identities':[], 'receipts':[], 'decisions':[],
        'native_summary':{'reservation_conflicts':0,'physical_fault_edge_entry_violation_count':0}}
    a=c.native_host.audit_result(data,result)
    b=c.native_host.audit_result(guarded(data),guarded(result))
    assert a==b and a['status']=='passed'


def test_real_full_outcomes_and_assessor_readonly_alloffered_fixture():
    jobs=[{'business_bag_id':str(i),'origin':0,'arrival':float(i),'destination':1,'storage_node':-1} for i in range(28506)]
    trays=[{'tray_id':str(i),'node':1,'mode':'empty','job':-1,'edge_to':-1,'available_at':1.} for i in range(22)]
    parking=[{'request_id':'p'+str(i),'tray_id':str(i),'source':0,'destination':1} for i in range(22)]
    calls=[{'kind':'transfer','retry':False,'submit_compute_ms':0.,'request':{**p,'owner_id':'A'}} for p in parking]
    owner={'owner':'A','supply':None,'operations':[],'bridge_publications':[],'consumed_completions':[],
        'calls':calls,'cap_relay':None,'failure':None,'outbox':{'outbox':{p['request_id']:{'kind':'transfer',
        'terminal':True,'client_view':{'last_delivered_ack':{'status':'received'}}} for p in parking}}}
    raw={'physical_time':86400.,'status':'horizon_complete','owners':[owner], 'result':{
        'jobs':[{'business_bag_id':j['business_bag_id'],'status':'waiting'} for j in jobs],'trays':trays,
        'advance':{'horizon_complete':True},'receipts':[{'event':'EMPTY_RECEIVED','reason':p['request_id'],
        'tray_id':p['tray_id'],'node':1,'time':1.} for p in parking]}}
    data={'jobs':jobs,'trays':trays};plan={'parking_plan':{'parking':parking,'token_tray_id':'0'},'public_contract':{}}
    expected=c.full.physical_outcomes(data,raw,plan)
    assert c.full.physical_outcomes(guarded(data),guarded(raw),guarded(plan))==expected
    assert c.r.original.assess(guarded(raw),guarded(plan))==c.r.original.assess(raw,plan)


def test_new_driver_keeps_old_source_and_fixed_budget():
    assert a.LIMIT==600 and a.prior.LIMIT==600 and a.MODULE!=a.prior.MODULE
    assert 'NativeSession' not in inspect.getsource(a.audit)
    assert a.namespace()['main'].__code__ is a.prior.main.__code__
    assert a.namespace()['verify_plan'] is a.verify_plan


def test_observer_binding_is_single_use_even_for_null():
    replay=SimpleNamespace(index=1,_observer_row={'ordinal':0,'result':None},
        _actor_return=None,_observer_pending=True)
    assert c.observer_result(None,replay,0) is None
    with pytest.raises(ValueError,match='binding'):c.observer_result(None,replay,0)


def test_private_factory_threads_shared_loader_to_inner_verifier(tmp_path,monkeypatch):
    reference=tmp_path/'reference';directory=reference/'bridge/api';directory.mkdir(parents=True)
    manifest=directory/'manifest.jsonl';manifest.write_text('')
    monkeypatch.setattr(c.r,'REFERENCE',reference);monkeypatch.setattr(c.r,'PREFIX_ROWS',0)
    monkeypatch.setattr(c.r,'MANIFEST_SHA',c.base.sha(manifest))
    source=tmp_path/'source';(source/'bridge').mkdir(parents=True);output=tmp_path/'new';output.mkdir()
    redirect=c.old.DerivedOutput(source,output);progress=c.Progress(output)
    original_globals=dict(vars(c.base))
    execute=c.bind({'source_before':{}},redirect,progress)
    captured=dict(zip(execute.__code__.co_freevars,(x.cell_contents for x in execute.__closure__)))
    checker=captured['checker'];shared=captured['shared'];runner=checker.__globals__['r']
    private=runner.isolated_base(ReplayTape=checker.__globals__['base'].ReplayTape,run_policy=lambda *a:None)
    assert private.verify_saved.__code__ is c.base.verify_saved.__code__
    assert private.verify_saved.__globals__['gzread']==shared.read
    assert checker.__globals__['base'].gzread==shared.read
    assert checker.__globals__['base'].gzwrite.__closure__
    assert vars(c.base)==original_globals
    progress.close()


def test_original_inner_verifier_readonly_shared_inputs_and_real_physical_audit(tmp_path):
    data={'jobs':[{'business_bag_id':str(i),'arrival':float(i),'deadline':-1} for i in range(28506)],
        'trays':[{'tray_id':str(i),'node':0} for i in range(22)], 'transfers':[],
        'node_contracts':[{'node':0,'capacity':22}], 'edge_contracts':[], 'edge_records':[]}
    result={'mode':'circulation','trays':[{'tray_id':str(i),'node':0,'edge_to':-1} for i in range(22)],
        'jobs':[{'loaded_at':-1,'storage_released_at':-1,'completed_at':-1} for _ in data['jobs']],
        'leg_identities':[], 'receipts':[], 'decisions':[],
        'native_summary':{'reservation_conflicts':0,'physical_fault_edge_entry_violation_count':0}}
    owners=[{'calls':[]}];assessment={'fixture':'unchanged'}
    raw={'input_sha256':c.base.INPUT_SHA,'binary_sha256':c.base.BINARY_SHA,'plan_sha256':'p'*64,
        'status':'fixture','tick':0,'physical_time':0.,'owners':owners,'result':result,
        'offered':28506,'native_state_sha256':'a'*64,'source_changed':[],
        'physical_audit':c.native_host.audit_result(data,result)}
    plan={'public_contract':{'node_contracts':data['node_contracts']},'inventory':data['trays'],'parking_plan':{}}
    class Replay:
        def __init__(self,*args):self.index=1;self.manifest=[{}];self.physical_time=0.
    actor=SimpleNamespace(summary=lambda:deepcopy(owners[0]),client=SimpleNamespace(calls=[]))
    protected_data,protected_raw=guarded(data),guarded(raw)
    private=c.r.original.isolated_base(verify_pins=lambda *a,**k:None,
        gzread=lambda path:protected_data if path.name=='input.json.gz' else protected_raw,
        read=lambda path:plan if path.name=='preregistered_protocol.json' else assessment,
        parking_plan=lambda *a:{},sha=lambda path:'p'*64,ReplayTape=Replay,
        run_policy=lambda *a:([actor],'fixture',0),assess=lambda *a:assessment)
    answer=private.verify_saved(tmp_path)
    assert answer['status']=='passed_saved_raw_replay' and protected_data==data and protected_raw==raw


def test_source_only_preparation_defers_large_artifact_reads_to_full_execute():
    text=inspect.getsource(a.prepare)
    assert 'gzread(' not in text and 'terminal_refs(' not in text and 'verify_plan(' not in text
    assert 'large_evidence_reads_this_preparation' in text
    assert 'prior.verify_plan' in inspect.getsource(a.verify_plan)


@pytest.mark.parametrize('change',['none','hash','field','order','float_type','missing_tail'])
def test_old_prefix_all_hashes_and_ordered_fields_retained(tmp_path,change):
    values=[row(),row(1)];directory=tape(tmp_path,values)
    consume,proof=c.transformed(c.original.PrefixComparison.consume,
        [('semantic_api(old) == semantic_api(row)','semantic_equal(old, row)')],
        {**c.original.PrefixComparison.consume.__globals__,'semantic_equal':c.semantic_equal})
    cls=type('TestPrefix',(c.original.PrefixComparison,),{'consume':consume})
    comparison=cls(directory,c.base.sha(directory/'manifest.jsonl'),2)
    current=deepcopy(values[0])
    if change=='hash':(directory/'000000.json.gz').write_bytes(b'changed')
    if change=='field':current['result']['state']['x'].append(9)
    if change=='order':current={key:current[key] for key in reversed(current)}
    if change=='float_type':current['result']['state']['x'][0]=1.0
    if change in ('hash','field','order','float_type'):
        with pytest.raises(ValueError):comparison.consume(current)
    else:
        comparison.consume(current)
        if change=='missing_tail':
            with pytest.raises(ValueError,match='incomplete'):comparison.finish()
        else:
            comparison.consume(values[1]);assert comparison.finish()['rows']==2
    assert proof['inverse_ast_exact']
