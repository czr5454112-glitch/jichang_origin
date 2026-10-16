"""Synthetic driver persistence/audit checks; no real model or native calls."""
import copy
import gzip
import inspect
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import validate_owned_full32_runtime as d


def group():return d.previous.domain.partition_original_domain()['groups'][0]


def test_private_worker_inverse_and_complete_globals():
    proof=d.source_proof()
    assert proof['worker_inverse_AST']['inverse_AST_exact'] and proof['worker_inverse_AST']['exact_statement_count']==1
    assert proof['save_inverse_AST']['inverse_AST_exact'] and proof['save_inverse_AST']['exact_statement_count']==1
    assert d.execute.__code__ is d.previous.execute.__code__ and d.main.__code__ is d.previous.main.__code__
    assert proof['original360_budget_code'] and proof['unchanged_default_GC'] and not proof['100ms_certified']


def test_pending_or_wrong_runtime_source_fails_closed(monkeypatch):
    monkeypatch.setattr(d,'SOURCE_SHA',None)
    with pytest.raises(ValueError,match='not_ready'):d.source_gate()


def test_evaluator_accepts_no_target_or_case_argument():
    assert tuple(inspect.signature(d.execute_group).parameters)==('group','make_context','save_prediction','model','future')
    assert d.LIMIT==360. and len(d.ORDER)==96 and len(d.GROUP_ORDER)==48


def test_private_output_copy_saved_before_postsave_failure(monkeypatch):
    events=[];original={'complete':{'events':[1.,-0.]}};g=group()
    def fake(group,make,save,*,model,future):
        assert make(0,group['representative_action'])=='initial_only'
        ref=save('native_default',original);events.append('terminal_failed_after_save')
        return {'context_constructions':1,'detail':{},'rows':{f'vector_{i:02d}':{'status':'unknown_group_error'} for i in group['candidate_indices']},'ref':ref}
    monkeypatch.setattr(d.runtime,'_group',fake)
    def sink(label,value):
        events.append('durable_save');assert value==original;value['complete']['events'].append(99.);return {'path':'saved'}
    result=d.execute_group(g,lambda i,a:'initial_only',sink,model=d.runtime.future.core,future=d.runtime.future)
    assert events==['durable_save','terminal_failed_after_save'] and original['complete']['events']==[1.,-0.]
    assert all(row['status']=='unknown_group_error' for row in result['rows'].values())


def test_initial_context_failure_retains_both_unknowns():
    def bad(*args):raise ValueError('initial_guard_failed')
    result=d.execute_group(group(),bad,lambda *args:None,model=d.runtime.future.core,future=d.runtime.future)
    assert result['context_constructions']==1 and len(result['rows'])==2
    assert all(row['status']=='unknown_group_error' for row in result['rows'].values())


def test_foreign_factory_rejected_before_context():
    seen=[]
    result=d.execute_group(group(),lambda *args:seen.append(1),lambda *args:None,model=object(),future=d.runtime.future)
    assert not seen and result['context_constructions']==0 and len(result['rows'])==2


@pytest.fixture
def evidence(tmp_path):
    point={'owner':'B','at':1.,'phase':'first_reuse_route','event_sequence':9}
    terminal={'model_time':40.,'event_count':8,'handler_pc':'next_event','remaining_heap_events':0,'consumed':True}
    counts={'initial_engines':1,'initial_advances':1,'prefix_same_resumes':1,'future_forks':2,'future_resumes':2}
    inner={'prefix':{'status':'supported_known_B_cut','parent_unconsumed':True,'isolation_basis':d.runtime.OWNERSHIP,
        'diagnostic_graphs_computed':False,'point':copy.deepcopy(point)},'counts':counts,'points':[point],'suffixes':{}}
    prior={'prefix':{'status':'supported_known_B_cut','point':{**copy.deepcopy(point),'graph_sha256':'historical','graph_encoded_bytes':2}},
        'counts':copy.deepcopy(counts),'points':[{**copy.deepcopy(point),'graph_sha256':'historical','graph_encoded_bytes':2}],'suffixes':{}}
    rows={};targets={}
    for i,choice in enumerate(d.previous.domain.LATER):
        value={'status':'conditional_prediction','all_chronology':[1.,-0.,choice],'completion':{'job':float(i+1)}}
        raw=d.bytes_of(value);path=tmp_path/(choice+'.json.gz');path.write_bytes(gzip.compress(raw,mtime=0))
        action={'future':choice};targets[choice]=raw
        inner['suffixes'][choice]={'status':'returned','isolation_basis':d.runtime.OWNERSHIP,'terminal_state':copy.deepcopy(terminal),
            'initial_cut_action':action,'prediction':d.ref(path)}
        prior['suffixes'][choice]={'status':'returned','terminal_state':{'graph_sha256':'old','graph_encoded_bytes':9,**copy.deepcopy(terminal)},
            'initial_cut_action':copy.deepcopy(action)}
        rows[f'vector_{i:02d}']={'status':'unknown_prediction_returned_audit_pending'}
    result={'context_constructions':1,'detail':inner,'rows':rows}
    old={'status':'exact_two_future_suffixes','result':{'status':'exact_two_future_suffixes','detail':prior}}
    return result,targets,old


def test_full_output_and_every_retained_metadata_matches(evidence):
    result,targets,old=evidence;d.audit_values(result,targets,old)
    assert result['status']=='exact_two_future_suffixes' and all(row['status']=='exact_conformance' for row in result['rows'].values())
    assert result['diagnostic_graphs_remeasured'] is False and result['prior_graph_audit_is_saved_reference_only'] is True
    assert 'three_mutable_graphs_disjoint' not in result['detail']['prefix']


@pytest.mark.parametrize('change',['point_float','point_type','terminal','count','action','graph_flag','postsave',
    'candidate_missing','target_floatbits','choice_order'])
def test_no_tolerance_or_missing_obligation_can_pass(evidence,change):
    result,targets,old=evidence;inner=result['detail'];choice=d.previous.domain.LATER[0]
    if change=='point_float':inner['points'][0]['at']=1.0000000000000002
    elif change=='point_type':inner['points'][0]['at']=1
    elif change=='terminal':inner['suffixes'][choice]['terminal_state']['event_count']+=1
    elif change=='count':inner['counts']['future_resumes']=1
    elif change=='action':inner['suffixes'][choice]['initial_cut_action']['future']='other'
    elif change=='graph_flag':inner['prefix']['three_mutable_graphs_disjoint']=True
    elif change=='postsave':inner['suffixes'][choice]['status']='unknown_suffix_error'
    elif change=='candidate_missing':result['rows'].pop('vector_01')
    elif change=='target_floatbits':targets[choice]=targets[choice].replace(b'-0.0',b'0.0')
    else:inner['suffixes']={k:inner['suffixes'][k] for k in reversed(inner['suffixes'])}
    with pytest.raises(ValueError):d.audit_values(result,targets,old)
    assert not any(row['status']=='exact_conformance' for row in result['rows'].values())


def test_modified_saved_prediction_rejected(evidence):
    result,targets,old=evidence;path=Path(result['detail']['suffixes']['native_default']['prediction']['path'])
    path.write_bytes(b'altered')
    with pytest.raises(ValueError,match='prediction_hash'):d.audit_values(result,targets,old)


def test_bad_target_does_not_remove_durable_outputs(evidence):
    result,targets,old=evidence;paths=[Path(s['prediction']['path']) for s in result['detail']['suffixes'].values()]
    targets['prefer_8']=b'{}'
    with pytest.raises(ValueError,match='complete_prediction_bytes'):d.audit_values(result,targets,old)
    assert all(path.is_file() for path in paths)


def test_comparison_group_hash_before_decode(tmp_path,evidence):
    result,targets,old=evidence;path=tmp_path/'reference.json';d.write(path,old)
    with pytest.raises(ValueError,match='comparison_only_group_hash'):
        d._audit_group(result,targets,{'path':str(path),'sha256':'0'*64})
