from contextlib import contextmanager
from copy import deepcopy
import gzip
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import bridge_saved_text_actor as c
from scripts.experiments.g31_ics_circulation import audit_bridge_saved_text_actor as a


class Journal:
    def __init__(self):self.rows=[]
    def emit(self,event,**fields):self.rows.append((event,fields))
    @contextmanager
    def stage(self,name):yield


class Prefix:
    def __init__(self):self.rows=[];self.index=0
    def consume(self,row):self.rows.append(row);self.index+=1


def save(directory,values,changed=None):
    directory.mkdir()
    manifest=[]
    for i,value in enumerate(values):
        row={'ordinal':i,'endpoint':'observe_protocol_control_policy_recent','args':['domestic'],
            'kwargs':{},'before':0.0,'result':value,'after':0.0}
        if changed:changed(row)
        path=directory/f'{i:06d}.json.gz'
        with gzip.open(path,'wt',encoding='utf-8') as f:json.dump(row,f,ensure_ascii=False)
        manifest.append({'path':path.name,'sha256':c.base.sha(path)})
    (directory/'manifest.jsonl').write_text('\n'.join(json.dumps(r) for r in manifest)+'\n',encoding='utf8')
    return directory


def replay(directory,prefix=None):
    prefix=prefix or Prefix();journal=Journal()
    cls,proof=c.replay_type(prefix,journal)
    tape=cls(directory)
    return tape,prefix,proof,journal


@pytest.mark.parametrize('value',[None,True,1,1.0,-0.0,'中文🌍',{'b':[1,False],'a':[]},[{'x':[-0.0]},[]]])
def test_actual_original_guard_flow_and_mutable_disjoint(tmp_path,value):
    tape,prefix,proof,_=replay(save(tmp_path/'api',[value]))
    returned=tape.observe_protocol_control_policy_recent('domestic')
    observed=c.frozen.observer_result(returned,tape,0)
    assert c.frozen.ordered_equal(returned,observed)
    def ids(v):
        result={id(v)} if type(v) in (dict,list) else set()
        for item in v.values() if type(v) is dict else v if type(v) is list else []:result|=ids(item)
        return result
    assert ids(returned).isdisjoint(ids(observed))
    assert observed is prefix.rows[0]['result']
    assert tape._text_binding is None and tape._observer_pending is False
    assert proof['runtime']=={'first_row_parses':1,'second_actor_parses':1,'pending_texts':0,
        'high_water_texts':1,'discarded_on_error':0,'instances':1}


def test_actor_mutation_cannot_modify_original_observer_or_next_row(tmp_path):
    tape,prefix,proof,_=replay(save(tmp_path/'api',[{'x':[]},{'x':[]}]))
    first=tape.observe_protocol_control_policy_recent('domestic')
    observed=c.frozen.observer_result(first,tape,0);first['x'].append('actor')
    second=tape.observe_protocol_control_policy_recent('domestic')
    other=c.frozen.observer_result(second,tape,1)
    assert observed==other=={'x':[]} and second=={'x':[]}
    assert proof['runtime']['pending_texts']==0


def test_second_parse_never_reads_replaced_file_or_future_row(tmp_path):
    directory=save(tmp_path/'api',[{'x':[1]}]);prefix=Prefix()
    def consume(row):
        Prefix.consume(prefix,row)
        # This synthetic mutation is NOT an accepted immutable-input audit;
        # it only proves no second read supplies the returned actor value.
        (directory/'000000.json.gz').write_bytes(b'changed after original read')
    prefix.consume=consume
    tape,_,proof,_=replay(directory,prefix)
    result=tape.observe_protocol_control_policy_recent('domestic')
    assert result=={'x':[1]};c.frozen.observer_result(result,tape,0)
    assert proof['runtime']['first_row_parses']==proof['runtime']['second_actor_parses']==1


@pytest.mark.parametrize('field,value',[('ordinal',3),('endpoint','protocol_command'),('args',['foreign']),
    ('kwargs',{'x':1}),('before',2.0),('after',1.0),('error','native error')])
def test_original_payload_clock_and_error_guards_remain(tmp_path,field,value):
    tape,prefix,proof,_=replay(save(tmp_path/'api',[{}],lambda row:row.update({field:value})))
    with pytest.raises(ValueError):tape.observe_protocol_control_policy_recent('domestic')
    assert tape._text_binding is None
    assert proof['runtime']['pending_texts']==0 and proof['runtime']['second_actor_parses']==0
    assert proof['runtime']['discarded_on_error']==1


def test_original_hash_and_missing_tape_file_guard(tmp_path):
    directory=save(tmp_path/'api',[{}]);(directory/'000000.json.gz').write_bytes(b'wrong')
    with pytest.raises(ValueError,match='tape_identity_or_hash'):replay(directory)
    (directory/'000000.json.gz').unlink()
    with pytest.raises(ValueError,match='omitted_tape_file'):replay(directory)


def test_prefix_error_stays_primary_and_sidecar_clears(tmp_path):
    prefix=Prefix();failure=ValueError('original comparison failed')
    def bad(row):raise failure
    prefix.consume=bad;tape,_,proof,_=replay(save(tmp_path/'api',[{}]),prefix)
    with pytest.raises(ValueError) as caught:tape.observe_protocol_control_policy_recent('domestic')
    assert caught.value is failure and tape._text_binding is None and proof['runtime']['pending_texts']==0


def test_second_parser_error_stays_primary_and_no_actor_claim(tmp_path,monkeypatch):
    tape,prefix,proof,_=replay(save(tmp_path/'api',[{}]));original=json.loads;calls=[]
    failure=MemoryError('second decoder failed')
    def decode(text,*args,**kwargs):
        calls.append(text)
        if len(calls)==2:raise failure
        return original(text,*args,**kwargs)
    monkeypatch.setattr(c.json,'loads',decode)
    with pytest.raises(MemoryError) as caught:tape.observe_protocol_control_policy_recent('domestic')
    assert caught.value is failure and tape._text_binding is None
    assert proof['runtime']['pending_texts']==proof['runtime']['second_actor_parses']==0
    assert tape._observer_pending is False


def test_unconsumed_observer_blocks_next_row_not_silently_overwritten(tmp_path):
    tape,_,_,_=replay(save(tmp_path/'api',[{},{}]))
    result=tape.observe_protocol_control_policy_recent('domestic')
    with pytest.raises(ValueError,match='unconsumed_prior_row'):tape.observe_protocol_control_policy_recent('domestic')
    c.frozen.observer_result(result,tape,0)
    value=tape.observe_protocol_control_policy_recent('domestic');c.frozen.observer_result(value,tape,1)


@pytest.mark.parametrize('text',[
    '{"result":{"x":1,"y":2,"x":3}}',
    '{"result":[true,1,1.0,-0.0]}',
    '{"result":"\\ud83c\\udf0d"}',
    '{"result":"\\ud800"}',
    '{"result":NaN}',
    '{"result":Infinity}',
])
def test_default_decoder_domain_not_replaced_by_strict_guard(tmp_path,text):
    path=tmp_path/'row.gz'
    with gzip.open(path,'wt',encoding='utf8') as f:f.write(text)
    expected=c.base.gzread(path);row,retained=c.read_text_row(path)
    assert retained==text
    # Encode with default ASCII/nonfinite settings only for this decoder-domain
    # test; full verifier retains its original allow_nan=False comparison.
    assert json.dumps(expected)==json.dumps(row)==json.dumps(json.loads(retained))


def test_reader_and_binder_complete_private_namespace():
    proof=c.source_proof();function=c.binder_function();old=c.frozen.bind
    assert proof['original_reader_AST_exact'] and function.__code__ is old.__code__
    assert function.__closure__ is old.__closure__ and function.__defaults__ is old.__defaults__
    assert set(function.__globals__)==set(old.__globals__)
    changed={k for k in old.__globals__ if function.__globals__[k] is not old.__globals__[k]}
    assert changed=={'SharedReads','semantic_equal','replay_type'}
    assert function.__globals__['semantic_equal'] is c.comparison.semantic_equal
    assert function.__globals__['observer_result'] is c.frozen.observer_result
    assert function.__globals__['Path'] is old.__globals__['Path']


def test_all_original_replay_guards_inverse_ast_proven():
    _,proof=c.replay_type(Prefix(),Journal())
    assert proof['inverse_ast_exact'] and len(proof['expressions'])==2
    assert proof['expressions'][0][0]=='gzread(self.directory / self.manifest[self.index]["path"])'
    assert proof['expressions'][1][0]=="deepcopy(row['result'])"


def test_decoder_identity_change_invalidates_source(monkeypatch):
    monkeypatch.setattr(c.json,'loads',lambda x:{})
    with pytest.raises(ValueError,match='text_actor_source_identity'):c.source_proof()


def test_runtime_complete_proof_not_manufactured(monkeypatch):
    def fake_binder():
        def bind(plan,redirect,progress):
            def run(directory):return {'replay':{'api_rows':2}},{'ast_proofs':[], 'source_proof':{},'policy_return_deepcopy_retained':True}
            return run
        return bind
    monkeypatch.setattr(c,'binder_function',fake_binder)
    with pytest.raises(ValueError,match='proof_denominator'):c.bind({},None,Journal())(Path('unused'))


def test_driver_private_namespace_binds_new_core_and_all_inherited_globals():
    ns=a.namespace();old=a.previous.namespace()
    assert set(old)<=set(ns) and ns['Path'] is Path
    assert ns['core'] is c and ns['verify_plan'] is a.verify_plan and ns['audit'] is a.audit
    assert ns['LIMIT']==600. and ns['MODULE']==a.MODULE
    assert ns['prior'] is a.prior and ns['base'] is a.base


def test_driver_main_actual_argument_parser_globals(monkeypatch,capsys):
    monkeypatch.setattr(sys,'argv',[a.MODULE,'--help'])
    with pytest.raises(SystemExit) as caught:a.main()
    assert caught.value.code==0 and '--plan-sha256' in capsys.readouterr().out


def test_driver_clone_selects_new_core_without_changing_previous(monkeypatch):
    original=a.previous.audit.__globals__['core'];captured=[]
    def audit(output,expected):
        captured.append((output,expected))
    # Test actual clone mechanism with a small source function. Existing
    # previous/source code is never edited or executed against saved inputs.
    clone=a.r.original.clone(audit,{**audit.__globals__,'core':c})
    clone('new','sha')
    assert captured==[('new','sha')] and a.previous.audit.__globals__['core'] is original
